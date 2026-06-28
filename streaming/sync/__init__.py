"""
Tier 4 — sync. Fan live scene state + events out to clients.

    from streaming.sync import StatePublisher, SinkHub, LiveDashboard

`StateSink` is the swappable destination contract; `SinkHub` fans out to many;
`StatePublisher` drives it from the pipeline thread. `LiveDashboard` is a built-in
browser sink (FastAPI/SSE); `PowerSyncSink` persists to Postgres for PowerSync to
stream everywhere. PowerSyncSink is imported lazily (needs psycopg) via
`from streaming.sync.powersync_sink import PowerSyncSink`.
"""

from streaming.sync.dashboard import LiveDashboard
from streaming.sync.sink import SinkHub, StatePublisher, StateSink

__all__ = [
    "StateSink",
    "SinkHub",
    "StatePublisher",
    "LiveDashboard",
]
