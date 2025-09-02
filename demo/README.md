# IBM MQ Streaming Demo

## Vision
In the spirit of pragmatic innovation, this demo shows how a classic message queue can drive real‑time video streaming. On the left, a broadcast studio picks a program by spinning a digital wheel. On the right, a living room TV renders whatever the studio sends. IBM MQ sits in the middle, guaranteeing delivery and letting us measure the journey.

## Components
1. **Web UI** – A single page showing the studio and the living room.
   - Wheel of Fortune spinner with multiple categories.
   - Incoming‑message indicator while the video selection is in flight.
   - Metrics panel on the living room side displaying timestamps and latency.
2. **FastAPI Server (`server.py`)** – Serves the UI, accepts spin results, posts them to MQ, and broadcasts MQ deliveries over WebSockets.
3. **IBM MQ** – Queue manager and queue (`VIDEO.STREAM`) transporting video selections.

## Prerequisites
- Python 3.10+
- IBM MQ queue manager reachable from this machine.
- The MQ Python bindings (`pymqi`).

Install the Python dependencies:
```bash
cd demo
pip install -r requirements.txt
```

## Configuration
Edit `server.py` if your MQ host, channel, port, or queue names differ. The default values target a developer queue manager:
```python
MQ_HOST = 'localhost'
MQ_PORT = '1414'
MQ_CHANNEL = 'DEV.APP.SVRCONN'
MQ_QMGR = 'QM1'
MQ_QUEUE = 'VIDEO.STREAM'
```

## Running the Demo
1. **Start the server**
   ```bash
   uvicorn demo.server:app --reload
   ```
2. **Open the browser**
   Navigate to [`http://localhost:8000`](http://localhost:8000).
3. **Spin the wheel**
   - The spinner chooses a slice at random.
   - The selection (category and YouTube URL) posts to IBM MQ.
   - An orange indicator flashes in the studio to show the message in transit.
4. **Watch the TV**
   - The server listens to MQ and pushes messages to the browser via WebSockets.
   - When the message arrives, the indicator stops and the TV loads the selected YouTube video.
   - The metrics panel updates with sent and received timestamps and calculated latency.

## Optional Enhancements Implemented
- **Incoming message animation** – Visual cue that a message is traveling.
- **MQ metrics panel** – Real‑time view of when the message left and when it arrived.
- **Categorized wheel slices** – Each slice carries both a category and a video link.

## Notes
This demo focuses on clarity rather than security or production hardening. It assumes an IBM MQ environment that allows client connections and that the YouTube videos are available in your region.
