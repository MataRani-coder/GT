# Ghost Trail — Advanced Investigator / Learned Anomaly / Privacy Layer

## Implemented

### 1. Agentic investigator
- `agent_tools.py` exposes structured, read-only investigation tools.
- `investigator.py` uses Claude tool-use when `ANTHROPIC_API_KEY` is configured.
- Without a key, the same tool layer runs in deterministic offline mode.
- The agent never receives raw video, face embeddings, passwords, or biometric templates.
- `request_face_escalation` creates a case proposal with `awaiting_human_approval`; it does not execute face recognition.
- High-risk behavioral alerts automatically create structured case files.
- Dashboard: `/investigator` for analyst/admin roles.

### 2. Learned path anomaly model
- `graph_anomaly.py` learns camera-to-camera transitions by time bucket.
- Scores rare transitions with smoothed transition probability.
- Learns dwell-duration statistics and adds an outlier component.
- Warm-starts from persisted sighting telemetry on tracker startup.
- Its score is bounded and added as an explainable factor to the existing behavior score.
- Local face-gating remains independent from the learned model.

### 4. Privacy by design
- `privacy.py` creates rotating daily pseudonymous aliases using HMAC.
- Face escalations are recorded in a privacy ledger without embeddings or images.
- Sightings and flagged captures have configurable retention windows.
- Expired sighting rows and flagged images are purged.
- Dashboard exposes an anonymity-rate metric and recent privacy events.
- Admins can trigger a retention purge.

## Configuration

`config.yaml` contains:

```yaml
graph_anomaly:
  bucket_minutes: 60
  smoothing: 1.0
  warmup_observations: 8
  training_rows: 20000
privacy:
  sighting_retention_hours: 24
  flagged_retention_hours: 168
```

`behavior.graph_weight` controls how much learned anomaly contributes to the
0–100 explainable risk score.

## Claude setup

Copy `.env.example` to `.env` and set:

```text
ANTHROPIC_API_KEY=...
GHOST_TRAIL_CLAUDE_MODEL=claude-sonnet-4-5
```

If the key is absent, the application still runs with offline investigation
logic. The UI labels the mode accordingly.

## Verification

- `python -m py_compile *.py` — PASS
- `python test_behavior_score.py` — PASS
- `python test_auth.py` — PASS
- Graph anomaly + privacy + offline investigator smoke test — PASS
- React production build could not be executed in the working environment
  because dashboard dependencies were not installed successfully; run
  `cd dashboard && npm install && npm run build` before deployment.
