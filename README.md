# ibmMQStreaming
This project stands up **one IBM MQ queue manager in Docker** (using your provided `build_mq_qmgrs.sh`), then configures **Streaming Queues** for **three** demos. 

awesome — below are **fully documented** files, ready to paste into the same folder layout. I added clear module/file headers (author, version, SPDX license), Google-style docstrings, typed signatures, usage notes, and inline comments while preserving behavior.

---

### `mq-streaming-demos/README.md`

````markdown
# IBM MQ Streaming Queue Demos (3 use cases)

**Author:** rob lee • **License:** MIT • **Version:** 1.1.0

This project stands up **one IBM MQ queue manager in Docker** (using your provided `build_mq_qmgrs.sh`),
then configures **Streaming Queues** for **three** demos. Two Python processes run **outside** the MQ container:

- `python/producer.py` — a CLI traffic generator (puts messages to source queues)
- `python/webapp_fastapi.py` — a FastAPI dashboard that **consumes ONLY the stream copies** and visualizes live rates via Server-Sent Events (SSE)

## Demos implemented
1. **Real-Time Financial Transaction Auditing**  
   Source: `APP.TXN.IN`  →  Stream: `AUDIT.TXN`

2. **E-Commerce Order Processing Fork**  
   Source: `ORDERS.IN`    →  Stream: `PROMO.FEED`

3. **Retail Inventory Real-Time Sync**  
   Source: `INV.UPDATES`  →  Stream: `CENTRAL.SYNC`

All three use **`STREAMQ(...) STRMQOS(ATLEAST_ONCE)`** so original apps are unaffected while the dashboard reads duplicates.

---

## Prerequisites (host / outside container)
- Python **3.9+**
- IBM MQ **Client** libraries installed (required by `pymqi`)
- Python deps: `pip install -r python/requirements.txt`

> Prefer not to install the MQ Client locally? You MAY containerize the two Python apps (still separate from the MQ container).

---

## Step 1 — Start MQ container (use your script)
```bash
chmod +x ./build_mq_qmgrs.sh
./build_mq_qmgrs.sh 1
````

Assumes **QM1** on **1414** with channel `DEV.APP.SVRCONN` and user `app` (password often `passw0rd` in dev).

---

## Step 2 — Configure Streaming Queues on the running QM

```bash
chmod +x scripts/configure_mq.sh
./scripts/configure_mq.sh --qmgr QM1 --container qm1
```

This creates (or replaces) 6 queues and enables streaming for the 3 use cases. Verify:

```bash
docker exec -it qm1 runmqsc QM1 <<<'DISPLAY QLOCAL(*) STREAMQ STRMQOS'
```

---

## Step 3 — Set your client connection env

```bash
cp python/.env.example python/.env
# adjust host/port/qmgr/channel/user/password if your script used different values
```

---

## Step 4 — Run the FastAPI SSE dashboard (outside the MQ container)

```bash
pip install -r python/requirements.txt
python python/webapp_fastapi.py
# open http://127.0.0.1:8000
```

The dashboard consumes these **stream queues**:

* `AUDIT.TXN`
* `PROMO.FEED`
* `CENTRAL.SYNC`

---

## Step 5 — Generate traffic

```bash
# 1) Financial TXN audit
python python/producer.py --use-case audit --rate 10

# 2) E-commerce order fork
python python/producer.py --use-case ecom --rate 5

