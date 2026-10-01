# Flaw #3 — Single Backend Fix

## Problem

The dashboard previously had a hard-coded external API dependency while the local FastAPI server was also running. That created two possible sources of truth.

## Fix

- REST client uses relative `/api` URLs.
- WebSocket client uses the current browser host at `/api/ws`.
- Vite proxies `/api` and WebSocket traffic to `127.0.0.1:8765` during development.
- FastAPI serves the built React dashboard and all REST/WebSocket endpoints in production.
- Removed the legacy `api/index.py` serverless API and `vercel.json` configuration so there is no second backend in the project.
- Demo fallback remains available only through explicit `VITE_DEMO_MODE=true`.

## Result

```text
React Dashboard
      |
      +---- /api/* ----> FastAPI :8765
      |
      +---- /api/ws ---> FastAPI :8765
                            |
                            +--> AI pipeline
                            +--> database
                            +--> cameras
```
