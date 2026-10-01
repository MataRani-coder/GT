# Ghost Trail — Live Room Scan

The Environment Map now has a **Live Room Scan** mode.

## What it does
1. Requests the browser camera.
2. Captures frames continuously while the user pans around a room.
3. Sends JPEG frames to `POST /api/environment/scan/frame`.
4. Uses OpenCV to estimate relative camera motion and structural lines.
5. Uses YOLO to detect scene objects/persons from the scan frames.
6. Builds a relative 2D virtual environment and updates telemetry in real time.

## Important limitation
This is a **relative monocular 2D reconstruction**, not a metric 3D SLAM/depth scan. The UI explicitly labels the map as relative and not-to-scale. It can drift as the camera moves.

For a true 3D room model, the next upgrade should use a depth-capable camera/AR stack (for example ARCore/ARKit/WebXR depth or a dedicated RGB-D camera) and a SLAM engine.

## Run
Use the existing Ghost Trail launcher. The dashboard source is automatically rebuilt when the launcher detects source changes.

On the Environment Map:
- Select **Live Room Scan**
- Click **START SCAN**
- Allow camera permission
- Move slowly around the room
- Watch detections, structure lines, coverage and relative camera pose update live

The older Radar/Blueprint modes remain available for comparison/demo use.

## Camera ownership and person enrollment

Room Scan now runs as an exclusive browser-camera session. Starting a scan first pauses local OpenCV surveillance cameras. The **ADD PERSON** action releases the scan camera before opening biometric enrollment, preventing two consumers from fighting over the webcam. If the operator was scanning, the UI offers an explicit **RESUME SCAN** action after enrollment.

The server also rejects `/api/environment/scan/frame` unless the exclusive session is active, so a stale browser cannot silently feed frames while surveillance owns the device.