# 3) Retail inventory sync
python python/producer.py --use-case retail --rate 3
```

---

## MQSC used

See `mqsc/10-streaming-demo.mqsc`.

## Troubleshooting

* **pymqi import error** → install IBM MQ Client and ensure library paths are set (LD\_LIBRARY\_PATH/DYLD\_LIBRARY\_PATH/PATH).
* **2035 NOT\_AUTHORIZED** → use `DEV.APP.SVRCONN`, `app` user, and your dev password.
* **Objects missing** → re-run Step 2 to apply MQSC.

````

---

### `mq-streaming-demos/mqsc/10-streaming-demo.mqsc`
```mqsc
* -----------------------------------------------------------------------------
* File      : 10-streaming-demo.mqsc
* Purpose   : Define source queues and their Streaming Queues for 3 demos.
* Author    : rob lee
* Version   : 1.1.0
* License   : MIT (SPDX-License-Identifier: MIT)
* Notes     : Uses STRMQOS(ATLEAST_ONCE) to duplicate messages for downstream
*             consumers without changing the original producer/consumer code.
* -----------------------------------------------------------------------------

* Use case 1: Real-Time Financial Transaction Auditing
DEFINE QLOCAL('APP.TXN.IN')     REPLACE DEFPSIST(YES) MAXDEPTH(50000) MAXMSGL(1048576) STREAMQ('AUDIT.TXN') STRMQOS(ATLEAST_ONCE)
DEFINE QLOCAL('AUDIT.TXN')      REPLACE DEFPSIST(YES) MAXDEPTH(100000) MAXMSGL(1048576)

* Use case 2: E-Commerce Order Processing Fork
DEFINE QLOCAL('ORDERS.IN')      REPLACE DEFPSIST(YES) MAXDEPTH(50000) MAXMSGL(1048576) STREAMQ('PROMO.FEED') STRMQOS(ATLEAST_ONCE)
DEFINE QLOCAL('PROMO.FEED')     REPLACE DEFPSIST(YES) MAXDEPTH(100000) MAXMSGL(1048576)

* Use case 3: Retail Inventory Real-Time Sync
DEFINE QLOCAL('INV.UPDATES')    REPLACE DEFPSIST(YES) MAXDEPTH(50000) MAXMSGL(1048576) STREAMQ('CENTRAL.SYNC') STRMQOS(ATLEAST_ONCE)
DEFINE QLOCAL('CENTRAL.SYNC')   REPLACE DEFPSIST(YES) MAXDEPTH(100000) MAXMSGL(1048576)

* Optional hygiene (uncomment and adapt):
* ALTER QMGR MONQ(MEDIUM) MONCHL(MEDIUM)
* DEFINE QLOCAL('QM1.DLQ') REPLACE
* ALTER QMGR DEADQ('QM1.DLQ')

END
````

---

### `mq-streaming-demos/scripts/configure_mq.sh`

```bash
#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# File      : configure_mq.sh
# Purpose   : Apply demo MQSC into a running IBM MQ container using runmqsc.
# Author    : rob lee
# Version   : 1.1.0
# License   : MIT (SPDX-License-Identifier: MIT)
# Requirements:
#   - Docker CLI available and user permitted to exec in target container.
#   - A running MQ container exposing runmqsc for the target queue manager.
# Usage:
#   ./configure_mq.sh [--qmgr QM1] [--container qm1] [--mqsc /path/to/file.mqsc]
# Exit Codes:
#   0  Success
#   2  MQSC file not found
#   1  Other error
# Notes:
#   - Script is idempotent when MQSC uses REPLACE.
#   - Follows POSIX shell best practices (set -euo pipefail).
# -----------------------------------------------------------------------------
set -euo pipefail

QMGR="QM1"
CONTAINER="qm1"
MQSC_FILE="$(dirname "$0")/../mqsc/10-streaming-demo.mqsc"

usage() {
  echo "Usage: $0 [--qmgr QM1] [--container qm1] [--mqsc /path/to/file.mqsc]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --qmgr) QMGR="$2"; shift 2;;
    --container) CONTAINER="$2"; shift 2;;
    --mqsc) MQSC_FILE="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

if [[ ! -f "$MQSC_FILE" ]]; then
  echo "MQSC file not found: $MQSC_FILE" >&2
  exit 2
fi

echo "Applying MQSC to $QMGR on container $CONTAINER ..."
docker exec -i "$CONTAINER" bash -lc "runmqsc $QMGR" < "$MQSC_FILE"

echo "Done."
echo "Verify with:"
echo "  docker exec -it $CONTAINER runmqsc $QMGR <<<'DISPLAY QLOCAL(*) STREAMQ STRMQOS'"
```

