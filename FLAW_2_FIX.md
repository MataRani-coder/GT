# Flaw #2 Fix — Real FastAPI WebSocket

## Problem
The React dashboard expected `/api/ws`, but the FastAPI server only had a WebSocket manager and no actual `/api/ws` endpoint. The frontend therefore disconnected and could not receive real-time backend events.

## Fixed
- Added a real FastAPI `@app.websocket("/api/ws")` endpoint.
- Sends an initial `init` message when a dashboard connects.
- Accepts the frontend heartbeat `ping` and responds with `pong`.
- Added a server-side telemetry task that broadcasts real status, FPS, cameras, and active alerts once per second.
- Added real detection broadcasts for newly observed tracks.
- Added queued alert delivery from `SHARED.pending_ws_alerts`.
- Cleans up disconnected WebSocket clients.
- Starts and stops the telemetry task with the FastAPI application lifecycle.

## Verification
- `python -m py_compile sentinel_server.py` — PASS
- FastAPI `/api/status` test — PASS
- WebSocket `/api/ws` connection — PASS
- Initial `init` message — PASS
- `ping` / `pong` heartbeat — PASS
- Real telemetry message — PASS
- Queued alert delivery — PASS

## Important
There is still no synthetic fallback in production mode. If the backend is unavailable, the dashboard must remain visibly offline. Demo simulation remains controlled separately by `VITE_DEMO_MODE=true`.
