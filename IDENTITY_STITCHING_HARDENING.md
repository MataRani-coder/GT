# Ghost Trail — Identity & Image Stitching Hardening

## Objective
Keep a person's global identity stable when the local tracker changes IDs, the person crosses cameras, or the visual quality of individual frames changes.

## Implemented changes

### 1. Exclusive camera ownership
- Surveillance OpenCV streams pause before browser Room Scan or biometric enrollment starts.
- Browser webcam sessions are never allowed to fall back to a fake success response when the backend cannot release the device.
- Scan frames are rejected unless an exclusive camera session is active.
- Capture reads/releases are serialized so an in-flight OpenCV read cannot race a browser `getUserMedia()` acquisition.

### 2. Room image stitching
- ORB feature extraction on consecutive scan frames.
- KNN descriptor matching with Lowe ratio filtering.
- RANSAC homography estimation.
- Minimum inlier ratio and projective-warp sanity gates.
- Incremental panorama accumulation on a bounded canvas.
- Overlap-aware composition and crop-to-content.
- Live panorama preview returned with scan telemetry.
- The result is explicitly treated as a relative monocular panorama, not metric 3D SLAM.

### 3. Guest identity stitching
- Global identity is separated from camera-local tracker IDs.
- Each identity keeps a multi-view gallery rather than one template.
- Gallery comparison now gives the strongest compatible anchor more weight while still requiring supporting templates.
- Face evidence is weighted above body Re-ID evidence when available.
- Ambiguous matches are rejected rather than forcing a wrong identity.
- Cross-camera handoff has a wider temporal window than same-camera continuity.
- Same-camera tracker-ID churn can use a short, conservative bounding-box overlap fallback when appearance embeddings temporarily disappear.
- Same-camera collision protection remains active so two simultaneous people cannot silently collapse into one global identity.

## Critical flaws and solutions

| Flaw | Failure mode | Solution |
|---|---|---|
| Webcam contention | Surveillance and Room Scan fight for one camera | Exclusive camera session + stream pause/resume |
| Fake session success | UI can acquire camera while backend still owns it | No-success fallback for session start |
| Scan endpoint usable without session | Parallel consumers can bypass ownership | Server-side 409 session guard |
| In-flight OpenCV read race | Release can overlap a frame read | Capture lock around read/release |
| Pose trace mistaken for reconstruction | Map looks precise but is only relative | Real feature-based panorama + explicit relative-scale disclaimer |
| Weak image matches | Bad frames corrupt panorama | Ratio test + RANSAC + inlier/warp gates |
| Panorama drift | Consecutive homographies accumulate error | Bounded incremental composition and rejection of weak transforms |
| Single-template Re-ID | Pose/lighting change causes missed match | Rolling multi-view gallery |
| Best-frame-only scoring | One lucky frame dominates identity decision | Top-k gallery score with weighted anchor/support |
| Local tracker ID churn | Same person becomes Guest_1, Guest_2, etc. | Global identity layer + temporal gallery stitching |
| Ambiguous identity match | Similar-looking guests get merged | Best-vs-second margin rejection |
| Short embedding dropout | New tracker ID created during temporary feature loss | Conservative same-camera bbox continuity fallback |

## Recommended next production-level upgrades

1. Replace monocular panorama reconstruction with visual-inertial SLAM or RGB-D/depth-assisted mapping when metric geometry is required.
2. Calibrate every camera and store camera intrinsics/extrinsics for true multi-camera spatial fusion.
3. Add a persistent identity quality score and expire stale guest galleries separately from registered identities.
4. Add a hard audit trail for every identity merge/split decision: camera, local track, timestamp, face score, body score, margin, and reason.
5. Evaluate stitching on a fixed test set containing occlusion, lighting changes, side profiles, hats/masks, and camera handoffs.
6. Add automated regression tests for false merges and false splits before every hackathon demo build.
