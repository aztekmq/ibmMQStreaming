"""FastAPI application demonstrating IBM MQ streaming with a spinner UI."""

import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pymqi

# ---------------------------------------------------------------------------
# MQ configuration (adjust to your environment)
# ---------------------------------------------------------------------------
MQ_HOST = 'localhost'
MQ_PORT = '1414'
MQ_CHANNEL = 'DEV.APP.SVRCONN'
MQ_QMGR = 'QM1'
MQ_QUEUE = 'VIDEO.STREAM'

# Data model for spin selections ------------------------------------------------
class SpinSelection(BaseModel):
    category: str
    url: str

# FastAPI setup -----------------------------------------------------------------
app = FastAPI(title="IBM MQ Streaming Demo")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Connected websocket clients
clients: set[WebSocket] = set()

# Helper functions --------------------------------------------------------------

def mq_put(selection: SpinSelection) -> None:
    """Send the selected video to IBM MQ as a JSON message."""
    message = {
        "category": selection.category,
        "url": selection.url,
        "sent_at": time.time(),
    }
    qmgr = None
    try:
        qmgr = pymqi.connect(MQ_QMGR, MQ_CHANNEL, MQ_HOST, MQ_PORT)
        queue = pymqi.Queue(qmgr, MQ_QUEUE)
        queue.put(json.dumps(message))
    finally:
        if qmgr is not None:
            qmgr.disconnect()

async def broadcast(payload: dict) -> None:
    """Send payload to all connected websocket clients."""
    dead_clients = []
    for ws in clients:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead_clients.append(ws)
    for ws in dead_clients:
        clients.remove(ws)

async def mq_listener() -> None:
    """Background task: poll MQ and broadcast incoming messages."""
    while True:
        qmgr = None
        try:
            qmgr = pymqi.connect(MQ_QMGR, MQ_CHANNEL, MQ_HOST, MQ_PORT)
            queue = pymqi.Queue(qmgr, MQ_QUEUE)
            while True:
                try:
                    raw = queue.get(waitInterval=5000)  # wait up to 5 seconds
                except pymqi.MQMIError as err:
                    if err.comp == pymqi.CMQC.MQCC_FAILED and err.reason == pymqi.CMQC.MQRC_NO_MSG_AVAILABLE:
                        await asyncio.sleep(1)
                        continue
                    raise
                data = json.loads(raw)
                received_at = time.time()
                latency = received_at - data.get("sent_at", received_at)
                payload = {
                    "category": data["category"],
                    "url": data["url"],
                    "sent_at": data.get("sent_at"),
                    "received_at": received_at,
                    "latency": latency,
                }
                await broadcast(payload)
        except Exception:
            await asyncio.sleep(1)
        finally:
            if qmgr is not None:
                qmgr.disconnect()

# FastAPI routes ----------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    asyncio.create_task(mq_listener())

@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    return html

@app.post("/spin")
async def spin(selection: SpinSelection) -> dict:
    mq_put(selection)
    return {"status": "queued"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection open
    except WebSocketDisconnect:
        clients.remove(websocket)
