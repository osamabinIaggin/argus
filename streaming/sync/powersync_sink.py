"""
PowerSyncSink — persist live scene state + events to Postgres so PowerSync can
stream them to every connected client (dashboard, chat, robot planner).

PowerSync syncs *database rows*, so the contract is simply: keep two tables fresh
and PowerSync's sync rules (see `powersync.yaml`) handle delivery, offline replay,
and per-client scoping. We write:

  * `scene_state(source_id PK, snapshot JSONB, updated_at)` — upserted; one live
    row per stream, always the latest snapshot.
  * `scene_events(seq BIGSERIAL, source_id, type, ts_wall, message, data JSONB)` —
    append-only; the derived event log.

Robustness: on_event/on_snapshot only enqueue (never block the pipeline). A single
writer thread drains the queue and writes; on a DB error it reconnects with
backoff and keeps going. If the queue backs up (slow/broken DB), the *snapshot* is
coalesced to the latest (drop-stale) while events are preserved up to a bound —
the live view stays fresh and we never grow memory without limit.

Setup (when you have infra):
  ./.venv/bin/pip install "psycopg[binary]"
  export DATABASE_URL=postgres://user:pass@host:5432/db
  # apply SCHEMA_SQL once, then point PowerSync at powersync.yaml
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from typing import Optional

from streaming.scene.events import Event
from streaming.sync.sink import StateSink

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scene_state (
    source_id   text PRIMARY KEY,
    snapshot    jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS scene_events (
    seq        bigserial PRIMARY KEY,
    source_id  text NOT NULL,
    type       text NOT NULL,
    ts_wall    double precision NOT NULL,
    message    text NOT NULL,
    data       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS scene_events_source_idx ON scene_events (source_id, seq);
"""


class PowerSyncSink(StateSink):
    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        ensure_schema: bool = True,
        max_queue: int = 2000,
        backoff_s: float = 2.0,
    ) -> None:
        self.dsn = dsn or os.environ.get("DATABASE_URL")
        if not self.dsn:
            raise ValueError("PowerSyncSink needs a DSN (arg) or DATABASE_URL env var")
        self.ensure_schema = ensure_schema
        self.backoff_s = backoff_s
        # ('event', dict) | ('state', dict). Snapshots are coalesced to latest.
        self._q: "queue.Queue[tuple]" = queue.Queue(maxsize=max_queue)
        self._latest_snapshot: Optional[dict] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._conn = None
        self.written_events = 0
        self.written_snapshots = 0
        self.dropped = 0
        self._thread = threading.Thread(target=self._loop, name="powersync", daemon=True)
        self._thread.start()

    # -- StateSink (pipeline thread; cheap, non-blocking) -----------------
    def on_event(self, event: Event) -> None:
        try:
            self._q.put_nowait(("event", event.to_dict()))
        except queue.Full:
            self.dropped += 1  # DB can't keep up; shed events rather than block Tier 1

    def on_snapshot(self, snapshot: dict) -> None:
        # Coalesce: only the freshest snapshot matters for the live row.
        with self._lock:
            self._latest_snapshot = snapshot
        try:
            self._q.put_nowait(("state", None))  # wake the writer; payload read under lock
        except queue.Full:
            pass

    # -- writer thread -----------------------------------------------------
    def _connect(self):
        import psycopg  # type: ignore

        self._conn = psycopg.connect(self.dsn, autocommit=True)
        if self.ensure_schema:
            self._conn.execute(SCHEMA_SQL)
        logger.info("PowerSyncSink connected")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._conn is None:
                    self._connect()
                kind, payload = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception as exc:  # noqa: BLE001 — connect failed; back off and retry
                logger.warning("PowerSyncSink connect failed: %s", exc)
                self._conn = None
                self._stop.wait(self.backoff_s)
                continue
            try:
                if kind == "event":
                    self._write_event(payload)
                else:
                    with self._lock:
                        snap = self._latest_snapshot
                    if snap is not None:
                        self._write_snapshot(snap)
            except Exception as exc:  # noqa: BLE001 — DB hiccup; drop conn, reconnect
                logger.warning("PowerSyncSink write failed: %s", exc)
                self._conn = None
                self._stop.wait(self.backoff_s)

    def _write_event(self, e: dict) -> None:
        self._conn.execute(
            "INSERT INTO scene_events (source_id, type, ts_wall, message, data) "
            "VALUES (%s, %s, %s, %s, %s)",
            (e["source_id"], e["type"], e["ts_wall"], e["message"], json.dumps(e["data"])),
        )
        self.written_events += 1

    def _write_snapshot(self, snap: dict) -> None:
        self._conn.execute(
            "INSERT INTO scene_state (source_id, snapshot, updated_at) "
            "VALUES (%s, %s, now()) "
            "ON CONFLICT (source_id) DO UPDATE SET snapshot = EXCLUDED.snapshot, "
            "updated_at = now()",
            (snap["source_id"], json.dumps(snap)),
        )
        self.written_snapshots += 1

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3.0)
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None
