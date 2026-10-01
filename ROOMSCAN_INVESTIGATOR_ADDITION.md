# Ghost Trail — Room Scan + Investigator Addition

This build is based on the current merged project. Only these additions were made:

1. Restored Project A's Live Room Scan UI inside the existing Tactical Map as a third view mode.
   - Existing Radar Sweep and Blueprint modes are preserved.
   - Existing camera, identity stitching, behavior/risk, alerts, and map logic were not replaced.
   - Uses the existing `/api/environment/scan/*` endpoints already present in the backend.
2. Exposed the already-existing Investigator page in the top navigation.
3. Preserved the camera stream authentication fix that makes the working camera feed load.

No backend architecture, identity-stitching logic, behavior engine, alert logic, or existing working camera backend was replaced.
