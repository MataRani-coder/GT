# Setup launcher fix

## Root cause

`setup_and_run.bat` was starting `sentinel_server.py` directly. That module defines the FastAPI application and `run_server()` function, but does not invoke `run_server()` when executed as a script. The process therefore exited immediately and port 8765 had nothing listening, producing `ERR_CONNECTION_REFUSED`.

## Fix

The launcher now starts `sentinel_app.py`, which is the actual application entry point. It:

1. prepares the dashboard build,
2. starts FastAPI,
3. starts the AI tracker,
4. waits for `/api/status` to become reachable,
5. opens the browser,
6. keeps the application alive.

No camera or synthetic-data behavior was changed by this fix.
