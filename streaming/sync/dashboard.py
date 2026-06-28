"""
LiveDashboard — a self-contained browser dashboard sink.

Implements StateSink and runs a tiny FastAPI + Server-Sent-Events server in a
background thread. The pipeline writes updates into thread-safe buffers via
on_event/on_snapshot; the browser holds one EventSource connection and renders
entities (on a bbox canvas), zones, activity, the latest semantic read, and a
live event feed.

SSE (not WebSocket) on purpose: it is one-directional server→client, survives
reconnects natively, and needs no extra deps. FastAPI/uvicorn are imported lazily
inside start(), so this module stays importable (and unit-testable) without them.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from typing import Optional, Tuple

from streaming.scene.events import Event
from streaming.sync.sink import StateSink

logger = logging.getLogger(__name__)


class LiveDashboard(StateSink):
    def __init__(self, host: str = "127.0.0.1", port: int = 8800, event_buffer: int = 500) -> None:
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        self._snapshot: dict = {}
        self._snapshot_v = 0
        self._events: deque[Tuple[int, dict]] = deque(maxlen=event_buffer)
        self._seq = 0
        self._server = None
        self._thread: Optional[threading.Thread] = None

    # -- StateSink (pipeline thread; cheap) --------------------------------
    def on_event(self, event: Event) -> None:
        with self._lock:
            self._seq += 1
            self._events.append((self._seq, event.to_dict()))

    def on_snapshot(self, snapshot: dict) -> None:
        with self._lock:
            self._snapshot = snapshot
            self._snapshot_v += 1

    # -- thread-safe reads for the SSE generator --------------------------
    def _read_snapshot(self) -> Tuple[dict, int]:
        with self._lock:
            return self._snapshot, self._snapshot_v

    def _events_since(self, seq: int) -> list[Tuple[int, dict]]:
        with self._lock:
            return [(s, e) for (s, e) in self._events if s > seq]

    # -- server lifecycle --------------------------------------------------
    def start(self) -> None:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse, StreamingResponse

        app = FastAPI()

        @app.get("/")
        def index() -> "HTMLResponse":
            return HTMLResponse(_HTML)

        @app.get("/stream")
        def stream() -> "StreamingResponse":
            return StreamingResponse(self._sse(), media_type="text/event-stream")

        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="dashboard", daemon=True)
        self._thread.start()
        logger.info("dashboard live at http://%s:%d", self.host, self.port)

    async def _sse(self):
        import asyncio

        last_v = -1
        last_seq = 0
        while True:
            snap, v = self._read_snapshot()
            if v != last_v:
                yield f"event: state\ndata: {json.dumps(snap)}\n\n"
                last_v = v
            for s, e in self._events_since(last_seq):
                yield f"event: ev\ndata: {json.dumps(e)}\n\n"
                last_seq = s
            await asyncio.sleep(0.2)

    def close(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


_HTML = """<!doctype html><html><head><meta charset=utf-8>
<title>Argus — live</title><style>
:root{color-scheme:dark}
body{margin:0;background:#0b0e14;color:#cdd6f4;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
header{display:flex;align-items:center;gap:16px;padding:12px 18px;border-bottom:1px solid #1c2230;background:#0d111a}
h1{font-size:16px;margin:0;letter-spacing:.5px}
.pill{padding:2px 10px;border-radius:999px;font-size:12px;background:#1c2230}
.idle{color:#6c7086}.low{color:#a6e3a1}.medium{color:#f9e2af}.high{color:#f38ba8}
main{display:grid;grid-template-columns:1.1fr .9fr;gap:14px;padding:14px}
.card{background:#0d111a;border:1px solid #1c2230;border-radius:10px;padding:12px}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#6c7086;margin:0 0 8px}
canvas{width:100%;background:#070a10;border-radius:8px;border:1px solid #1c2230}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:3px 6px;font-size:13px}
th{color:#6c7086;font-weight:500}tr+tr td{border-top:1px solid #151b27}
#sem{min-height:38px;color:#bac2de}.stale{color:#6c7086;font-style:italic}
#feed{height:240px;overflow:auto;font-size:12px}
.evt{padding:2px 0;border-bottom:1px solid #151b27}
.t-entity_entered{color:#a6e3a1}.t-entity_exited{color:#6c7086}
.t-zone_breach{color:#f38ba8}.t-zone_entered,.t-zone_exited{color:#89b4fa}
.t-semantic_note{color:#cba6f7}.t-activity_change{color:#f9e2af}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#a6e3a1;margin-right:6px}
.off{background:#f38ba8}
</style></head><body>
<header>
  <h1>◎ ARGUS</h1>
  <span class=pill><span id=conn class=dot></span><span id=src>—</span></span>
  <span class=pill>entities <b id=ecount>0</b></span>
  <span class=pill>activity <b id=act class=idle>idle</b></span>
  <span class=pill>events <b id=evtot>0</b></span>
</header>
<main>
  <div class=card><h2>Scene</h2><canvas id=cv width=854 height=480></canvas></div>
  <div>
    <div class=card><h2>What's happening</h2><div id=sem class=stale>waiting…</div></div>
    <div class=card style=margin-top:14px><h2>Entities</h2>
      <table><thead><tr><th>id</th><th>label</th><th>conf</th><th>zones</th><th>speed</th></tr></thead>
      <tbody id=ents></tbody></table></div>
    <div class=card style=margin-top:14px><h2>Event feed</h2><div id=feed></div></div>
  </div>
</main>
<script>
const $=id=>document.getElementById(id);
const cv=$('cv'),cx=cv.getContext('2d');let evtot=0;
const COL={person:'#a6e3a1',car:'#89b4fa',chair:'#f9e2af',default:'#cba6f7'};
function draw(s){
  const [W,H]=s.frame_size&&s.frame_size[0]?s.frame_size:[854,480];
  cv.width=W;cv.height=H;cx.clearRect(0,0,W,H);cx.fillStyle='#070a10';cx.fillRect(0,0,W,H);
  cx.lineWidth=2;cx.font='13px monospace';
  for(const e of s.entities||[]){const[x1,y1,x2,y2]=e.bbox;const c=COL[e.label]||COL.default;
    cx.strokeStyle=c;cx.strokeRect(x1,y1,x2-x1,y2-y1);
    cx.fillStyle=c;cx.fillText(`${e.label}#${e.track_id}`,x1+2,Math.max(12,y1-4));}
}
function renderState(s){
  $('src').textContent=s.source_id||'—';$('ecount').textContent=s.entity_count||0;
  const a=$('act');a.textContent=(s.activity&&s.activity.label)||'idle';a.className=(s.activity&&s.activity.label)||'idle';
  const sem=$('sem');if(s.semantic&&s.semantic.text){sem.textContent=s.semantic.text;sem.className=s.semantic.stale?'stale':'';}
  const tb=$('ents');tb.innerHTML='';
  for(const e of s.entities||[]){const tr=document.createElement('tr');
    tr.innerHTML=`<td>#${e.track_id}</td><td>${e.label}</td><td>${e.confidence}</td><td>${(e.zones||[]).join(',')||'—'}</td><td>${e.speed}</td>`;tb.appendChild(tr);}
  draw(s);
}
function addEvent(e){evtot++;$('evtot').textContent=evtot;
  const f=$('feed'),d=document.createElement('div');d.className='evt t-'+e.type;
  const t=new Date(e.ts_wall*1000).toLocaleTimeString();
  d.textContent=`${t}  ${e.message}`;f.prepend(d);
  while(f.childElementCount>200)f.removeChild(f.lastChild);
}
const es=new EventSource('/stream');
es.addEventListener('state',m=>renderState(JSON.parse(m.data)));
es.addEventListener('ev',m=>addEvent(JSON.parse(m.data)));
es.onopen=()=>$('conn').className='dot';
es.onerror=()=>$('conn').className='dot off';
</script></body></html>"""
