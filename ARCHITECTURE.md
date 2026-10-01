# Ghost Trail — Single Backend Architecture

Ghost Trail now uses **one FastAPI application** as the source of truth for the dashboard.

## Production

```text
Browser / React Dashboard
        |
        | REST: /api/*
        | WebSocket: /api/ws
        v
sentinel_server.py :8765
        |
        +--> SentinelTracker / AI pipeline
        +--> SQLite / sightings / identities / alerts
        +--> Camera streams
        +--> React static build (dashboard/dist)
```

There is no separate Vercel/serverless API in the production project.

## Development

Vite runs on port 3000 and proxies both `/api` REST requests and `/api/ws` WebSocket traffic to `http://127.0.0.1:8765`.

The browser therefore always uses the same relative endpoints:

- `GET/POST/... /api/...`
- `WS /api/ws`

## Demo mode

`VITE_DEMO_MODE=true` enables the explicitly labeled synthetic simulator for presentations. It does **not** create a second backend. Production mode (`false`) always reports backend failures instead of inventing live-looking data.

## Advanced intelligence layer

```text
Structured telemetry
       |
       +--> Learned Graph Anomaly ----+
       |                              |
       +--> Explainable Behavior -----+--> Risk / Alert
       |                              |
       +--> Privacy Ledger            +--> Case File
                                      |
                              Analyst Investigator
                                      |
                               Claude tool-use (optional)
                                      |
                              Human approval required
                              for biometric escalation
```

The LLM layer is isolated from raw video and biometric embeddings. Tool
responses contain structured telemetry, risk factors, timestamps and camera
paths only.
