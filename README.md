Ghost Trail
Anonymous until it matters.

ASYNC'26 — Cybersecurity & Defense
![Project Status: Alpha](#project-status)
![Python 3.11+](#prerequisites)
![Node.js 20+](#prerequisites)
![FastAPI](#technology-stack)
![React](#technology-stack)
> \*\*Repository note:\*\* CI/CD, automated test-coverage, and code-quality badges should be connected to the repository once those workflows exist. The badges above identify the documented project/runtime status and are not claims of passing CI or coverage.
ASYNC'26 Repository Compliance
This README follows the ASYNC'26 Technical Guidelines structure: context and value proposition, architecture, reproducible installation, configuration, developer usage, QA, reliability/performance, security, governance, and license information. fileciteturn0file1L8-L43
Quick Links
Demo & Media
Architecture & System Design
Installation
Environment Variables
Usage & API Examples
Testing & QA
Performance & Maturity
Security Reporting
Troubleshooting
Contributing
License
Demo & Media
Demo
The repository should include a link to the official ASYNC'26 demonstration video once published:
Demo video: `TODO — add official demo URL`
Screenshots
Add high-resolution screenshots/GIFs to `assets/screenshots/` and link them here before technical review:
`TODO — Dashboard screenshot`
`TODO — Tracking / Re-ID screenshot`
`TODO — Alerts / Face Review screenshot`
`TODO — Environment / Live Room Scan screenshot`
`TODO — Investigator screenshot`
> These entries are intentionally marked TODO because the supplied README did not contain actual screenshot files or a published demo URL. No media is being represented as available when it has not been supplied.
Documentation & Design Links
API / Swagger: `TODO — add deployed or repository-local Swagger/OpenAPI URL`
Setup documentation: this README
Architecture: System Architecture
AI pipeline: How the AI Pipeline Works
Privacy/security design: Privacy & Security Design

Ghost Trail is an explainable, privacy-aware, multi-camera security intelligence platform designed for real-time perimeter monitoring, behavioral anomaly detection, cross-camera identity stitching, human-reviewed face verification, and investigator-assisted analysis.
The system is built around a simple principle:
> \*\*Detect broadly, identify conservatively, and explain every escalation.\*\*
Instead of performing facial recognition on everyone who appears on camera, Ghost Trail tracks people anonymously using body-based Re-ID and evaluates their behavior across the monitored environment. Face verification is introduced only when configured behavioral conditions justify escalation.
---
Table of Contents
Overview
Core Features
1. Multi-Camera AI Detection
2. Anonymous Person Tracking
3. Cross-Camera Identity Stitching
4. Explainable Behavior Risk Engine
5. Gated Face Recognition
6. Human Face Verification
7. Real-Time Alert System
8. Multi-Camera Tracking & Intelligence
9. Tactical Environment Map
10. Live Room Scan
11. Investigator Workbench
12. Learned Path Anomaly Detection
13. Privacy Ledger & Retention
14. Contextual Object Monitoring
15. Camera Management
16. Analytics & Data Export
17. Role-Based Access Control
18. Audit & Persistent Security Incidents
19. Live WebSocket Telemetry
20. Desktop / One-Click Windows Launch
How the AI Pipeline Works
Risk Model
Face Review Workflow
Room Scan Workflow
System Architecture
Technology Stack
Project Structure
Installation
Running Ghost Trail
Configuration
API Overview
Privacy & Security Design
Important Limitations
Troubleshooting
Team
---
Overview
Ghost Trail combines computer vision, multi-object tracking, person Re-ID, behavioral analytics, face verification, spatial visualization, and analyst tooling into a single command-center application.
Primary workflow
```text
Camera Feeds
     │
     ▼
YOLO Person / Object Detection
     │
     ▼
Per-Camera Tracking
(ByteTrack / tracker)
     │
     ▼
Anonymous Body Re-ID
(OSNet)
     │
     ▼
Cross-Camera Global Identity
     │
     ▼
Behavior \& Path Analysis
     │
     ├── Normal / Watch
     │
     └── Suspicious / High Risk
              │
              ▼
      Face Recognition Gate
              │
              ▼
      Human Face Verification
              │
              ▼
      Explainable Security Alert
              │
              ▼
      Investigation / Audit Trail
```
The React dashboard provides the operator interface while a FastAPI backend coordinates the AI pipeline, cameras, database, alerts, authentication, room scanning, privacy ledger, and investigator services.
---
Core Features
1. Multi-Camera AI Detection
Ghost Trail can process multiple surveillance feeds simultaneously.
Capabilities
Live camera streams
Person detection
Multi-object tracking
Camera-specific zones
Camera health/status information
Per-camera telemetry
Live FPS information
Detection overlays
Camera enable/disable controls
Add/remove camera channels
Camera-specific alerting
Cross-camera movement analysis
The system uses YOLO-based detection and maintains individual local tracks before creating a global identity across cameras.
---
2. Anonymous Person Tracking
People are initially treated as anonymous Guests rather than immediately being assigned a real-world identity.
Each person can receive a global Guest ID that persists across compatible camera observations.
Example
```text
CAM\_01
  └── Local Track 17
        │
        ▼
     Guest 42
        │
        ├── CAM\_02
        │      └── Local Track 8
        │
        └── CAM\_03
               └── Local Track 4
```
This allows the system to reason about movement and behavior without requiring immediate facial identification.
---
3. Cross-Camera Identity Stitching
Ghost Trail separates:
Local camera track IDs
Global Ghost Trail IDs
Registered identities
The identity stitcher can compare recent body and face embeddings and uses camera handoff timing to determine whether observations likely belong to the same global track.
Re-ID capabilities
OSNet body embeddings
Cross-camera handoff matching
Face-assisted stitching when available
Handoff grace period
Maximum handoff gap
Same-camera duplicate identity prevention
Registered identity matching
Anonymous Guest matching
The same global identity can be observed by multiple cameras at the same time while preventing two simultaneous local tracks in the same camera from incorrectly sharing one identity.
---
4. Explainable Behavior Risk Engine
Ghost Trail does not treat the presence of an unknown person as automatically suspicious.
Instead, behavior is converted into a configurable 0–100 risk score.
Current behavioral factors
Dwell time
Extended loitering
Repeated entry/re-entry
Reverse movement
Cross-camera movement
Restricted-zone entry
Off-hours activity
Learned path anomaly
Each factor contributes a bounded number of points.
The system also generates a human-readable explanation such as:
```text
Risk Score: 72
Tier: Suspicious

Factors:
- Dwell time (31s)
- Repeat passes (2)
- Cross-camera movement (2 zones)
```
This makes alerts easier for an operator to understand and investigate.
---
5. Gated Face Recognition
Face recognition is deliberately separated from normal detection.
The default workflow is:
```text
Person detected
     ↓
Anonymous tracking
     ↓
Behavior evaluated
     ↓
Suspicious behavior?
     ↓
YES
     ↓
Face recognition may be attempted
```
The face recognition stack uses InsightFace/ArcFace with ONNX Runtime.
This architecture reduces unnecessary biometric processing and keeps ordinary observations anonymous.
Face stack
InsightFace
ArcFace
ONNX Runtime
Configurable face similarity threshold
The application also performs a face-stack availability check and avoids silently claiming biometric functionality when the required models/dependencies are unavailable.
---
6. Human Face Verification
Automated face matching does not automatically become a final identity decision.
Flagged captures enter a human-review workflow.
Pending review
An analyst can:
Confirm Face
Promotes the Guest into the enrolled identity database
Saves the accepted face to the `Faces/` gallery
Marks the identity as verified
Resolves related active incidents
Creates a resolved audit event
Deny Face
Marks the identity as High Risk
Creates a persistent security incident
Keeps the review decision in SQLite
Makes the incident available in the Alerts/Security Incident views
Enrolled profiles
Verified profiles can be:
Viewed
Edited
Updated with name/badge/role/clearance/notes
Removed from enrollment
Re-enrolling/updating a profile can reset the face-review state to pending where appropriate.
---
7. Real-Time Alert System
Ghost Trail provides both visual and dashboard-level alerts.
Alert categories
Anomalous behavior
Watchlist match
Contextual object alert
Legacy unknown-person alert compatibility
Alert UX
Camera alerts can include:
Animated alert border
Color-coded overlay
Alert banner
Alert details
Alert priority
Alert cooldown/deduplication
Alert timestamps
Camera association
The dashboard also provides:
Live alert popovers
Emergency alert banner
Alert dismissal
Active/resolved status
Face review actions
Alert filtering
Audible notification support
---
8. Multi-Camera Tracking & Intelligence
The Tracking page provides a historical and analytical view of surveillance telemetry.
Available information
Total sightings
Authorized detections
Anonymous Guests
High Risk detections
Average confidence
Camera-level detection counts
Time-based activity
Individual sighting records
Camera filters
Type filters
Search by person/name/sighting ID
Export
Filtered tracking results can be exported as:
CSV
JSON
This makes the telemetry useful for later analysis and reporting.
---
9. Tactical Environment Map
The Environment section provides a spatial view of the monitored area.
The existing interface supports multiple visualization modes.
Radar Sweep
A tactical radar-style visualization for active camera/target information.
Blueprint
A schematic environment representation.
Live Room Scan
A camera-assisted relative environment reconstruction mode.
The tactical environment also provides a live target spatial roster with identity/risk information.
---
10. Live Room Scan
Live Room Scan allows an operator to use a browser camera to scan a physical room.
Workflow
```text
START SCAN
   ↓
Browser Camera Permission
   ↓
Continuous Frame Capture
   ↓
JPEG Frames → Backend
   ↓
Camera Motion Estimation
   ↓
Structural Line Detection
   ↓
YOLO Scene/Object Detection
   ↓
Relative 2D Environment
   ↓
Live Map + Telemetry
```
Live scan displays
Detected objects/persons
Structural lines
Coverage
Relative camera pose
Scanning progress/telemetry
Camera ownership protection
Room Scan uses an exclusive browser-camera session.
When scanning begins:
Local surveillance camera access is paused where required
The server tracks ownership of the camera session
Stale scan requests are rejected
When adding a person:
The scan camera is released
Biometric enrollment can use the camera
The operator can explicitly resume the scan afterward
Important limitation
Live Room Scan is a relative monocular 2D reconstruction.
It is not:
Metric 3D SLAM
A depth scan
A guaranteed-to-scale floor plan
A replacement for RGB-D/AR depth hardware
Camera drift can occur as the operator moves around the room.
---
11. Investigator Workbench
The Investigator page provides an analyst-facing investigation interface.
An operator can submit structured investigation queries such as:
```text
Investigate the most recent high-risk track.
```
The investigator can use structured telemetry to build an evidence-oriented response.
Investigator features
Investigation queries
Evidence summaries
Tool-use reporting
Investigation case files
Severity information
Structured telemetry analysis
Privacy ledger visibility
AI investigator modes
If `ANTHROPIC\_API\_KEY` is configured:
```text
Claude tool-use mode
```
Without the API key:
```text
Offline deterministic investigator mode
```
The investigator is deliberately restricted to structured telemetry and does not directly control biometric escalation.
---
12. Learned Path Anomaly Detection
Ghost Trail can learn normal camera-transition behavior from persisted sightings.
The graph anomaly component models patterns such as:
```text
Camera A → Camera B
Camera B → Camera C
Camera A → Camera C
```
It also considers dwell distributions and time buckets.
A deviation from the learned baseline becomes an additional bounded risk factor.
Example
```text
Expected:
CAM\_01 → CAM\_02 → CAM\_03

Observed:
CAM\_01 → CAM\_03

Result:
Learned Path Anomaly contributes to risk score
```
The anomaly score is explainable and integrated into the broader behavior-risk system.
---
13. Privacy Ledger & Retention
Ghost Trail includes a dedicated privacy layer.
Privacy features
Rotating pseudonymous aliases
Privacy event ledger
Face-escalation event logging
No face embeddings stored in the privacy ledger
No raw images stored in privacy events
Configurable telemetry retention
Configurable flagged-capture retention
Administrative purge functionality
The Investigator page exposes privacy metrics such as:
Total sightings
Face escalations
Anonymous rate
Privacy ledger events
Retention windows
Default retention
The supplied configuration currently uses:
```yaml
sighting\_retention\_hours: 24
flagged\_retention\_hours: 168
```
These values are configurable.
---
14. Contextual Object Monitoring
Ghost Trail can monitor objects in the environment without automatically declaring every detected object a threat.
The contextual-object engine tracks objects over time and evaluates context.
For example:
```text
Object detected
     ↓
Object remains stationary
     ↓
Person association evaluated
     ↓
Configured duration reached
     ↓
Contextual Object Alert
```
This design is intended to reduce false alarms caused by one-frame object detections.
---
15. Camera Management
Administrators can manage surveillance channels from the dashboard.
Camera controls
Add camera
Remove camera
Enable/disable camera
Configure camera name
Configure source
Assign camera zone
View camera status
View live stream
Focus camera
Fullscreen camera
Digital PTZ-style zoom controls
HUD/telemetry visibility
High-resolution snapshot
Camera configuration is stored in the project configuration and exposed through the backend API.
---
16. Analytics & Data Export
The dashboard provides operational analytics based on persisted sighting telemetry.
Analytics include
Timeline activity
Camera activity
Authorized detections
Unknown/anonymous detections
High Risk detections
Average matching confidence
Total sightings
Tracking data can be exported to:
```text
CSV
JSON
```
The system uses the persisted SQLite `sighting\_logs` table rather than inventing telemetry when the backend is unavailable.
---
17. Role-Based Access Control
Ghost Trail includes role-based permissions.
The primary roles are:
```text
viewer
analyst
admin
```
Viewer
Intended for read-only operational visibility.
Analyst
Can perform investigation and security-review actions such as:
Face review
Alert dismissal
Investigation queries
Analyst-level operations
Admin
Includes analyst capabilities plus administrative functions such as:
Camera management
Configuration changes
Privacy purge
Administrative settings
Exact authorization is enforced by the FastAPI backend.
---
18. Audit & Persistent Security Incidents
Important security decisions are persisted rather than existing only in the browser.
Examples include:
Face verification denied
Face verification accepted
Security incidents
Investigation case files
Privacy events
Review timestamps
Review notes
This means important operator decisions survive application restarts.
---
19. Live WebSocket Telemetry
The dashboard receives real-time events through a WebSocket connection.
Live events can include
Detection updates
Tracking updates
Alerts
System telemetry
Camera status changes
The frontend can therefore update without repeatedly reloading the entire page.
REST endpoints are used for persistent data and commands while WebSockets provide live event delivery.
---
20. Desktop / One-Click Windows Launch
The project includes Windows launch scripts for hackathon/demo use.
Recommended first launch
```text
RUN\_GHOST\_TRAIL.bat
```
This can:
Create/use the Python virtual environment
Install Python dependencies
Install dashboard dependencies
Build the React dashboard
Start the Ghost Trail backend/application
Open the local application
For subsequent launches:
```text
START\_GHOST\_TRAIL.bat
```
The application is served locally at:
```text
http://127.0.0.1:8765
```
---
How the AI Pipeline Works
Stage 1 — Detection
YOLO detects people and monitored objects in each camera frame.
```text
Frame
 ↓
YOLO
 ↓
Bounding boxes + classes + confidence
```
Stage 2 — Local Tracking
Detected people are assigned local track IDs.
```text
Camera 01
  Person → Track 17
  Person → Track 23
```
Stage 3 — Anonymous Re-ID
OSNet generates body embeddings to help recognize the same person across camera boundaries without immediately assigning a real-world identity.
```text
Track 17
 ↓
OSNet embedding
 ↓
Global Guest 42
```
Stage 4 — Behavioral Analysis
The global track accumulates behavioral evidence:
```text
Dwell
Re-entry
Zone changes
Reverse movement
Restricted-zone entry
Off-hours activity
Learned path anomaly
```
Stage 5 — Risk Decision
The evidence is converted into a 0–100 score.
```text
0 ─────────────────────────────── 100
      Watch    Suspicious   High Risk
       30          60           80
```
The exact thresholds are configurable.
Stage 6 — Face Escalation
Suspicious behavior can trigger the face-recognition gate.
The system can compare the captured face against the configured enrolled/watchlist identities.
Stage 7 — Human Review
Flagged identities can be reviewed by an authorized operator.
```text
Pending Review
      │
      ├── Confirm → Verified / Enrolled
      │
      └── Deny → High Risk Incident
```
Stage 8 — Investigation
Structured telemetry can be queried through the Investigator workbench.
---
Risk Model
The current default configuration uses the following conceptual weights:
Factor	Default maximum contribution
Restricted-zone entry	35
Dwell / loitering	30
Repeated entry	25
Cross-camera movement	20
Off-hours activity	15
Reverse movement	15
Learned path anomaly	Configurable
The total score is capped at 100.
Default tiers
Score	Tier	Meaning

0–29	Normal	No meaningful behavioral risk
30–59	Watch	Behavior worth observing
60–79	Suspicious	Escalation conditions may be met
80–100	High Risk	Highest behavioral risk tier
These values are configuration-driven and should be tuned for the deployment environment.
---
Face Review Workflow
```text
Anonymous Guest
      │
      ▼
Behavioral Escalation
      │
      ▼
Face Capture / Match
      │
      ▼
Flagged for Review
      │
      ├────────────────────┐
      ▼                    ▼
Confirm Face            Deny Face
      │                    │
      ▼                    ▼
Verified Identity      High Risk
      │                    │
      ▼                    ▼
Enrolled Database      Security Incident
      │                    │
      └──────────┬─────────┘
                 ▼
             Audit Trail
```
A flagged person is not automatically treated as a confirmed identity. Human review is an explicit step.
---
Room Scan Workflow
Open Environment.
Select Live Room Scan.
Click START SCAN.
Grant browser camera permission.
Move slowly around the room.
The browser sends JPEG frames to the backend.
The backend estimates relative motion and structural lines.
YOLO analyzes detected scene objects/persons.
The relative environment visualization updates.
Stop the scan when finished.
For the best demo result, move smoothly rather than making rapid camera movements.
---
System Architecture
```text
┌──────────────────────────────────────────────────────┐
│                 React Dashboard                      │
│                                                      │
│ Dashboard │ Tracking │ Alerts │ People │ Environment │
│ Investigator │ Settings                              │
└───────────────────────┬──────────────────────────────┘
                        │
                 REST / WebSocket
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│                 FastAPI Backend                      │
│                  Port 8765                           │
│                                                      │
│ Auth │ Cameras │ Streams │ Alerts │ Room Scan        │
│ Persons │ Tracking │ Investigator │ Privacy │ Config │
└───────────────┬──────────────────────┬───────────────┘
                │                      │
                ▼                      ▼
       ┌────────────────┐      ┌─────────────────┐
       │ AI Pipeline    │      │ SQLite Database │
       │                │      │                 │
       │ YOLO           │      │ sightings       │
       │ Tracker        │      │ identities      │
       │ OSNet Re-ID    │      │ incidents       │
       │ ArcFace        │      │ cases           │
       │ Behavior       │      │ privacy events  │
       │ Graph Anomaly  │      │ audit data      │
       └────────────────┘      └─────────────────┘
```
Production architecture
The project uses one FastAPI application as the backend source of truth.
The React dashboard is built into:
```text
dashboard/dist
```
and served by the application.
---
Technology Stack
Frontend
React
Vite
JavaScript / TypeScript
Tailwind CSS
Lucide React
Axios
Recharts
WebSocket client
Backend
Python
FastAPI
Uvicorn
OpenCV
SQLite
AI / Computer Vision
YOLO / Ultralytics
ByteTrack-compatible tracking
Torch
Torchvision
TorchReID
OSNet
InsightFace
ArcFace
ONNX Runtime
SciPy
Optional AI Investigator
Anthropic API
Offline deterministic fallback
Desktop / Packaging
PyWebView
PyStray
PyInstaller
Windows batch launchers
---
Project Structure
```text
Ghost\_Trail\_RoomScan\_Investigator\_Merged/
│
├── sentinel\_app.py
├── sentinel\_server.py
├── sentinel\_tracker.py
├── detector.py
├── tracker.py
├── identity\_manager.py
├── face\_recognizer.py
├── behavior\_analyzer.py
├── graph\_anomaly.py
├── object\_context.py
├── alert\_manager.py
├── investigator.py
├── agent\_tools.py
├── privacy.py
├── database.py
├── stream\_manager.py
├── config.yaml
├── requirements.txt
│
├── tracker.db
│
├── dashboard/
│   ├── package.json
│   ├── vite.config.js
│   ├── src/
│   │   ├── pages/
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── TrackingPage.jsx
│   │   │   ├── AlertsPage.jsx
│   │   │   ├── PersonsPage.jsx
│   │   │   ├── TacticalMapPage.jsx
│   │   │   ├── InvestigatorPage.jsx
│   │   │   └── SettingsPage.jsx
│   │   ├── components/
│   │   ├── services/
│   │   └── context/
│   └── dist/
│
├── assets/
│
├── Faces/
│
├── RUN\_GHOST\_TRAIL.bat
├── START\_GHOST\_TRAIL.bat
└── README.md
```
---
Installation
Requirements
Recommended environment:
Windows 10/11
Python 3.11+
Node.js 20.x+ and npm
Optional NVIDIA GPU with compatible CUDA/PyTorch setup
One or more camera sources
Recommended GPU: NVIDIA GPU with a compatible CUDA/PyTorch installation for accelerated inference. CPU execution may be possible but performance depends on the workload.
Runtime versions
Component	Required / Recommended	Purpose
Python	3.11+	Backend and AI pipeline
Node.js	20.x+	React/Vite dashboard
npm	Bundled with Node.js	Frontend dependencies
Windows	10/11 recommended	Primary documented launch environment
NVIDIA GPU	Optional	Accelerated AI inference
Python dependencies
Install using:
```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```
Frontend dependencies
```powershell
cd dashboard
npm install
```
Build the dashboard:
```powershell
npm run build
```
Return to the project root:
```powershell
cd ..
```
---
Running Ghost Trail
Easiest method
Double-click:
```text
RUN\_GHOST\_TRAIL.bat
```
The application should become available at:
```text
http://127.0.0.1:8765
```
Manual backend start
```powershell
python sentinel\_app.py
```
Do not start a separate production API server unless the project's architecture has specifically been changed to require it.
Development frontend
For frontend development:
```powershell
cd dashboard
npm run dev
```
The Vite development server proxies `/api` and WebSocket traffic to the Ghost Trail backend on port `8765`.
---
Configuration
Most operational behavior can be configured through:
```text
config.yaml
```
Important configuration groups include:
```yaml
behavior:
face\_recognition:
object\_monitoring:
reid:
graph\_anomaly:
privacy:
database:
cameras:
```
Behavior configuration
Examples:
```yaml
behavior:
  watch\_dwell\_sec: 8.0
  suspicious\_dwell\_sec: 20.0
  high\_risk\_dwell\_sec: 45.0
  score\_watch: 30
  score\_suspicious: 60
  score\_high: 80
```
Off-hours
```yaml
off\_hours\_start: 22
off\_hours\_end: 6
```
Restricted zones
```yaml
restricted\_zones:
  - "Zone C - Restricted"
  - "Zone C"
  - "Restricted"
```
Re-ID
Important controls include:
Body matching threshold
Cross-camera body threshold
Cross-camera face threshold
Guest face threshold
Registered face threshold
Handoff grace period
Maximum camera handoff gap
Re-ID interval
Re-ID model
Privacy
Retention can be configured for:
Sighting telemetry
Flagged review captures
Anonymous identity information
---
Environment Variables
The supplied project documentation references `ANTHROPIC\_API\_KEY` for the optional AI investigator. Other runtime configuration is primarily documented through `config.yaml`.
Variable	Description	Type	Default	Required
`ANTHROPIC\_API\_KEY`	Enables Claude tool-use mode for the optional investigator	String	Unset	No
`TODO: project-specific variable`	Add any deployment-specific secret/configuration variables used by the repository	String	Project-defined	If used
> \*\*Important:\*\* The supplied README does not provide a complete `.env` schema. Before technical review, replace the TODO row with every environment variable actually read by the codebase, including its type, default, and required/optional status. Do not put real secrets in the repository.
Usage & API Examples
Start the application
```powershell
# First launch
RUN\_GHOST\_TRAIL.bat

# Subsequent launch
START\_GHOST\_TRAIL.bat
```
The documented local application URL is:
```text
http://127.0.0.1:8765
```
Manual backend launch
```powershell
python sentinel\_app.py
```
Frontend development
```powershell
cd dashboard
npm install
npm run dev
```
Example authentication request
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "<configured-user>",
  "password": "<configured-password>"
}
```
> The exact authentication request schema is not specified in the supplied README. Treat the payload above as a usage placeholder and verify it against the backend/OpenAPI schema before publishing.
Example telemetry endpoint
```http
GET /api/sightings
```
Example investigator request
```http
POST /api/investigator/query
Content-Type: application/json
```
> The exact request body is implementation-specific and was not provided in the supplied README. Add a verified request/response example from the running API before technical review.
API Overview
The FastAPI backend exposes `/api/\*` endpoints.
Authentication
```text
POST /api/auth/login
GET  /api/auth/me
```
Live telemetry
```text
WS /api/ws
```
Cameras
```text
GET    /api/cameras
POST   /api/cameras
POST   /api/cameras/{camera\_id}/toggle
DELETE /api/cameras/{camera\_id}
GET    /api/stream/{camera\_id}
```
Environment / Room Scan
```text
POST /api/camera/session/start
POST /api/camera/session/stop
GET  /api/camera/session/status

POST /api/environment/scan/reset
POST /api/environment/scan/frame
```
Persons
```text
GET    /api/persons
POST   /api/persons
PUT    /api/persons/{person\_id}
DELETE /api/persons/{person\_id}
POST   /api/persons/{person\_id}/unenroll
POST   /api/persons/{person\_id}/face-review
```
Flagged face review
```text
GET    /api/persons/flagged
POST   /api/persons/flagged/{flag\_id}/confirm
POST   /api/persons/flagged/{flag\_id}/deny
DELETE /api/persons/flagged/{flag\_id}
```
Alerts
```text
GET    /api/alerts
POST   /api/alerts/{alert\_id}/dismiss
DELETE /api/alerts
```
Tracking / analytics
```text
GET /api/sightings
GET /api/dashboard
GET /api/stats
GET /api/behavior-rules
```
Investigator
```text
GET  /api/investigator/cases
POST /api/investigator/query
```
Privacy
```text
GET  /api/privacy/ledger
POST /api/privacy/purge
```
Configuration
```text
GET  /api/config
POST /api/config
```
Audit
```text
GET /api/audit
```
---
Privacy & Security Design
Ghost Trail includes several layers intended to reduce unnecessary exposure of biometric and surveillance data.
Anonymous by default
Ordinary detections are represented through anonymous/global Guest IDs and body Re-ID rather than immediately identifying the person.
Biometric escalation gate
Face recognition is gated by behavioral escalation rather than being the default operation for every detection.
Human review
A face match/review can be explicitly confirmed or denied by an authorized operator.
Persistent audit trail
Important decisions are recorded in SQLite.
Privacy ledger
Privacy-relevant events are recorded separately from biometric embeddings/images.
Retention controls
Old telemetry and temporary flagged captures can be purged according to configured retention periods.
Role-based permissions
Sensitive actions require appropriate roles.
Camera ownership
Room Scan and biometric enrollment use controlled exclusive camera sessions to prevent multiple consumers from fighting over the same webcam.
---
Important Limitations
Room Scan is not 3D SLAM
The current implementation is a relative monocular 2D reconstruction.
For true spatial reconstruction, a future implementation could integrate:
ARCore
ARKit
WebXR depth
RGB-D cameras
A dedicated SLAM engine
Camera drift
Relative room reconstruction can drift as the camera moves.
Re-ID is probabilistic
Body and face embeddings are similarity-based signals, not absolute identity proof.
Thresholds should be tuned for the actual environment.
Face recognition requires its model stack
InsightFace and ONNX Runtime must be installed correctly.
Run:
```powershell
python check\_face\_stack.py
```
before relying on biometric functionality.
Hardware affects performance
GPU acceleration can substantially improve real-time detection, Re-ID, and face-processing performance.
For supported configurations, CUDA devices can be selected in `config.yaml`.
Demo thresholds
The default behavioral thresholds are intentionally short enough to demonstrate escalation during a live presentation.
For a real deployment, thresholds should be calibrated using representative operational data.
---
Testing & QA
The supplied README documents operational checks such as:
```powershell
python check\_face\_stack.py
python -m pip install -r requirements.txt
```
For repository-level technical review, the following QA commands should be implemented/documented when their corresponding tooling exists:
```powershell
# Unit tests
pytest

# Integration tests
pytest tests/integration

# Linting
ruff check .

# Formatting check
ruff format --check .

# Static/type analysis
mypy .
```
> These commands are the expected QA interface for the repository documentation, but the supplied project README does not establish that all of these tools/tests currently exist. Do not treat a command as passing until the corresponding workflow is added and verified.
Recommended QA coverage
Backend unit tests
AI pipeline integration tests
Authentication/RBAC tests
Camera-session ownership tests
Room Scan tests
Re-ID matching tests
Alert deduplication tests
Privacy-retention/purge tests
API contract tests
Frontend build validation
Performance & Maturity
Current maturity
Alpha / Hackathon Prototype
The supplied project is explicitly described as a prototype/hackathon implementation. It should not be represented as production-ready without the security, privacy, accuracy, load, and validation work listed in the repository limitations. fileciteturn0file0L1574-L1588
Performance
The current README documents live FPS telemetry but does not provide reproducible benchmark measurements for latency, throughput, GPU memory, CPU usage, or multi-camera scaling. fileciteturn0file0L112-L123
Before technical review, populate this table from measured runs:
Metric	Measurement	Test conditions
Detection FPS	`TODO`	Camera resolution/model/GPU
End-to-end latency	`TODO` ms	Input → alert
Cameras processed concurrently	`TODO`	Hardware/configuration
GPU memory	`TODO` MB	Model stack
CPU utilization	`TODO` %	Test workload
Room Scan frame rate	`TODO` FPS	Browser/backend setup
No benchmark values are invented here because the supplied README does not contain measured performance results.

Dashboard does not load
Rebuild the frontend:
```powershell
cd dashboard
npm install
npm run build
cd ..
python sentinel\_app.py
```
Camera feed does not appear
Check:
Camera source configuration.
Camera permissions.
Authentication/token availability.
Whether another application is using the camera.
Whether Room Scan currently owns the browser camera.
Room Scan cannot start
Make sure:
Browser camera permission is granted.
No conflicting webcam application is using the device.
A previous scan session has been stopped.
The backend is running.
Face recognition is unavailable
Run:
```powershell
python check\_face\_stack.py
```
Then reinstall dependencies if necessary:
```powershell
python -m pip install -r requirements.txt
```
Cross-camera stitching creates unexpected Guests
Review:
Body Re-ID threshold
Face threshold
Handoff grace period
Maximum camera handoff gap
Camera placement
Lighting
Camera overlap
Lower thresholds can increase matching tolerance but may also increase false merges.
Tracking database issues
The project includes database utilities such as:
```text
check\_db.py
clean\_db.py
```
Use them carefully because database cleanup can remove persisted telemetry and identity information.
---
Demo Flow
For a competition or live demonstration, the following sequence showcases the major capabilities:
1. Command Center
Open the Dashboard and show:
Live cameras
People tracked
Active alerts
System status
Behavior risk
2. Cross-Camera Tracking
Move through two camera zones and demonstrate the same anonymous Guest continuing across cameras.
3. Behavioral Escalation
Remain in a configured zone long enough for the behavior score to increase.
Show the explainable factors behind the score.
4. Face Review
Trigger the face-verification workflow and demonstrate:
```text
Flagged for Review
       ↓
Confirm Face / Deny Face
```
5. Alerts
Open the Alerts page and demonstrate:
Active alert
Camera source
Risk information
Human-review controls
Alert dismissal
6. Tracking Intelligence
Open Tracking to show historical telemetry and export it to CSV/JSON.
7. Environment
Switch between:
```text
Radar Sweep
Blueprint
Live Room Scan
```
8. Investigator
Run:
```text
Investigate the most recent high-risk track.
```
Show the evidence summary, tools used, case files, and privacy metrics.
9. Settings
Demonstrate that behavior weights, thresholds, camera channels, Re-ID settings, and retention settings can be configured.
---
Design Philosophy
Ghost Trail is built around four principles:
1. Detect broadly
Computer vision should observe the environment without requiring immediate identity attribution.
2. Identify conservatively
Biometric processing is introduced only when the configured behavioral logic warrants escalation.
3. Explain every alert
Operators should see the evidence and behavioral factors that contributed to a risk decision.
4. Keep humans in the loop
Sensitive identity decisions can be reviewed and explicitly confirmed or denied by authorized personnel.
---
Security Reporting
Ghost Trail is a cybersecurity/defense-oriented prototype and should not expose security-sensitive vulnerability details through public issue tracking.
Private vulnerability reporting: `TODO — add the team's official security contact or private disclosure mechanism`
When reporting a vulnerability, include:
Affected component/version
Reproduction steps
Expected vs. actual behavior
Security impact
Relevant logs or minimal proof of concept
Whether the issue involves authentication, authorization, biometric data, privacy, or data retention
Do not include real credentials, biometric data, personal data, or production secrets in reports.
Contributing
This repository is currently maintained as an ASYNC'26 hackathon project.
Before contributing:
Create or work from an appropriate feature/fix branch.
Keep changes scoped to the relevant component.
Do not commit credentials, API keys, camera secrets, biometric data, databases containing personal data, or generated runtime artifacts.
Run the applicable build and QA checks before submitting changes.
Update the README when changing setup, API behavior, configuration, architecture, or security controls.
Code style
Python: follow PEP 8; use the repository formatter/linter once configured.
React/JavaScript: follow the repository ESLint/formatter configuration once configured.
Prefer clear, descriptive names and small focused functions.
Document security-sensitive behavior and configuration changes.
License
License: TODO — add the project's actual open-source license before publication.
The supplied repository documentation does not declare a specific license, so no license has been invented here. If the project is intended to be open source, add the selected license file (for example, `LICENSE`) and update this section accordingly.
ASYNC'26 README Compliance Checklist
Requirement	README coverage
Elevator pitch / value proposition	✅
Badges / status indicators	✅
Screenshots / demo media	⚠️ Add actual media/URL
Architecture diagrams	✅
End-to-end execution flow	✅
Documentation links	⚠️ Add Swagger/OpenAPI URL
Runtime versions	✅ Python 3.11+, Node 20.x+
Step-by-step installation	✅
Environment-variable matrix	⚠️ Complete project-specific variables
Usage/API snippets	⚠️ Verify exact request schemas
Testing / QA commands	⚠️ Add/verify actual test tooling
Benchmarks	⚠️ Add measured results
Maturity status	✅ Alpha / Hackathon Prototype
Troubleshooting / limitations	✅
Security reporting	⚠️ Add private contact/mechanism
Contribution / code style	✅
Open-source license	⚠️ Add actual license
Team
PowerPuff Girls
ASYNC 2.0 — Cybersecurity & Defense Track
Garv Bhat — Lead
1MS25CS058
1MS25ME069
1MS25IS093
---
License / Project Status
This repository represents the Ghost Trail prototype/hackathon implementation.
Before production deployment, the system should undergo additional:
Security testing
Privacy/legal review
Bias and accuracy evaluation
Camera/environment calibration
Threshold calibration
Load testing
Model validation
Access-control testing
Data-retention validation