---

### `mq-streaming-demos/python/requirements.txt`

```text
# -----------------------------------------------------------------------------
# Dependencies for producer and FastAPI SSE web dashboard
# Maintainer: rob lee • License: MIT
# -----------------------------------------------------------------------------
pymqi==1.13.1
python-dotenv==1.0.1
fastapi==0.112.2
uvicorn==0.30.6
```

---

### `mq-streaming-demos/python/.env.example`

```ini
# -----------------------------------------------------------------------------
# IBM MQ Client Connection Settings (Example)
# Author  : rob lee
# License : MIT
# Notes   : Copy to ".env" and adjust as required. These values MUST match the
#           queue manager and channel created by your Docker script.
# -----------------------------------------------------------------------------
MQ_HOST=127.0.0.1
MQ_PORT=1414
MQ_QMGR=QM1
MQ_CHANNEL=DEV.APP.SVRCONN
MQ_USER=app
MQ_PASSWORD=passw0rd

# Optional CCDT path (leave empty to use HOST/PORT/CHANNEL).
# Example (Linux):
# MQ_CCDT=/home/user/ccdt/AMQCLCHL.TAB
MQ_CCDT=
```

---

### `mq-streaming-demos/python/producer.py`

```python
# -*- coding: utf-8 -*-
# =============================================================================
# File      : producer.py
# Purpose   : Generate sample messages for 3 Streaming Queue demos.
# Author    : rob lee
# Version   : 1.1.0
# License   : MIT (SPDX-License-Identifier: MIT)
# Standards : PEP 8, PEP 257; Google-style docstrings; RFC 2119 keywords used.
# Dependencies:
#   - pymqi (IBM MQ Client required on host)
#   - python-dotenv
# =============================================================================
"""
CLI producer for IBM MQ Streaming Queue demos.

This utility connects to a queue manager over TCP and continuously PUTs messages
to one of three *source* queues. Streaming Queues (configured separately via
MQSC) duplicate the traffic to corresponding *stream* queues for dashboards or
downstream analytics.

Usage:
    python producer.py --use-case {audit|ecom|retail} --rate 5

Environment:
    Values are loaded from `.env` in the same directory (see .env.example).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import time
from datetime import datetime
from typing import Callable, Dict, Tuple

from dotenv import load_dotenv
import pymqi  # requires IBM MQ Client on host

__author__ = "rob lee"
__license__ = "MIT"
__version__ = "1.1.0"


def load_cfg() -> Dict[str, str]:
    """Load IBM MQ connection configuration from .env.

    Returns:
        Dict[str, str]: A dictionary containing host, port, qmgr, channel,
        user, password, and optional ccdt values.
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
        pymqi.MQMIError: If connection fails (e.g., channel auth).
    """
    cd = pymqi.CD()
    cd.ChannelName = cfg["channel"].encode()
    cd.ConnectionName = f'{cfg["host"]}({cfg["port"]})'.encode()
    cd.ChannelType = pymqi.CMQC.MQCHT_CLNTCONN
    cd.TransportType = pymqi.CMQC.MQXPT_TCP

    if cfg["ccdt"]:
        # CCDT path split into MQCHLLIB (dir) / MQCHLTAB (file)
        os.environ["MQCHLLIB"], os.environ["MQCHLTAB"] = os.path.split(cfg["ccdt"])

    # No TLS for dev; in production, configure pymqi.SCO with key repos
    sco = pymqi.SCO()
    qmgr = pymqi.QueueManager(None)
    qmgr.connect_with_options(cfg["qmgr"], cd=cd, sco=sco, user=cfg["user"], password=cfg["password"])
    return qmgr


def rand_id(n: int = 8) -> str:
    """Generate a random alphanumeric identifier.

    Args:
        n: Desired length of the identifier.

    Returns:
        str: Random ID of length n.
    """
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def txn_message() -> Dict[str, object]:
    """Construct a synthetic transaction message."""
    return {
        "type": "txn",
        "txn_id": rand_id(),
        "account": f"ACCT-{random.randint(10000, 99999)}",
        "amount": round(random.uniform(-500.0, 500.0), 2),
        "currency": "USD",
        "ts": datetime.utcnow().isoformat() + "Z",
        "merchant": random.choice(["AMAZON", "UBER", "STARBUCKS", "WALMART"]),
    }


def order_message() -> Dict[str, object]:
    """Construct a synthetic e-commerce order message."""
    items = random.randint(1, 4)
    return {
        "type": "order",
        "order_id": rand_id(),
        "customer_id": f"CUST-{random.randint(1000, 9999)}",
        "items": items,
        "total": round(random.uniform(10.0, 300.0), 2),
        "ts": datetime.utcnow().isoformat() + "Z",
        "promo_opt_in": random.choice([True, False]),
    }


def inventory_message() -> Dict[str, object]:
    """Construct a synthetic inventory update message."""
    return {
        "type": "inventory",
        "sku": f"SKU-{random.randint(10000, 99999)}",
        "delta": random.randint(-5, 10),
        "store": random.choice(["DAL01", "AUS02", "NYC03", "SFO04"]),
        "ts": datetime.utcnow().isoformat() + "Z",
    }


USE_CASES: Dict[str, Tuple[str, Callable[[], Dict[str, object]]]] = {
    "audit": ("APP.TXN.IN", txn_message),
    "ecom": ("ORDERS.IN", order_message),
    "retail": ("INV.UPDATES", inventory_message),
}


def put_loop(qmgr: pymqi.QueueManager, queue_name: str, rate: float) -> None:
    """Continuously PUT messages to a queue at an approximate rate.

    Args:
        qmgr: Connected queue manager handle.
        queue_name: Target *source* queue name.
        rate: Approximate messages per second (MUST be > 0 for intended effect).

    Notes:
        - Uses NO_SYNCPOINT for performance (at-least-once semantics).
        - Streaming Queue duplication is handled by the queue attributes (MQSC).
    """
    q = pymqi.Queue(qmgr, queue_name)
    try:
        interval = 1.0 / max(rate, 0.01)
        while True:
            # Build message based on selected queue
            if queue_name == "APP.TXN.IN":
                msg = txn_message()
            elif queue_name == "ORDERS.IN":
                msg = order_message()
            else:
                msg = inventory_message()

            data = json.dumps(msg).encode("utf-8")
            md = pymqi.MD()
            pmo = pymqi.PMO(Options=pymqi.CMQC.MQPMO_NO_SYNCPOINT)
            q.put(data, md, pmo)
            print(f"Put -> {queue_name}: {msg}")
            time.sleep(interval)
    finally:
        q.close()


def main() -> None:
    """CLI entry point parsing arguments and starting the generator."""
    ap = argparse.ArgumentParser(description="IBM MQ Streaming Demos Producer (pymqi)")
    ap.add_argument("--use-case", choices=USE_CASES.keys(), required=True, help="Which demo stream to drive")
    ap.add_argument("--rate", type=float, default=5.0, help="Messages per second (approx)")
    args = ap.parse_args()

    cfg = load_cfg()
    queue_name, _ = USE_CASES[args.use_case]
    qmgr = connect(cfg)

    try:
        put_loop(qmgr, queue_name, args.rate)
    except KeyboardInterrupt:
        pass
    finally:
        qmgr.disconnect()


if __name__ == "__main__":
    main()
```

---

### `mq-streaming-demos/python/webapp_fastapi.py`

```python
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
```

--
