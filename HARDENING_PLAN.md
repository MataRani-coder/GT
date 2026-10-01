# Ghost Trail — Surveillance & Image-Stitching Hardening

## Architecture change: one physical webcam, two exclusive modes

The primary local webcam is now treated as an exclusive resource.

- **SURVEILLANCE mode:** OpenCV owns the webcam and the normal detection/Re-ID pipeline runs.
- **SCAN / ENROLL mode:** the backend releases local webcam handles before the browser calls `getUserMedia()`.
- **RETURN:** browser tracks are stopped, then the backend reacquires the webcam.
- Network/RTSP cameras remain available during the browser session.

Endpoints:
- `POST /api/camera/session/start`
- `POST /api/camera/session/stop`
- `GET /api/camera/session/status`

## Image stitching improvements

1. ORB feature extraction with a larger feature budget.
2. KNN descriptor matching with ratio filtering.
3. RANSAC homography estimation instead of raw translation.
4. Inlier-ratio gating to reject weak matches.
5. Projective-warp sanity checks to reject unstable homographies.
6. Incremental panorama accumulation with a bounded canvas.
7. Feathered overlap blending to reduce hard seams.
8. Live panorama preview in the room-scan UI.
9. Existing pose/structure telemetry is retained as a separate relative spatial layer.

This remains a monocular 2D panorama/relative map, not metric 3D SLAM.

## Identity stitching improvements

1. Guest and registered identities use rolling multi-frame galleries instead of a single best historical template.
2. Similarity uses the mean of the strongest few gallery matches, reducing sensitivity to one accidental high-similarity frame.
3. Face/body evidence is combined when both are available.
4. Ambiguity-margin rejection prevents a forced match when two identities are too close in score.
5. Gallery history is expanded from 5 to 20 normalized embeddings.
6. Same-camera collision protection remains active, while cross-camera handoff remains allowed.
7. Local tracker IDs remain ephemeral; the global identity is the continuity key.

## Critical flaws identified

| # | Flaw | Impact | Resolution |
|---|---|---|---|
| 1 | Browser room scan competed with OpenCV for the same webcam | Scan could fail or show camera-unavailable | Exclusive camera session added |
| 2 | Room scanner accumulated a pose trace but did not actually stitch images | Map could drift and lacked visual reconstruction | Incremental ORB/RANSAC panorama added |
| 3 | Re-ID relied too heavily on one template/best historical match | Pose/lighting/clothing changes caused ID churn | Rolling multi-frame galleries |
| 4 | Close candidate scores could still force an identity decision | False merges between similar guests | Ambiguity-margin rejection |
| 5 | Local tracker IDs are inherently unstable | Occlusion/reacquisition can create a new local ID | Global identity handoff path strengthened |
| 6 | Cross-camera handoff used a short timing window | Normal transitions could create a new Guest | Handoff window increased and made gallery-based |
| 7 | Weak feature matches could contribute to stitching drift | Panorama corruption after blur/low texture | RANSAC inlier and homography gates |
| 8 | Simple overwrite-style panorama composition can create seams | Reduced visual reliability | Feathered overlap blending |
| 9 | One face/body score could dominate a decision | Camera/pose changes can destabilize matching | Face/body fusion + top-k gallery similarity |
| 10 | Camera acquisition failures were not coordinated between UI and backend | Generic webcam failure was difficult to diagnose | Session API and explicit failure handling |
| 11 | Scan mode had no stitched visual result | Operator could not verify coverage | Live panorama preview |
| 12 | Monocular reconstruction can be mistaken for metric 3D geometry | Incorrect spatial interpretation | Relative-2D labeling retained and documented |

## Recommended next-stage upgrades

- Calibrate each camera and store lens intrinsics/distortion parameters.
- Add camera-specific Re-ID score calibration instead of one global threshold.
- Add an explicit `unknown/ambiguous` state instead of forcing every detection into a Guest identity.
- Use a dedicated SLAM/AR depth pipeline for metric 3D room reconstruction.
- Benchmark cross-camera Re-ID with precision, recall, F1, false-merge rate and ID-switch rate.
- Log model versions, thresholds, camera IDs and benchmark dataset version with every evaluation report.
