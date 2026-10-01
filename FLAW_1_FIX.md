# Ghost Trail — Flaw #1 Fix

## What changed

- Synthetic WebSocket telemetry no longer starts automatically when the backend is unavailable.
- CameraFeed no longer displays a synthetic surveillance scene when a real camera stream fails.
- Simulation is now controlled explicitly by `dashboard/.env`:
  - `VITE_DEMO_MODE=false` → real backend/camera only.
  - `VITE_DEMO_MODE=true` → intentional synthetic presentation mode.
- Simulation mode is visibly labeled `DEMO / SIMULATION`.
- Offline cameras show `CAMERA OFFLINE` / `REAL FEED REQUIRED` instead of fake detections.
- Removed hard-coded fallback FPS/recording indicators from the camera HUD.

## Test

```bash
cd dashboard
npm install
npm run build
```

For real mode, keep `VITE_DEMO_MODE=false`. If the FastAPI backend is unavailable, the UI should show disconnected/offline state rather than inventing telemetry.

For presentation-only simulation, set `VITE_DEMO_MODE=true` and restart Vite. The UI will explicitly identify the synthetic feed as simulation.
