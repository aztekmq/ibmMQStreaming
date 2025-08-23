# -*- coding: utf-8 -*-
# =============================================================================
# File      : webapp_fastapi.py
# Purpose   : FastAPI + SSE dashboard for IBM MQ Streaming Queue demos.
# Author    : rob lee
# Version   : 1.1.0
# License   : MIT (SPDX-License-Identifier: MIT)
# Standards : PEP 8, PEP 257; Google-style docstrings; RFC 2119 keywords used.
# Dependencies:
#   - fastapi, uvicorn, python-dotenv, pymqi (IBM MQ Client required on host)
# =============================================================================
"""
FastAPI dashboard that consumes *stream queues* and publishes live metrics via
Server-Sent Events (SSE). The HTML page uses a minimalist Canvas 2D chart to
visualize recent rates and payload samples without external JS libraries.

Run:
    pip install -r requirements.txt
    cp .env.example .env
    python webapp_fastapi.py
    # open http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
import pymqi  # requires IBM MQ Client on host

__author__ = "rob lee"
__license__ = "MIT"
__version__ = "1.1.0"


def load_cfg() -> Dict[str, str]:
    """Load IBM MQ connection configuration from .env.

    Returns:
        Dict[str, str]: Connection parameters: host, port, qmgr, channel, user,
        password, and optional ccdt.
    """
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    return {
        "host": os.getenv("MQ_HOST", "127.0.0.1"),
        "port": int(os.getenv("MQ_PORT", "1414")),
        "qmgr": os.getenv("MQ_QMGR", "QM1"),
        "channel": os.getenv("MQ_CHANNEL", "DEV.APP.SVRCONN"),
        "user": os.getenv("MQ_USER", "app"),
        "password": os.getenv("MQ_PASSWORD", "passw0rd"),
        "ccdt": os.getenv("MQ_CCDT", ""),
    }


def connect(cfg: Dict[str, str]) -> pymqi.QueueManager:
    """Create a TCP client connection using pymqi.

    Args:
        cfg: Connection parameters (host/port/qmgr/channel/user/password/ccdt).

    Returns:
        pymqi.QueueManager: An established queue manager connection.

    Raises:
        pymqi.MQMIError: If the connection fails.
    """
    cd = pymqi.CD()
    cd.ChannelName = cfg["channel"].encode()
    cd.ConnectionName = f'{cfg["host"]}({cfg["port"]})'.encode()
    cd.ChannelType = pymqi.CMQC.MQCHT_CLNTCONN
    cd.TransportType = pymqi.CMQC.MQXPT_TCP

    if cfg["ccdt"]:
        # Use CCDT if provided: split into MQCHLLIB (dir) and MQCHLTAB (file)
        os.environ["MQCHLLIB"], os.environ["MQCHLTAB"] = os.path.split(cfg["ccdt"])

    # No TLS in dev; add key repos to pymqi.SCO for TLS in production
    sco = pymqi.SCO()
    qmgr = pymqi.QueueManager(None)
    qmgr.connect_with_options(cfg["qmgr"], cd=cd, sco=sco, user=cfg["user"], password=cfg["password"])
    return qmgr


class StreamReader(threading.Thread):
    """Background consumer that drains a stream queue into a ring buffer & metrics.

    The reader blocks on GET with a short wait interval and updates:
      - `total`: total messages consumed since start
      - `timestamps`: recent message timestamps for rate computation
      - `recent`: last N decoded payloads for UI display

    Attributes:
        qmgr: Queue manager connection.
        queue_name: Stream queue name to consume from.
        ring_size: Max number of recent payloads to retain for the UI.
    """

    def __init__(self, qmgr: pymqi.QueueManager, queue_name: str, ring_size: int = 50) -> None:
        super().__init__(daemon=True)
        self.qmgr = qmgr
        self.queue_name = queue_name
        self.q = pymqi.Queue(qmgr, queue_name)
        self.recent: List[dict] = []
        self.total = 0
        self.timestamps: List[float] = []
        self.ring_size = ring_size
        self.stop_flag = threading.Event()

    def run(self) -> None:
        """Consume messages until stopped; update rolling stats."""
        gmo = pymqi.GMO()
        gmo.Options = (
            pymqi.CMQC.MQGMO_NO_SYNCPOINT
            | pymqi.CMQC.MQGMO_WAIT
            | pymqi.CMQC.MQGMO_CONVERT
        )
        gmo.WaitInterval = 500  # 0.5s
        md = pymqi.MD()

        while not self.stop_flag.is_set():
            try:
                data = self.q.get(None, md, gmo)
                self.total += 1
                self.timestamps.append(time.time())
                try:
                    obj = json.loads(data.decode("utf-8"))
                except Exception:
                    # Fall back to hex preview if not JSON
                    obj = {"raw": data[:128].hex()}
                self.recent.append(obj)
                self.recent = self.recent[-self.ring_size:]
                # Trim timestamps older than 30s for smoothed rate
                cutoff = time.time() - 30
                self.timestamps = [t for t in self.timestamps if t >= cutoff]
            except pymqi.MQMIError as e:
                if e.comp == pymqi.CMQC.MQCC_FAILED and e.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                    # No message available within wait interval
                    continue
                # Back off briefly on other transient conditions
                time.sleep(0.1)

    def stats(self) -> Dict[str, object]:
        """Compute a snapshot of rate/total and return recent payloads.

        Returns:
            Dict[str, object]: Keys `rate` (float msgs/sec, last 10s),
            `total` (int), and `recent` (list of last ~10 payloads).
        """
        now = time.time()
        rate = len([t for t in self.timestamps if t >= now - 10]) / 10.0
        return {"total": self.total, "rate": rate, "recent": self.recent[-10:]}


app = FastAPI(title="IBM MQ Streaming Demos (FastAPI + SSE)")
readers: Dict[str, StreamReader] = {}

# Minimal static HTML with Vanilla JS and Canvas 2D charts.
HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>IBM MQ Streaming Demos — FastAPI + SSE</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body { font-family: system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; margin: 20px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.05); }
    .metric { font-size: 28px; font-weight: 700; }
    canvas { width: 100%; height: 120px; border-radius: 8px; background: #fafafa; }
    pre { white-space: pre-wrap; word-break: break-word; background: #f7f7f7; padding: 8px; border-radius: 8px; }
    small { color: #666; }
  </style>
</head>
<body>
  <h1>IBM MQ Streaming Queue Demos — FastAPI + SSE</h1>
  <p>Live updates via <strong>Server-Sent Events</strong>. Start your producers, then watch the charts move.</p>
  <div class="grid">
    <div class="card">
      <h2>Financial Transaction Audit <small>(AUDIT.TXN)</small></h2>
      <div class="metric" id="m_audit">0.0 /s</div>
      <small id="t_audit">total: 0</small>
      <canvas id="c_audit"></canvas>
      <pre id="r_audit"></pre>
    </div>
    <div class="card">
      <h2>E-commerce Promotions Feed <small>(PROMO.FEED)</small></h2>
      <div class="metric" id="m_promo">0.0 /s</div>
      <small id="t_promo">total: 0</small>
      <canvas id="c_promo"></canvas>
      <pre id="r_promo"></pre>
    </div>
    <div class="card">
      <h2>Retail Central Sync <small>(CENTRAL.SYNC)</small></h2>
      <div class="metric" id="m_sync">0.0 /s</div>
      <small id="t_sync">total: 0</small>
      <canvas id="c_sync"></canvas>
      <pre id="r_sync"></pre>
    </div>
  </div>

<script>
function makeChart(canvasId) {
  const el = document.getElementById(canvasId);
  const ctx = el.getContext('2d');
  const data = new Array(60).fill(0); // last 60 seconds
  function draw() {
    const W = el.width = el.clientWidth;
    const H = el.height = 120;
    ctx.clearRect(0,0,W,H);
    const max = Math.max(1, ...data);
    ctx.beginPath();
    const dx = W / (data.length - 1);
    for (let i = 0; i < data.length; i++) {
      const x = i * dx;
      const y = H - (data[i] / max) * (H - 10) - 5;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.lineWidth = 2; ctx.strokeStyle = '#0b61a4'; ctx.stroke();
  }
  return { push: (val) => { data.push(val); data.shift(); draw(); }, draw };
}
const charts = { audit: makeChart('c_audit'), promo: makeChart('c_promo'), sync: makeChart('c_sync') };
charts.audit.draw(); charts.promo.draw(); charts.sync.draw();

const evt = new EventSource('/sse');
evt.onmessage = (e) => {
  const s = JSON.parse(e.data);
  document.getElementById('m_audit').textContent = (s.AUDIT_TXN.rate).toFixed(1) + ' /s';
  document.getElementById('t_audit').textContent = 'total: ' + s.AUDIT_TXN.total;
  document.getElementById('m_promo').textContent = (s.PROMO_FEED.rate).toFixed(1) + ' /s';
  document.getElementById('t_promo').textContent = 'total: ' + s.PROMO_FEED.total;
  document.getElementById('m_sync').textContent  = (s.CENTRAL_SYNC.rate).toFixed(1) + ' /s';
  document.getElementById('t_sync').textContent  = 'total: ' + s.CENTRAL_SYNC.total;

  charts.audit.push(s.AUDIT_TXN.rate);
  charts.promo.push(s.PROMO_FEED.rate);
  charts.sync.push(s.CENTRAL_SYNC.rate);

  document.getElementById('r_audit').textContent = s.AUDIT_TXN.recent.map(x => JSON.stringify(x)).join('\\n');
  document.getElementById('r_promo').textContent = s.PROMO_FEED.recent.map(x => JSON.stringify(x)).join('\\n');
  document.getElementById('r_sync').textContent  = s.CENTRAL_SYNC.recent.map(x => JSON.stringify(x)).join('\\n');
};
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """Serve the dashboard HTML."""
    return HTML


def snapshot() -> Dict[str, dict]:
    """Collect a snapshot of current metrics for all three queues.

    Returns:
        Dict[str, dict]: Metrics for stream queues AUDIT.TXN, PROMO.FEED, CENTRAL.SYNC.
    """
    def _safe(name: str) -> dict:
        return readers[name].stats() if name in readers else {"rate": 0.0, "total": 0, "recent": []}

    return {
        "AUDIT_TXN": _safe("AUDIT.TXN"),
        "PROMO_FEED": _safe("PROMO.FEED"),
        "CENTRAL_SYNC": _safe("CENTRAL.SYNC"),
    }


@app.get("/api/metrics", response_class=JSONResponse)
def metrics() -> Dict[str, dict]:
    """Polling fallback; returns the same payload as SSE frames."""
    return snapshot()


@app.get("/sse")
def sse() -> StreamingResponse:
    """Server-Sent Events: emit a JSON snapshot once per second.

    Returns:
        StreamingResponse: A response with media type `text/event-stream`.
    """
    def gen():
        while True:
            data = json.dumps(snapshot())
            yield f"data: {data}\n\n"
            time.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


def bootstrap_readers() -> None:
    """Initialize MQ connection and start three stream readers.

    MUST be invoked before serving SSE to ensure data starts flowing.
    """
    cfg = load_cfg()
    qmgr = connect(cfg)
    for qn in ["AUDIT.TXN", "PROMO.FEED", "CENTRAL.SYNC"]:
        r = StreamReader(qmgr, qn)
        r.start()
        readers[qn] = r


# Initialize on import so the app is ready when uvicorn starts
bootstrap_readers()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)