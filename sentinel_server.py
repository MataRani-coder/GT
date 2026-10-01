"""
sentinel_server.py
==================
Internal FastAPI server embedded inside sentinel.exe.
- Serves the built React dashboard (static files from dashboard/dist/)
- Provides REST endpoints for camera info, persons, alerts, settings
- Streams live MJPEG camera frames via /api/stream/<camera_id>
- Broadcasts real-time detections/alerts over WebSocket /api/ws
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import cv2
import numpy as np
import uvicorn
import yaml
import subprocess
import shutil
import hashlib
import hmac
import secrets
import datetime as _dt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, Form, UploadFile, Depends, HTTPException, Request, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from detector import YoloDetector


# ──────────────────────────────────────────────────────────────────────────────
# Helpers to resolve bundled asset paths (works both in .py and PyInstaller .exe)
# ──────────────────────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    """Return the base directory of the bundled executable or the script directory."""
    if getattr(sys, "frozen", False):
        # Running inside PyInstaller bundle
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


BASE_DIR = _base_dir()
STATIC_DIR = BASE_DIR / "dashboard" / "dist"

def _safe_gallery_stem(name: str) -> str:
    """Canonical filename stem used for enrolled face images."""
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("._")
    return stem or "person"

CONFIG_PATH = BASE_DIR / "config.yaml"


# ──────────────────────────────────────────────────────────────────────────────
# Shared state (written by tracker thread, read by API)
# ──────────────────────────────────────────────────────────────────────────────

class _SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        # Latest rendered frame per camera_id  (numpy BGR)
        self.frames: Dict[str, np.ndarray] = {}
        # Active alerts list (dicts)
        self.alerts: List[Dict[str, Any]] = []
        # Detection telemetry: {camera_id: {track_id: {name, bbox, conf}}}
        self.detections: Dict[str, Dict[int, Dict[str, Any]]] = {}
        # System status
        self.status: str = "starting"   # starting | running | stopped | error
        self.fps: float = 0.0
        self.camera_ids: List[str] = []
        # Live capture diagnostics populated by StreamManager.
        self.camera_status: Dict[str, Dict[str, Any]] = {}
        # Log of recent events for frontend alerts page
        self.alert_log: List[Dict[str, Any]] = []
        # Face recognition health: never imply biometric capability when the model is unavailable.
        self.face_recognition_available: bool = False
        self.face_recognition_status: str = "not_initialized"
        self.face_recognition_error: Optional[str] = None
        self.face_recognition_model: Optional[str] = None
        
        # Queue for WebSocket to broadcast instantly
        self.pending_ws_alerts: List[Dict[str, Any]] = []
        
        # Daily unknown detection counter — resets each day
        import datetime as _dt
        self.today_unknown_count: int = 0
        self._today_date: str = _dt.date.today().isoformat()

    def push_frame(self, camera_id: str, frame: np.ndarray) -> None:
        with self.lock:
            self.frames[camera_id] = frame

    def push_detections(self, camera_id: str, detections: Dict[int, Dict[str, Any]]) -> None:
        with self.lock:
            self.detections[camera_id] = detections

    def _check_daily_reset(self) -> None:
        """Reset daily counters and alert logs when a new day starts."""
        import datetime as _dt
        today = _dt.date.today().isoformat()
        if today != self._today_date:
            print(f"[SHARED] New day detected ({self._today_date} → {today}) — resetting daily stats")
            self._today_date = today
            self.today_unknown_count = 0
            self.alerts.clear()
            self.alert_log.clear()

    def push_alert(self, alert: Dict[str, Any]) -> None:
        with self.lock:
            self._check_daily_reset()
            # Increment counter for unknown person alerts
            if alert.get("type") == "unknown_person":
                self.today_unknown_count += 1
            self.alerts.append(alert)
            # Add to historical log too
            self.alert_log.insert(0, alert)
            self.pending_ws_alerts.append(alert)
            if len(self.alert_log) > 200:
                self.alert_log = self.alert_log[:200]

    def expire_alerts(self) -> None:
        now = time.time()
        with self.lock:
            self._check_daily_reset()
            self.alerts = [a for a in self.alerts if now - a.get("timestamp", 0) < a.get("duration_sec", 30.0)]

    def get_frame(self, camera_id: str) -> Optional[np.ndarray]:
        with self.lock:
            return self.frames.get(camera_id)


SHARED = _SharedState()

# ──────────────────────────────────────────────────────────────────────────────
# Live room/environment scanner
# ──────────────────────────────────────────────────────────────────────────────

class _EnvironmentScanner:
    """Builds a live, relative 2D room model from browser camera frames.

    This is intentionally a relative spatial reconstruction, not a metric 3D
    SLAM system. OpenCV estimates frame-to-frame camera motion and structure
    lines; YOLO supplies real object detections. The frontend visualizes the
    accumulated result as a virtual room map.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.previous_gray: Optional[np.ndarray] = None
        self.pose_x = 0.0
        self.pose_y = 0.0
        self.pose_angle = 0.0
        self.frames = 0
        self.total_motion = 0.0
        self.last_ts = 0.0
        self.segments: List[Dict[str, float]] = []
        self.detector = None
        self.names: Dict[int, str] = {}
        self.initialized = False
        # Panorama state: current-frame -> accumulated panorama homography.
        self.panorama: Optional[np.ndarray] = None
        self.panorama_h: Optional[np.ndarray] = None
        self._current_to_pano: Optional[np.ndarray] = None
        self.stitch_confidence = 0.0
        self.stitched_frames = 0

    def reset(self) -> None:
        with self.lock:
            self.previous_gray = None
            self.pose_x = 0.0
            self.pose_y = 0.0
            self.pose_angle = 0.0
            self.frames = 0
            self.total_motion = 0.0
            self.last_ts = 0.0
            self.segments = []
            self.initialized = False
            self.panorama = None
            self.panorama_h = None
            self._current_to_pano = None
            self.stitch_confidence = 0.0
            self.stitched_frames = 0

    def _ensure_detector(self):
        if self.detector is not None:
            return
        cfg = _load_config()
        model_cfg = cfg.get("model", {})
        self.detector = YoloDetector(
            weights=model_cfg.get("weights", "yolov8n.pt"),
            device=model_cfg.get("device", "auto"),
            conf_thres=float(model_cfg.get("conf_thres", 0.40)),
            iou_thres=float(model_cfg.get("iou_thres", 0.45)),
            # Room scanning should see ordinary scene objects as well as
            # security classes; the main tracker remains class-filtered.
            classes=None,
            imgsz=int(model_cfg.get("imgsz", 480)),
        )
        self.names = self.detector.class_name_map()

    @staticmethod
    def _structure(frame: np.ndarray) -> List[Dict[str, float]]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 55, 145)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180.0, threshold=55,
            minLineLength=max(45, int(min(frame.shape[:2]) * 0.11)),
            maxLineGap=24,
        )
        h, w = gray.shape[:2]
        result = []
        if lines is None:
            return result
        for raw in lines[:80]:
            x1, y1, x2, y2 = [int(v) for v in raw[0]]
            dx, dy = x2 - x1, y2 - y1
            length = float((dx * dx + dy * dy) ** 0.5)
            if length < min(w, h) * 0.12:
                continue
            angle = float(np.degrees(np.arctan2(dy, dx)))
            # Keep wall/furniture-like dominant horizontal/vertical structure.
            norm = abs(((angle + 90.0) % 180.0) - 90.0)
            if norm < 18.0 or abs(norm - 90.0) < 18.0:
                result.append({
                    "x1": x1 / w, "y1": y1 / h,
                    "x2": x2 / w, "y2": y2 / h,
                    "strength": min(1.0, length / (w * 0.55)),
                })
            if len(result) >= 32:
                break
        return result

    def _motion(self, gray: np.ndarray) -> tuple[float, float, float]:
        if self.previous_gray is None:
            return 0.0, 0.0, 0.0

        orb = cv2.ORB_create(nfeatures=700)
        kp1, des1 = orb.detectAndCompute(self.previous_gray, None)
        kp2, des2 = orb.detectAndCompute(gray, None)
        if des1 is None or des2 is None or len(kp1) < 8 or len(kp2) < 8:
            return 0.0, 0.0, 0.0

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(matcher.match(des1, des2), key=lambda m: m.distance)[:80]
        if len(matches) < 8:
            return 0.0, 0.0, 0.0

        p1 = np.float32([kp1[m.queryIdx].pt for m in matches])
        p2 = np.float32([kp2[m.trainIdx].pt for m in matches])
        affine, inliers = cv2.estimateAffinePartial2D(
            p1, p2, method=cv2.RANSAC, ransacReprojThreshold=3.5
        )
        if affine is None:
            return 0.0, 0.0, 0.0

        dx = float(affine[0, 2] / max(1, gray.shape[1]))
        dy = float(affine[1, 2] / max(1, gray.shape[0]))
        angle = float(np.degrees(np.arctan2(affine[1, 0], affine[0, 0])))
        inlier_ratio = float(np.mean(inliers)) if inliers is not None else 0.0
        if inlier_ratio < 0.22:
            return 0.0, 0.0, 0.0
        return dx, dy, angle

    def _stitch_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """Incrementally build a robust panorama from overlapping scan frames.

        The old scanner only accumulated a pose trace. This adds feature-based
        homography stitching with RANSAC, overlap gating, and a bounded canvas.
        It is still a monocular panorama, not metric SLAM.
        """
        h, w = frame.shape[:2]
        view = frame
        if self.panorama is None:
            self.panorama = view.copy()
            self.panorama_h = np.eye(3, dtype=np.float64)
            self._current_to_pano = np.eye(3, dtype=np.float64)
            self.stitch_confidence = 1.0
            self.stitched_frames = 1
            return {"updated": True, "confidence": 1.0, "frames": 1}

        prev = self.previous_gray
        if prev is None:
            return {"updated": False, "confidence": self.stitch_confidence, "frames": self.stitched_frames}

        gray = cv2.cvtColor(view, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create(nfeatures=1200, fastThreshold=12)
        kp1, des1 = orb.detectAndCompute(prev, None)
        kp2, des2 = orb.detectAndCompute(gray, None)
        if des1 is None or des2 is None or len(kp1) < 12 or len(kp2) < 12:
            return {"updated": False, "confidence": 0.0, "frames": self.stitched_frames}

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        knn = matcher.knnMatch(des1, des2, k=2)
        good = [m for m, n in knn if m.distance < 0.72 * n.distance]
        if len(good) < 10:
            return {"updated": False, "confidence": 0.0, "frames": self.stitched_frames}

        src = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
        if H is None or mask is None:
            return {"updated": False, "confidence": 0.0, "frames": self.stitched_frames}
        inlier_ratio = float(mask.mean())
        if inlier_ratio < 0.28:
            return {"updated": False, "confidence": round(inlier_ratio, 3), "frames": self.stitched_frames}

        # Reject extreme projective warps that usually indicate a bad match.
        if abs(H[2, 0]) > 0.004 or abs(H[2, 1]) > 0.004:
            return {"updated": False, "confidence": round(inlier_ratio, 3), "frames": self.stitched_frames}

        pano = self.panorama
        ph, pw = pano.shape[:2]
        # Keep a generous but bounded canvas around the current panorama.
        canvas_w, canvas_h = 2400, 1400
        tx = (canvas_w - pw) // 2
        ty = (canvas_h - ph) // 2
        T = np.array([[1.0, 0.0, tx], [0.0, 1.0, ty], [0.0, 0.0, 1.0]], dtype=np.float64)
        step_to_pano = (self._current_to_pano if self._current_to_pano is not None else np.eye(3)) @ H
        current_to_canvas = T @ step_to_pano

        warped = cv2.warpPerspective(view, current_to_canvas, (canvas_w, canvas_h))
        base = np.zeros_like(warped)
        base[ty:ty+ph, tx:tx+pw] = pano

        warped_mask = cv2.warpPerspective(np.ones((h, w), dtype=np.uint8) * 255, current_to_canvas, (canvas_w, canvas_h))
        base_mask = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
        base_mask[ty:ty+ph, tx:tx+pw] = 255

        # Feather the overlap instead of simply overwriting it.
        overlap = (warped_mask > 0) & (base_mask > 0)
        only_new = (warped_mask > 0) & ~overlap
        only_base = (base_mask > 0) & ~overlap
        out = np.zeros_like(base)
        out[only_base] = base[only_base]
        out[only_new] = warped[only_new]
        if np.any(overlap):
            out[overlap] = ((base[overlap].astype(np.float32) * 0.5) + (warped[overlap].astype(np.float32) * 0.5)).astype(np.uint8)

        ys, xs = np.where((base_mask > 0) | (warped_mask > 0))
        if len(xs) > 0:
            x1, x2 = max(0, int(xs.min())), min(canvas_w, int(xs.max()) + 1)
            y1, y2 = max(0, int(ys.min())), min(canvas_h, int(ys.max()) + 1)
            cropped = out[y1:y2, x1:x2]
            if cropped.size:
                self.panorama = cropped
                crop_T = np.array([[1.0, 0.0, -x1], [0.0, 1.0, -y1], [0.0, 0.0, 1.0]], dtype=np.float64)
                self._current_to_pano = crop_T @ current_to_canvas
                self.panorama_h = self._current_to_pano.copy()
                self.stitch_confidence = inlier_ratio
                self.stitched_frames += 1
                return {"updated": True, "confidence": round(inlier_ratio, 3), "frames": self.stitched_frames}

        return {"updated": False, "confidence": round(inlier_ratio, 3), "frames": self.stitched_frames}

    def _panorama_preview(self) -> Optional[str]:
        if self.panorama is None or self.panorama.size == 0:
            return None
        image = self.panorama
        scale = min(1.0, 1100.0 / max(image.shape[:2]))
        if scale < 1.0:
            image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', image, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
        if not ok:
            return None
        import base64
        return 'data:image/jpeg;base64,' + base64.b64encode(encoded.tobytes()).decode('ascii')

    def process(self, frame: np.ndarray) -> Dict[str, Any]:
        with self.lock:
            h0, w0 = frame.shape[:2]
            scale = min(1.0, 960.0 / max(w0, h0))
            if scale < 1.0:
                frame = cv2.resize(frame, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            stitch = self._stitch_frame(frame)
            dx, dy, da = self._motion(gray)
            self.pose_x += dx
            self.pose_y += dy
            self.pose_angle += da
            motion = float((dx * dx + dy * dy) ** 0.5)
            self.total_motion += motion
            self.previous_gray = gray
            self.frames += 1
            self.last_ts = time.time()
            self.initialized = True

            segments = self._structure(frame)
            if segments:
                self.segments = segments

            detections = []
            try:
                self._ensure_detector()
                det = self.detector.infer(frame)
                class_ids = det.class_id if det.class_id is not None else np.array([], dtype=int)
                for i, box in enumerate(det.xyxy):
                    conf = float(det.confidence[i]) if det.confidence is not None else 0.0
                    cls = int(class_ids[i]) if i < len(class_ids) else -1
                    x1, y1, x2, y2 = [float(v) for v in box]
                    cx = ((x1 + x2) * 0.5) / frame.shape[1]
                    cy = ((y1 + y2) * 0.5) / frame.shape[0]
                    detections.append({
                        "class_id": cls,
                        "label": self.names.get(cls, f"class_{cls}"),
                        "confidence": round(conf, 3),
                        "x": round(cx, 4),
                        "y": round(cy, 4),
                        "w": round((x2 - x1) / frame.shape[1], 4),
                        "h": round((y2 - y1) / frame.shape[0], 4),
                    })
            except Exception as exc:
                # Scanning remains useful with structure-only reconstruction if
                # the optional YOLO model cannot initialize.
                print(f"[ENV SCAN] detector unavailable: {exc}")

            people = sum(1 for d in detections if d["label"] == "person")
            unique_labels = {}
            for d in detections:
                unique_labels[d["label"]] = unique_labels.get(d["label"], 0) + 1

            # A rough room-shape signal from the detected structural lines.
            horizontal = sum(
                1 for seg in self.segments
                if abs(seg["x2"] - seg["x1"]) >= abs(seg["y2"] - seg["y1"])
            )
            vertical = max(0, len(self.segments) - horizontal)
            coverage = min(100.0, 8.0 + self.frames * 1.7 + min(35.0, self.total_motion * 220.0))

            return {
                "timestamp": self.last_ts,
                "frame": self.frames,
                "pose": {
                    "x": round(self.pose_x, 5),
                    "y": round(self.pose_y, 5),
                    "angle": round(self.pose_angle, 2),
                    "confidence": round(min(0.99, 0.35 + 0.012 * min(self.frames, 30)), 2),
                },
                "segments": self.segments,
                "detections": detections,
                "stitching": {
                    **stitch,
                    "panorama": self._panorama_preview(),
                },
                "metrics": {
                    "objects": len(detections),
                    "people": people,
                    "structure_lines": len(self.segments),
                    "motion": round(motion, 5),
                    "coverage": round(coverage, 1),
                    "horizontal_lines": horizontal,
                    "vertical_lines": vertical,
                    "classes": unique_labels,
                },
                "disclaimer": "Relative 2D reconstruction from monocular camera; scale is not metric.",
            }


ENV_SCANNER = _EnvironmentScanner()

# Camera sessions are exclusive: the browser cannot reliably acquire a
# Windows webcam while OpenCV is holding the same device. The surveillance
# tracker therefore releases local camera handles for room scans/enrollment.
_CAMERA_SESSION_LOCK = threading.Lock()
_CAMERA_SESSION_ACTIVE = False
_CAMERA_SESSION_CAMERAS: List[str] = []

def _begin_exclusive_local_camera_session() -> Dict[str, Any]:
    global _CAMERA_SESSION_ACTIVE, _CAMERA_SESSION_CAMERAS
    with _CAMERA_SESSION_LOCK:
        if _CAMERA_SESSION_ACTIVE:
            return {"active": True, "paused_cameras": list(_CAMERA_SESSION_CAMERAS)}
        tracker = getattr(SHARED, "tracker", None)
        if tracker is None or not hasattr(tracker, "pause_local_cameras"):
            raise HTTPException(status_code=503, detail="Surveillance tracker is not ready")
        paused = tracker.pause_local_cameras()
        _CAMERA_SESSION_CAMERAS = [str(x) for x in paused]
        _CAMERA_SESSION_ACTIVE = True
        return {"active": True, "paused_cameras": list(_CAMERA_SESSION_CAMERAS)}

def _end_exclusive_local_camera_session() -> Dict[str, Any]:
    global _CAMERA_SESSION_ACTIVE, _CAMERA_SESSION_CAMERAS
    with _CAMERA_SESSION_LOCK:
        tracker = getattr(SHARED, "tracker", None)
        ids = list(_CAMERA_SESSION_CAMERAS)
        if tracker is not None and hasattr(tracker, "resume_local_cameras"):
            tracker.resume_local_cameras(ids)
        _CAMERA_SESSION_CAMERAS = []
        _CAMERA_SESSION_ACTIVE = False
        return {"active": False, "resumed_cameras": ids}


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket connection manager
# ──────────────────────────────────────────────────────────────────────────────

class _WsManager:
    def __init__(self) -> None:
        self.clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        data = json.dumps(payload)
        dead: List[WebSocket] = []
        async with self._lock:
            clients = list(self.clients)
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        async with self._lock:
            for ws in dead:
                self.clients.discard(ws)


WS_MANAGER = _WsManager()


# ──────────────────────────────────────────────────────────────────────────────
# Authentication / RBAC
# ──────────────────────────────────────────────────────────────────────────────
AUTH_DB_PATH = BASE_DIR / "auth.db"
AUTH_TOKEN_TTL_SEC = int(os.getenv("GHOST_TRAIL_TOKEN_TTL_SEC", str(8 * 60 * 60)))
AUTH_SECRET_PATH = BASE_DIR / ".ghost_trail_auth_secret"


def _load_auth_secret() -> bytes:
    env_secret = os.getenv("GHOST_TRAIL_AUTH_SECRET")
    if env_secret:
        return env_secret.encode("utf-8")
    try:
        if AUTH_SECRET_PATH.exists():
            return AUTH_SECRET_PATH.read_bytes()
        secret = secrets.token_bytes(32)
        AUTH_SECRET_PATH.write_bytes(secret)
        try:
            AUTH_SECRET_PATH.chmod(0o600)
        except Exception:
            pass
        return secret
    except Exception:
        return b"ghost-trail-local-development-secret-change-me"


AUTH_SECRET = _load_auth_secret()


def _auth_db():
    import sqlite3
    conn = sqlite3.connect(str(AUTH_DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('viewer','analyst','admin')),
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            result TEXT NOT NULL,
            detail TEXT
        )
    """)
    conn.commit()
    return conn


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def _password_verify(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(candidate, digest_hex)
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _create_token(user: dict) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "GTJWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({
        "sub": int(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": int(time.time()),
        "exp": int(time.time()) + AUTH_TOKEN_TTL_SEC,
    }, separators=(",", ":")).encode())
    body = f"{header}.{payload}".encode("ascii")
    sig = _b64(hmac.new(AUTH_SECRET, body, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def _decode_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid token")
    body = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = _b64(hmac.new(AUTH_SECRET, body, hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise ValueError("invalid signature")
    payload = json.loads(_unb64(parts[1]).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("token expired")
    return payload


def _bootstrap_admin() -> None:
    conn = _auth_db()
    row = conn.execute("SELECT id FROM users WHERE username = ?", (os.getenv("GHOST_TRAIL_ADMIN_USERNAME", "admin"),)).fetchone()
    if row:
        conn.close()
        return
    username = os.getenv("GHOST_TRAIL_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("GHOST_TRAIL_ADMIN_PASSWORD")
    generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True
    conn.execute("INSERT INTO users(username,password_hash,role,enabled,created_at) VALUES(?,?,?,?,?)",
                 (username, _password_hash(password), "admin", 1, time.time()))
    conn.commit()
    conn.close()
    if generated:
        print(f"[AUTH] Bootstrap admin created: username={username} password={password}")
        try:
            (BASE_DIR / "auth_bootstrap.txt").write_text(
                f"Ghost Trail bootstrap administrator\nUsername: {username}\nPassword: {password}\n\nChange GHOST_TRAIL_ADMIN_PASSWORD before deployment.\n",
                encoding="utf-8"
            )
        except Exception:
            pass


def _current_user_from_token(token: str) -> dict:
    payload = _decode_token(token)
    conn = _auth_db()
    row = conn.execute("SELECT id, username, role, enabled FROM users WHERE id = ?", (payload["sub"],)).fetchone()
    conn.close()
    if not row or not row["enabled"]:
        raise ValueError("user disabled")
    return dict(row)


def _extract_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    token = request.query_params.get("token", "")
    if token:
        return token
    raise HTTPException(status_code=401, detail="Authentication required")


def require_auth(request: Request) -> dict:
    try:
        return _current_user_from_token(_extract_token(request))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token") from exc


def require_roles(*roles: str):
    def dependency(user: dict = Depends(require_auth)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role for this operation")
        return user
    return dependency


def _audit(user: dict, action: str, target: str = "", result: str = "success", detail: str = "") -> None:
    try:
        conn = _auth_db()
        conn.execute("INSERT INTO audit_log(timestamp,username,role,action,target,result,detail) VALUES(?,?,?,?,?,?,?)",
                     (time.time(), user.get("username", "unknown"), user.get("role", "unknown"), action, target, result, detail[:1000]))
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"[AUTH] Audit write failed: {exc}")


class LoginRequest(BaseModel):
    username: str
    password: str


_bootstrap_admin()

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Ghost Trail", version="1.0.0")

@app.on_event("startup")
async def start_ws_telemetry() -> None:
    app.state.ws_telemetry_task = asyncio.create_task(_ws_telemetry_loop())


@app.on_event("shutdown")
async def stop_ws_telemetry() -> None:
    task = getattr(app.state, "ws_telemetry_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def _pop_pending_ws_alerts() -> List[Dict[str, Any]]:
    """Atomically take alerts waiting for real-time WebSocket delivery."""
    with SHARED.lock:
        pending = list(SHARED.pending_ws_alerts)
        SHARED.pending_ws_alerts.clear()
        return pending


async def _ws_telemetry_loop() -> None:
    """Broadcast real server state to connected dashboards once per second."""
    last_detection_keys: Set[tuple] = set()
    try:
        while True:
            await asyncio.sleep(1.0)

            with SHARED.lock:
                status = SHARED.status
                fps = round(SHARED.fps, 1)
                cameras = list(SHARED.camera_ids)
                active_alerts = len(SHARED.alerts)
                detections_snapshot = {
                    str(camera_id): dict(detections)
                    for camera_id, detections in SHARED.detections.items()
                }

            # This heartbeat is generated only from real backend state.
            await WS_MANAGER.broadcast({
                "type": "telemetry",
                "timestamp": time.time(),
                "status": status,
                "fps": fps,
                "cameras": cameras,
                "active_alerts": active_alerts,
            })

            # Send each newly observed track once, rather than flooding the
            # dashboard with the same detection every second.
            current_detection_keys: Set[tuple] = set()
            for camera_id, detections in detections_snapshot.items():
                for track_id, det in detections.items():
                    key = (camera_id, str(track_id), str(det.get("name", "")))
                    current_detection_keys.add(key)
                    if key in last_detection_keys:
                        continue
                    await WS_MANAGER.broadcast({
                        "type": "detection",
                        "camera_id": camera_id,
                        "track_id": track_id,
                        "name": det.get("name", "Unknown"),
                        "confidence": det.get("conf", det.get("confidence", 0.0)),
                        "bbox": det.get("bbox"),
                        "is_known": bool(det.get("is_known", False)),
                        "timestamp": time.time(),
                    })
            last_detection_keys = current_detection_keys

            # Alerts are queued by the real tracker/API state and delivered
            # immediately on the next server heartbeat.
            for alert in _pop_pending_ws_alerts():
                await WS_MANAGER.broadcast({"type": "alert", **alert})
    except asyncio.CancelledError:
        raise


@app.post("/api/auth/login")
def login(body: LoginRequest):
    conn = _auth_db()
    row = conn.execute("SELECT id, username, password_hash, role, enabled FROM users WHERE username = ?", (body.username.strip(),)).fetchone()
    conn.close()
    if not row or not row["enabled"] or not _password_verify(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user = {"id": row["id"], "username": row["username"], "role": row["role"]}
    _audit(user, "LOGIN", "auth", "success")
    return {"success": True, "token": _create_token(user), "user": user, "expires_in": AUTH_TOKEN_TTL_SEC}


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(require_auth)):
    return {"success": True, "user": user}


@app.get("/api/audit")
def get_audit_log(limit: int = 100, user: dict = Depends(require_roles("admin"))):
    limit = max(1, min(int(limit), 500))
    conn = _auth_db()
    rows = conn.execute("SELECT id,timestamp,username,role,action,target,result,detail FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Authenticated real-time dashboard channel for telemetry and alerts."""
    token = websocket.query_params.get("token", "")
    try:
        user = _current_user_from_token(token)
    except Exception:
        await websocket.close(code=1008, reason="Authentication required")
        return
    await WS_MANAGER.connect(websocket)
    try:
        with SHARED.lock:
            initial = {
                "type": "init",
                "status": SHARED.status,
                "fps": round(SHARED.fps, 1),
                "cameras": list(SHARED.camera_ids),
                "active_alerts": len(SHARED.alerts),
            "face_recognition": {
                "available": SHARED.face_recognition_available,
                "status": SHARED.face_recognition_status,
                "model": SHARED.face_recognition_model,
                "error": SHARED.face_recognition_error,
            },
            }
        await websocket.send_json(initial)

        # Keep the connection open and accept browser heartbeats/control frames.
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[WS] Client disconnected: {exc}")
    finally:
        await WS_MANAGER.disconnect(websocket)


# ──────────────────────────────────────────────────────────────────────────────
# Agentic investigation + privacy ledger
# ──────────────────────────────────────────────────────────────────────────────

class InvestigatorQuery(BaseModel):
    query: str


@app.get("/api/investigator/cases")
def investigator_cases(limit: int = 100, user: dict = Depends(require_roles("analyst", "admin"))):
    db = _get_db()
    if db is None:
        return []
    return db.list_investigation_cases(limit=limit)


@app.post("/api/investigator/query")
def investigator_query(body: InvestigatorQuery, user: dict = Depends(require_roles("analyst", "admin"))):
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
    agent = getattr(tracker, "investigator", None) if tracker else None
    if agent is None:
        raise HTTPException(status_code=503, detail="Investigator is not initialized")
    result = agent.run(body.query)
    _audit(user, "INVESTIGATION_QUERY", "investigator", "success", body.query[:500])
    return result


@app.get("/api/privacy/ledger")
def privacy_ledger(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
    manager = getattr(tracker, "privacy_manager", None) if tracker else None
    if manager is None:
        return {"status": "initializing", "event_counts": {}, "recent_events": []}
    return manager.ledger()


@app.post("/api/privacy/purge")
def privacy_purge(user: dict = Depends(require_roles("admin"))):
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
    manager = getattr(tracker, "privacy_manager", None) if tracker else None
    if manager is None:
        raise HTTPException(status_code=503, detail="Privacy manager is not initialized")
    result = manager.purge_expired()
    _audit(user, "PRIVACY_PURGE", "privacy", "success", json.dumps(result))
    return {"success": True, **result}


# ── Config helpers ──────────────────────────────────────────────────────────

def _load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False)


# ── System configuration endpoints ─────────────────────────────────────────

@app.get("/api/config")
def get_system_config(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    cfg = _load_config()
    object_cfg = cfg.get("object_monitoring", {})
    return {
        "object_monitoring": object_cfg,
        "behavior": cfg.get("behavior", {}),
        # Legacy keys retained so older dashboard builds do not break.
        "threat_classes": object_cfg.get("monitored_classes", []),
        "threat_alert_cooldown_sec": object_cfg.get("alert_cooldown_sec", 30.0),
        "confidence_threshold": cfg.get("model", {}).get("conf_thres", 0.40),
        "cameras": cfg.get("cameras", []),
    }

@app.post("/api/config")
def update_system_config(payload: Dict[str, Any], user: dict = Depends(require_roles("admin"))):
    incoming = payload.get("data", payload) if isinstance(payload, dict) else {}
    cfg = _load_config()

    if "behavior" in incoming:
        behavior = dict(incoming.get("behavior") or {})
        point_keys = [
            "dwell_weight", "reentry_weight", "zone_weight",
            "off_hours_weight", "restricted_zone_weight",
            "reverse_movement_weight", "graph_weight",
            "score_watch", "score_suspicious", "score_high",
        ]
        for key in point_keys:
            if key in behavior:
                behavior[key] = max(0, min(100, int(behavior[key])))

        positive_float_keys = [
            "watch_dwell_sec", "suspicious_dwell_sec", "high_risk_dwell_sec",
            "zone_hop_window_sec",
        ]
        for key in positive_float_keys:
            if key in behavior:
                behavior[key] = max(0.1, float(behavior[key]))

        for key in ("off_hours_start", "off_hours_end"):
            if key in behavior:
                behavior[key] = max(0, min(23, int(behavior[key])))

        if "reentry_high_risk" in behavior:
            behavior["reentry_high_risk"] = max(1, min(20, int(behavior["reentry_high_risk"])))

        # Keep the risk bands ordered so a single bad UI edit cannot invert
        # the meaning of Watch/Suspicious/High Risk.
        watch = int(behavior.get("score_watch", 30))
        suspicious = max(watch, int(behavior.get("score_suspicious", 60)))
        high = max(suspicious, int(behavior.get("score_high", 80)))
        behavior["score_watch"] = watch
        behavior["score_suspicious"] = suspicious
        behavior["score_high"] = high

        if "restricted_zones" in behavior:
            zones = behavior.get("restricted_zones") or []
            behavior["restricted_zones"] = [str(z).strip() for z in zones if str(z).strip()]

        cfg["behavior"] = behavior

    if "object_monitoring" in incoming:
        obj = dict(incoming.get("object_monitoring") or {})
        monitored = sorted({int(x) for x in obj.get("monitored_classes", [2, 24, 26, 28])})
        contextual = sorted({int(x) for x in obj.get("contextual_alert_classes", [24, 26, 28]) if int(x) in monitored})
        obj["monitored_classes"] = monitored
        obj["contextual_alert_classes"] = contextual
        obj["unattended_sec"] = max(1.0, float(obj.get("unattended_sec", 10.0)))
        obj["stationary_speed_px_sec"] = max(1.0, float(obj.get("stationary_speed_px_sec", 18.0)))
        obj["person_proximity_ratio"] = max(0.5, float(obj.get("person_proximity_ratio", 1.5)))
        obj["alert_cooldown_sec"] = max(1.0, float(obj.get("alert_cooldown_sec", 30.0)))
        cfg["object_monitoring"] = obj
    elif "threat_classes" in incoming:
        # Compatibility with the old UI: these are monitored objects, not threat verdicts.
        cfg.setdefault("object_monitoring", {})["monitored_classes"] = sorted({int(x) for x in incoming.get("threat_classes", [])})

    if "cameras" in incoming and isinstance(incoming["cameras"], list):
        cfg["cameras"] = incoming["cameras"]
    if "confidence_threshold" in incoming:
        cfg.setdefault("model", {})["conf_thres"] = max(0.01, min(0.99, float(incoming["confidence_threshold"])))

    _save_config(cfg)
    if hasattr(SHARED, "tracker") and SHARED.tracker:
        SHARED.tracker.stop()
        SHARED.tracker.start()
    return get_system_config()

# ── REST endpoints ──────────────────────────────────────────────────────────


@app.post("/api/camera/session/start")
def start_camera_session(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    result = _begin_exclusive_local_camera_session()
    _audit(user, "CAMERA_EXCLUSIVE_SESSION_START", "local_webcam", detail=str(result))
    return result

@app.post("/api/camera/session/stop")
def stop_camera_session(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    result = _end_exclusive_local_camera_session()
    _audit(user, "CAMERA_EXCLUSIVE_SESSION_STOP", "local_webcam", detail=str(result))
    return result

@app.get("/api/camera/session/status")
def camera_session_status(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    with _CAMERA_SESSION_LOCK:
        return {"active": _CAMERA_SESSION_ACTIVE, "paused_cameras": list(_CAMERA_SESSION_CAMERAS)}

@app.post("/api/environment/scan/reset")
def reset_environment_scan(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    ENV_SCANNER.reset()
    _audit(user, "ENVIRONMENT_SCAN_RESET", "room_scan")
    return {"success": True, "status": "ready"}


@app.post("/api/environment/scan/frame")
async def scan_environment_frame(
    frame: UploadFile = File(...),
    user: dict = Depends(require_roles("viewer", "analyst", "admin")),
):
    with _CAMERA_SESSION_LOCK:
        if not _CAMERA_SESSION_ACTIVE:
            raise HTTPException(status_code=409, detail="Start an exclusive camera session before scanning.")
    raw = await frame.read()
    if not raw or len(raw) > 6 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Invalid or oversized scan frame")
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode scan frame")
    result = ENV_SCANNER.process(image)
    return {"success": True, **result}


@app.get("/api/status")
async def get_status(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    with SHARED.lock:
        return {
            "status": SHARED.status,
            "fps": round(SHARED.fps, 1),
            "cameras": SHARED.camera_ids,
            "active_alerts": len(SHARED.alerts),
            "face_recognition": {
                "available": SHARED.face_recognition_available,
                "status": SHARED.face_recognition_status,
                "model": SHARED.face_recognition_model,
                "error": SHARED.face_recognition_error,
            },
            "investigator": {
                "available": bool(getattr(getattr(SHARED, "tracker", None), "investigator", None)),
                "claude_enabled": bool(getattr(getattr(getattr(SHARED, "tracker", None), "investigator", None), "enabled", False)),
                "model": getattr(getattr(getattr(SHARED, "tracker", None), "investigator", None), "model", None),
            },
            "graph_anomaly": getattr(getattr(getattr(SHARED, "tracker", None), "graph_anomaly", None), "snapshot", lambda: {})(),
        }


@app.get("/api/cameras")
async def get_cameras(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    cfg = _load_config()
    cams = cfg.get("cameras", [])
    result = []
    for c in cams:
        cid = str(c.get("camera_id", ""))
        with SHARED.lock:
            status = dict(SHARED.camera_status.get(cid, {}))
            online = bool(status.get("connected")) or cid in SHARED.frames
        result.append({
            "camera_id": cid,
            "name": str(c.get("name", f"Camera {cid}")),
            "source": str(c.get("source", "")),
            "actual_source": status.get("actual_source", c.get("source", "")),
            "backend": status.get("backend", "unknown"),
            "error": status.get("error"),
            "enabled": bool(c.get("enabled", True)),
            "online": online,
        })
    return result


def _mjpeg_stream(camera_id: str):
    """Yield the latest annotated frame for a camera as an MJPEG stream."""
    camera_id = str(camera_id)
    while True:
        frame = SHARED.get_frame(camera_id)
        if frame is None:
            # Keep the browser connection alive while the tracker is still
            # waiting for its first frame.  Once a frame arrives, the real
            # annotated camera image is streamed below.
            time.sleep(0.05)
            continue

        try:
            ok, encoded = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82]
            )
            if not ok:
                time.sleep(0.02)
                continue
            payload = encoded.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
                + payload
                + b"\r\n"
            )
        except Exception as exc:
            print(f"[WARN] MJPEG stream {camera_id} failed: {exc}")
            time.sleep(0.05)


@app.get("/api/stream/{camera_id}")
def stream_camera(camera_id: str, token: str = Query("")):
    try:
        _current_user_from_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc
    # Only expose cameras that are actually configured.
    cfg = _load_config()
    configured = {str(c.get("camera_id")) for c in cfg.get("cameras", [])}
    if str(camera_id) not in configured:
        return JSONResponse(status_code=404, content={"detail": "Camera not found"})

    return StreamingResponse(
        _mjpeg_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
        },
    )

class CameraAdd(BaseModel):
    camera_id: str
    name: str
    source: str

@app.post("/api/cameras")
def add_camera(body: CameraAdd, user: dict = Depends(require_roles("admin"))):
    cfg = _load_config()
    cams = cfg.setdefault("cameras", [])
    for c in cams:
        if str(c.get("camera_id")) == body.camera_id:
            c["name"] = body.name
            c["source"] = body.source
            c["enabled"] = True
            break
    else:
        cams.append({
            "camera_id": body.camera_id,
            "name": body.name,
            "source": body.source,
            "enabled": True
        })
    _save_config(cfg)
    # Restart tracker so new camera takes effect
    if hasattr(SHARED, "tracker") and SHARED.tracker:
        SHARED.tracker.stop()
        SHARED.tracker.start()
    _audit(user, "CAMERA_ADD", body.camera_id)
    return {"success": True, "camera": body.dict()}

class CameraToggle(BaseModel):
    enabled: bool

@app.post("/api/cameras/{camera_id}/toggle")
def toggle_camera(camera_id: str, body: CameraToggle, user: dict = Depends(require_roles("admin"))):
    cfg = _load_config()
    cams = cfg.get("cameras", [])
    for c in cams:
        if str(c.get("camera_id")) == camera_id:
            c["enabled"] = body.enabled
    _save_config(cfg)
    if hasattr(SHARED, "tracker") and SHARED.tracker:
        SHARED.tracker.stop()
        SHARED.tracker.start()
    _audit(user, "CAMERA_TOGGLE", camera_id, detail=f"enabled={body.enabled}")
    return {"success": True}

@app.delete("/api/cameras/{camera_id}")
def remove_camera(camera_id: str, user: dict = Depends(require_roles("admin"))):
    cfg = _load_config()
    cams = cfg.get("cameras", [])
    cfg["cameras"] = [c for c in cams if str(c.get("camera_id")) != camera_id]
    _save_config(cfg)
    if hasattr(SHARED, "tracker") and SHARED.tracker:
        SHARED.tracker.stop()
        SHARED.tracker.start()
    _audit(user, "CAMERA_DELETE", camera_id)
    return {"success": True}


import sqlite3

class PersonUpdateRequest(BaseModel):
    name: str
    badge_id: str = ""
    role: str = ""
    clearance: str = "Level 2 (Personnel)"
    profile_note: str = ""

@app.get("/api/persons")
def get_persons(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    """Return the complete tracked-person database, including anonymous Guests.

    Registered identities come from the identity gallery. Anonymous identities
    are reconstructed from persisted sighting logs so the Persons page can
    show the same body-ReID movement history even before biometric review.
    """
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)

    persons_by_id = {}
    try:
        with SHARED.lock:
            tracker = getattr(SHARED, "tracker", None)
            manager = getattr(tracker, "identity_manager", None) if tracker else None
            behavior = getattr(tracker, "behavior_analyzer", None) if tracker else None

            if manager is not None:
                for pid, identity in manager.identities.items():
                    details = manager.db.get_identity_details(int(pid)) if identity.is_registered else {}
                    status = str(details.get("face_review_status") or identity.face_review_status or "pending")
                    risk = behavior.score_global(int(pid), time.time()) if behavior is not None else {
                        "score": 0, "tier": "none", "reason": "normal activity"
                    }
                    persons_by_id[int(pid)] = {
                        "id": int(pid),
                        "name": identity.name,
                        "anonymous": not bool(identity.is_registered),
                        "status": "High Risk" if status == "denied" else ("Active" if identity.is_registered else "Anonymous"),
                        "face_review_status": status if identity.is_registered else "not_applicable",
                        "face_reviewed_ts": details.get("face_reviewed_ts"),
                        "face_review_note": details.get("face_review_note"),
                        "risk_tier": "high_risk" if status == "denied" else risk.get("tier"),
                        "risk_score": int(risk.get("score", 0)),
                        "risk_factors": risk.get("reason", "normal activity"),
                        "badge_id": details.get("badge_id") or "" if details else "",
                        "role": details.get("role") or "" if details else "",
                        "clearance": details.get("clearance") or ("Body Re-ID / Anonymous" if not identity.is_registered else "Level 2 (Personnel)"),
                        "profile_note": details.get("profile_note") or "" if details else "",
                        "last_seen": int(identity.last_seen_ts * 1000),
                        "camera": identity.last_seen_camera,
                        "confidence": float(identity.last_match_confidence or 0.0),
                        "sighting_count": 0,
                        "cameras_visited": [],
                        "thumbnail": f"/api/persons/{pid}/thumbnail" if identity.is_registered else None,
                    }

        # Rebuild movement history from persisted sightings. This also recovers
        # anonymous Guests after a dashboard refresh/restart.
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT sl.global_track_id, sl.timestamp, sl.camera_id, sl.match_confidence,
                   ri.name, ri.face_review_status
            FROM sighting_logs sl
            LEFT JOIN registered_identities ri ON sl.global_track_id = ri.id
            ORDER BY sl.timestamp ASC
        """).fetchall()
        conn.close()

        for row in rows:
            pid = int(row["global_track_id"])
            if pid not in persons_by_id:
                name = row["name"] or f"Guest_{abs(pid)}"
                persons_by_id[pid] = {
                    "id": pid,
                    "name": name,
                    "anonymous": True,
                    "status": "Anonymous",
                    "face_review_status": "not_applicable",
                    "face_reviewed_ts": None,
                    "face_review_note": None,
                    "risk_tier": "none",
                    "risk_score": 0,
                    "risk_factors": "normal activity",
                    "badge_id": "",
                    "role": "",
                    "clearance": "Body Re-ID / Anonymous",
                    "profile_note": "Tracked using body Re-ID; biometric identity not established.",
                    "last_seen": int(float(row["timestamp"]) * 1000),
                    "camera": str(row["camera_id"]),
                    "confidence": float(row["match_confidence"] or 0.0),
                    "sighting_count": 0,
                    "cameras_visited": [],
                    "thumbnail": None,
                }
            person = persons_by_id[pid]
            person["sighting_count"] += 1
            cam = str(row["camera_id"])
            if cam not in person["cameras_visited"]:
                person["cameras_visited"].append(cam)
            if float(row["timestamp"]) * 1000 >= float(person["last_seen"] or 0):
                person["last_seen"] = int(float(row["timestamp"]) * 1000)
                person["camera"] = cam
                if row["match_confidence"] is not None:
                    person["confidence"] = float(row["match_confidence"])

        # Refresh current runtime risk values after the sighting pass.
        with SHARED.lock:
            tracker = getattr(SHARED, "tracker", None)
            behavior = getattr(tracker, "behavior_analyzer", None) if tracker else None
            if behavior is not None:
                for pid, person in persons_by_id.items():
                    if pid in getattr(tracker.identity_manager, "identities", {}):
                        risk = behavior.score_global(pid, time.time())
                        person["risk_score"] = int(risk.get("score", 0))
                        person["risk_tier"] = risk.get("tier", "none")
                        person["risk_factors"] = risk.get("reason", "normal activity")

        return sorted(persons_by_id.values(), key=lambda x: x.get("last_seen") or 0, reverse=True)
    except Exception as exc:
        print(f"[ERROR] /api/persons: {exc}")
        return []

@app.put("/api/persons/{person_id}")
def update_person(person_id: int, body: PersonUpdateRequest, user: dict = Depends(require_roles("analyst", "admin"))):
    name = body.name.strip()
    if not name:
        return JSONResponse(status_code=400, content={"success": False, "error": "Name cannot be empty"})
    db = _get_db()
    if db is None:
        return JSONResponse(status_code=503, content={"success": False, "error": "Tracker not running"})
    existing = db.get_identity_details(person_id)
    if not existing:
        return JSONResponse(status_code=404, content={"success": False, "error": "Person not found"})
    old_name = str(existing.get("name") or "")
    tracker = getattr(SHARED, "tracker", None)
    manager = getattr(tracker, "identity_manager", None) if tracker else None
    if manager is not None:
        ok = manager.update_identity_details(person_id, name, body.badge_id, body.role, body.clearance, body.profile_note)
    else:
        ok = db.update_identity_details(person_id, name, body.badge_id, body.role, body.clearance, body.profile_note)
    if not ok:
        return JSONResponse(status_code=404, content={"success": False, "error": "Person not found"})

    # Keep the gallery thumbnail in sync when an accepted Guest is renamed.
    # The filename is derived from the profile name for enrolled faces.
    try:
        faces_dir = BASE_DIR / "Faces"
        old_file = faces_dir / f"{_safe_gallery_stem(old_name)}.jpg"
        new_file = faces_dir / f"{_safe_gallery_stem(name)}.jpg"
        if old_file.exists() and old_file.resolve() != new_file.resolve():
            new_file.parent.mkdir(parents=True, exist_ok=True)
            old_file.replace(new_file)
    except Exception as exc:
        print(f"[WARN] Could not rename face gallery image: {exc}")

    # Keep historical pending captures readable under the edited profile name.
    try:
        with sqlite3.connect(db.db_path, timeout=5.0) as conn:
            conn.execute("UPDATE flagged_persons SET guest_label = ? WHERE global_track_id = ?", (name, int(person_id)))
            conn.commit()
    except Exception:
        pass

    return {"success": True, "id": person_id, "name": name}

@app.get("/api/persons/{person_id}/thumbnail")
def get_person_thumbnail(person_id: int, user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    
    name = None
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM registered_identities WHERE id = ?", (person_id,))
        row = cursor.fetchone()
        if row:
            name = row[0]
        conn.close()
    except Exception:
        pass
        
    if name:
        faces_dir = BASE_DIR / "Faces"
        img_path = faces_dir / f"{_safe_gallery_stem(name)}.jpg"
        if img_path.exists():
            return FileResponse(str(img_path))
            
    return RedirectResponse("/assets/placeholder.jpg")

@app.post("/api/persons")
def register_person(name: str = Form(...), image: UploadFile = File(None), force: str = Form("false"), update_id: str = Form(None), user: dict = Depends(require_roles("admin"))):
    if not image:
        return {"success": False, "error": "Image required"}
    
    faces_dir = Path("Faces")
    faces_dir.mkdir(exist_ok=True)
    img_path = faces_dir / f"{_safe_gallery_stem(name)}.jpg"
    
    with open(img_path, "wb") as f:
        shutil.copyfileobj(image.file, f)
        
    cmd = [sys.executable, "register_identity.py", "--name", name, "--input", str(img_path)]
    if force.lower() == "true":
        cmd.append("--force")
    if update_id and update_id.strip() != "null":
        cmd.append("--update-id")
        cmd.append(update_id.strip())
        
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 2:
        import json
        for line in result.stdout.splitlines():
            if '{"conflict":' in line:
                try:
                    conflict_data = json.loads(line)
                    conflict_data["thumbnail"] = f"/api/persons/{conflict_data['id']}/thumbnail"
                    return {"success": False, "conflict": conflict_data}
                except Exception:
                    pass
        return {"success": False, "error": "Similarity conflict detected but failed to parse details."}
    elif result.returncode != 0:
        return {"success": False, "error": f"Registration failed: {result.stderr}"}
        
    with SHARED.lock:
        if hasattr(SHARED, "tracker") and SHARED.tracker and hasattr(SHARED.tracker, "identity_manager") and SHARED.tracker.identity_manager:
            SHARED.tracker.identity_manager._load_from_db()
            
    _audit(user, "PERSON_REGISTER", name)
    return {"success": True, "person": {"id": -1, "name": name}}

@app.delete("/api/persons/{person_id}")
def delete_person(person_id: int, user: dict = Depends(require_roles("admin"))):
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM registered_identities WHERE id = ?", (person_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

    # Immediately remove from in-memory identity manager
    with SHARED.lock:
        if hasattr(SHARED, "tracker") and SHARED.tracker and hasattr(SHARED.tracker, "identity_manager") and SHARED.tracker.identity_manager:
            SHARED.tracker.identity_manager.remove_identity(person_id)
    _audit(user, "PERSON_DELETE", str(person_id))
    return {"success": True}


@app.post("/api/persons/{person_id}/unenroll")
def unenroll_person(person_id: int, user: dict = Depends(require_roles("admin"))):
    """Remove a profile from the active enrolled face database and gallery."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    review = db.get_face_review(person_id)
    if not review:
        return JSONResponse(status_code=404, content={"success": False, "error": "Person not found"})

    name = str(review.get("name") or f"person_{person_id}")
    removed = db.delete_identity(person_id)
    if not removed:
        return {"success": False, "error": "Person could not be removed"}

    gallery_path = BASE_DIR / "Faces" / f"{_safe_gallery_stem(name)}.jpg"
    try:
        if gallery_path.exists():
            gallery_path.unlink()
    except Exception as exc:
        print(f"[WARN] Could not remove enrolled face image for {name}: {exc}")

    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None
        if manager is not None:
            manager.remove_identity(person_id)

    _audit(user, "PERSON_UNENROLL", str(person_id))
    return {"success": True, "id": person_id, "name": name, "status": "unenrolled"}


class FaceReviewRequest(BaseModel):
    status: str
    note: Optional[str] = None


@app.post("/api/persons/{person_id}/face-review")
def review_person_face(person_id: int, body: FaceReviewRequest, user: dict = Depends(require_roles("analyst", "admin"))):
    """Record a human face verification decision for an enrolled person.

    Confirmed -> verified/authorized for face-review purposes.
    Denied -> High Risk incident is created in the Security Incidents feed.
    """
    status = str(body.status).strip().lower()
    if status not in {"confirmed", "denied"}:
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": "status must be 'confirmed' or 'denied'"
        })

    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    person = db.get_face_review(person_id)
    if not person:
        return JSONResponse(status_code=404, content={
            "success": False,
            "error": "Person not found"
        })

    reviewed_ts = time.time()
    note = body.note.strip() if body.note else None

    if status == "confirmed":
        db.set_face_review(person_id, "confirmed", reviewed_ts, note)
        db.resolve_active_incidents_for_person(person_id, reviewed_ts)
        with SHARED.lock:
            tracker = getattr(SHARED, "tracker", None)
            manager = getattr(tracker, "identity_manager", None) if tracker else None
            if manager is not None:
                manager.set_face_review_status(person_id, "confirmed")
        _resolve_person_runtime_alerts(person_id, str(person["name"]))
        # Record the acceptance so the operator can audit the change.
        incident = db.create_face_acceptance_incident(person_id, str(person["name"]), reviewed_ts)
        alert = _incident_to_alert(incident)
        _audit(user, "FACE_REVIEW_CONFIRM", str(person_id), detail=note or "")
        return {
            "success": True,
            "person_id": person_id,
            "status": "confirmed",
            "reviewed_ts": reviewed_ts,
            "message": "face has been accepted, person has been added to the database",
            "incident": alert,
        }

    db.set_face_review(person_id, "denied", reviewed_ts, note)
    # Replace older person-specific active alarms with the single authoritative
    # face-denial incident created below.
    db.resolve_active_incidents_for_person(person_id, reviewed_ts)
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None
        if manager is not None:
            manager.set_face_review_status(person_id, "denied")
    incident = db.create_face_denial_incident(person_id, str(person["name"]), reviewed_ts)

    # Do not add the same persistent incident to the live feed repeatedly if
    # an operator clicks Deny more than once.
    with SHARED.lock:
        already_live = any(
            int(a.get("incident_id")) == int(incident["id"])
            for a in SHARED.alert_log
            if a.get("incident_id") is not None
        )

    alert = {
        "id": f"face-denied-{incident['id']}",
        "incident_id": int(incident["id"]),
        "source": "manual_face_review",
        "type": "face_verification_denied",
        "alert_type": "face_verification_denied",
        "person_id": person_id,
        "person_name": str(person["name"]),
        "camera_id": incident.get("camera_id") or "PERSONS_DB",
        "message": incident["message"],
        "detail": incident["detail"],
        "risk_tier": "high_risk",
        "severity": "critical",
        "timestamp": reviewed_ts,
        "status": "active",
        "duration_sec": 86400.0,
    }
    if not already_live:
        SHARED.push_alert(alert)
    return {
        "success": True,
        "person_id": person_id,
        "status": "denied",
        "reviewed_ts": reviewed_ts,
        "risk_tier": "high_risk",
        "incident": alert,
    }


def _incident_to_alert(row: Dict[str, Any]) -> Dict[str, Any]:
    incident_type = str(row.get("incident_type") or "security_incident")
    prefix = "face-accepted" if incident_type == "face_verification_accepted" else "face-denied"
    return {
        "id": f"{prefix}-{int(row['id'])}",
        "incident_id": int(row["id"]),
        "source": str(row.get("source") or "manual_face_review"),
        "type": str(row.get("incident_type") or "security_incident"),
        "alert_type": str(row.get("incident_type") or "security_incident"),
        "person_id": row.get("person_id"),
        "person_name": row.get("person_name"),
        "camera_id": row.get("camera_id") or "PERSONS_DB",
        "message": row.get("message"),
        "detail": row.get("detail"),
        "risk_tier": row.get("risk_tier"),
        "severity": "critical" if row.get("risk_tier") == "high_risk" else ("info" if row.get("risk_tier") == "verified" else "warning"),
        "timestamp": row.get("timestamp"),
        "status": row.get("status", "active"),
        "duration_sec": 86400.0,
    }


def _get_db():
    """Return the running tracker's IdentityDatabase, or None if not up yet."""
    with SHARED.lock:
        if hasattr(SHARED, "tracker") and SHARED.tracker and getattr(SHARED.tracker, "identity_manager", None):
            return SHARED.tracker.identity_manager.db
    return None


@app.get("/api/persons/flagged")
def list_flagged_persons(status: str = "pending_review", user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    """
    Pending-review queue: faces captured because a track's behavior crossed
    the Suspicious/High-Risk line. Nothing here is a final 'suspicious' tag
    until a human confirms it — pass status='' to see everything, or
    status='confirmed' / 'dismissed' for already-reviewed items.
    """
    db = _get_db()
    if db is None:
        return []
    rows = db.list_flagged_persons(status=status or None)
    for row in rows:
        row["thumbnail"] = f"/api/persons/flagged/{row['id']}/thumbnail"
    return rows


@app.get("/api/persons/flagged/{flag_id}/thumbnail")
def get_flagged_thumbnail(flag_id: int, user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    db = _get_db()
    row = db.get_flagged_person(flag_id) if db else None
    if not row:
        return RedirectResponse("/assets/placeholder.jpg")
    img_path = Path(row["image_path"])
    if not img_path.is_absolute():
        img_path = BASE_DIR / img_path
    if img_path.exists():
        return FileResponse(str(img_path))
    return RedirectResponse("/assets/placeholder.jpg")


def _resolve_person_runtime_alerts(person_id: int, person_name: Optional[str] = None) -> None:
    with SHARED.lock:
        for collection in (SHARED.alert_log, SHARED.alerts):
            for alert in collection:
                same_person = alert.get("person_id") == int(person_id)
                same_name = bool(person_name) and alert.get("person_name") == person_name
                if (same_person or same_name) and alert.get("type") in {
                    "face_verification_denied", "anomalous_behavior", "watchlist_match", "unknown_person"
                }:
                    alert["status"] = "resolved"

@app.post("/api/persons/flagged/{flag_id}/confirm")
def confirm_flagged_person(flag_id: int, user: dict = Depends(require_roles("analyst", "admin"))):
    """Accept a flagged face and promote that exact guest identity into the
    enrolled face database. A persistent informational security incident is
    also created so the acceptance is auditable in Security Incidents."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    row = db.get_flagged_person(flag_id)
    if not row:
        return {"success": False, "error": "Not found"}

    reviewed_ts = time.time()
    gid = int(row["global_track_id"])
    guest_name = str(row["guest_label"])

    # Persist the acceptance state first. IdentityManager uses this value on
    # startup to keep this profile enrolled even after a restart.
    db.set_face_review(
        gid,
        "confirmed",
        reviewed_ts,
        "face has been accepted, person has been added to the database",
    )
    db.set_flagged_status(flag_id, "confirmed", reviewed_ts)
    db.set_flagged_status_for_identity(gid, "confirmed", reviewed_ts)

    # Copy the reviewed face image into the normal Faces gallery so the same
    # image is used by the Persons Database thumbnail after promotion.
    src = Path(row["image_path"])
    if not src.is_absolute():
        src = BASE_DIR / src
    faces_dir = BASE_DIR / "Faces"
    faces_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_gallery_stem(guest_name) if guest_name else f"person_{gid}"
    gallery_path = faces_dir / f"{safe_name}.jpg"
    try:
        if src.exists():
            shutil.copy2(src, gallery_path)
    except Exception as exc:
        print(f"[WARN] Could not copy accepted face into gallery: {exc}")

    # Promote the same runtime global ID so there is no second identity entry.
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None

    if manager is not None:
        if not manager.promote_identity(gid):
            # It may have been evicted from RAM; reload the persisted gallery.
            manager._load_from_db()
            manager.promote_identity(gid)

    _resolve_person_runtime_alerts(gid, guest_name)
    db.resolve_active_incidents_for_person(gid, reviewed_ts)

    incident = db.create_face_acceptance_incident(gid, guest_name, reviewed_ts)
    alert = _incident_to_alert(incident)

    with SHARED.lock:
        already_live = any(
            int(a.get("incident_id")) == int(incident["id"])
            for a in SHARED.alert_log
            if a.get("incident_id") is not None
        )
    if not already_live:
        SHARED.push_alert(alert)

    return {
        "success": True,
        "id": flag_id,
        "status": "confirmed",
        "person_id": gid,
        "person_name": guest_name,
        "message": "face has been accepted, person has been added to the database",
        "incident": alert,
    }


@app.post("/api/persons/flagged/{flag_id}/deny")
def deny_flagged_person(flag_id: int, user: dict = Depends(require_roles("analyst", "admin"))):
    """Human denies the captured face; retain the capture, mark it High Risk,
    and create a persistent Security Incident."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}

    row = db.get_flagged_person(flag_id)
    if not row:
        return JSONResponse(status_code=404, content={"success": False, "error": "Not found"})

    reviewed_ts = time.time()
    incident = db.deny_flagged_person(flag_id, reviewed_ts)
    if not incident:
        return JSONResponse(status_code=404, content={"success": False, "error": "Not found"})

    # Update the live identity immediately. The DB update above makes the
    # decision persistent so it is restored on the next application start.
    with SHARED.lock:
        tracker = getattr(SHARED, "tracker", None)
        manager = getattr(tracker, "identity_manager", None) if tracker else None
        if manager is not None:
            manager.set_face_review_status(int(row["global_track_id"]), "denied")

    alert = _incident_to_alert(incident)
    alert["duration_sec"] = 86400.0

    with SHARED.lock:
        already_live = any(
            int(a.get("incident_id")) == int(incident["id"])
            for a in SHARED.alert_log
            if a.get("incident_id") is not None
        )
    if not already_live:
        SHARED.push_alert(alert)

    return {
        "success": True,
        "id": flag_id,
        "status": "denied",
        "risk_tier": "high_risk",
        "incident": alert,
    }


@app.delete("/api/persons/flagged/{flag_id}")
def dismiss_flagged_person(flag_id: int, user: dict = Depends(require_roles("analyst", "admin"))):
    """Human reviews the photo and clears it — deletes the row AND the
    saved image. Use this for false positives (wrong person, bad crop,
    behavior that had an innocent explanation)."""
    db = _get_db()
    if db is None:
        return {"success": False, "error": "Tracker not running"}
    row = db.get_flagged_person(flag_id)
    if not row:
        return {"success": False, "error": "Not found"}

    img_path = Path(row["image_path"])
    if not img_path.is_absolute():
        img_path = BASE_DIR / img_path
    try:
        if img_path.exists():
            img_path.unlink()
    except Exception:
        pass

    db.delete_flagged_person(flag_id)
    return {"success": True, "id": flag_id}


@app.get("/api/alerts")
async def get_alerts(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    """Return runtime alerts plus persistent security incidents.

    Persistent face-verification incidents are merged by incident_id so the
    same review event is never rendered twice when it also exists in SHARED.
    """
    with SHARED.lock:
        runtime_alerts = list(SHARED.alert_log[:100])

    db = _get_db()
    persisted_alerts = []
    if db is not None:
        persisted_alerts = [_incident_to_alert(row) for row in db.list_security_incidents(limit=200)]

    runtime_incident_ids = {
        int(a["incident_id"])
        for a in runtime_alerts
        if a.get("incident_id") is not None
    }
    merged = list(runtime_alerts)
    merged.extend(a for a in persisted_alerts if int(a["incident_id"]) not in runtime_incident_ids)
    merged.sort(key=lambda a: float(a.get("timestamp") or 0), reverse=True)
    return merged[:200]


@app.post("/api/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, user: dict = Depends(require_roles("analyst", "admin"))):
    db = _get_db()
    # Persistent face-review incident IDs use face-denied-N or face-accepted-N.
    if str(alert_id).startswith(("face-denied-", "face-accepted-")):
        try:
            incident_id = int(str(alert_id).split("-")[-1])
            if db is not None:
                db.set_security_incident_status(incident_id, "resolved", time.time())
            with SHARED.lock:
                for alert in SHARED.alert_log:
                    if str(alert.get("id", "")) == str(alert_id):
                        alert["status"] = "dismissed"
            return {"success": True, "alert_id": alert_id}
        except ValueError:
            pass

    with SHARED.lock:
        for alert in SHARED.alert_log:
            if str(alert.get("id", "")) == str(alert_id) or str(alert.get("timestamp", "")) == str(alert_id):
                alert["status"] = "dismissed"
                break
    return {"success": True, "alert_id": alert_id}


@app.delete("/api/alerts")
async def clear_alerts(user: dict = Depends(require_roles("analyst", "admin"))):
    db = _get_db()
    if db is not None:
        db.clear_security_incidents()
    with SHARED.lock:
        SHARED.alert_log.clear()
        SHARED.alerts.clear()
    return {"ok": True}


@app.get("/api/sightings")
def get_sightings(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    """Return recent sighting logs from the database."""
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    
    sightings = []
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sl.id, sl.timestamp, sl.camera_id, ri.name, sl.bounding_box_coords,
                   sl.global_track_id, sl.match_confidence, ri.face_review_status
            FROM sighting_logs sl
            LEFT JOIN registered_identities ri ON sl.global_track_id = ri.id
            ORDER BY sl.id DESC
            LIMIT 300
        """)
        for row in cursor.fetchall():
            bbox = [0, 0, 0, 0]
            if row[4]:
                try:
                    import json as _json
                    bbox = _json.loads(row[4])
                except Exception:
                    pass
                    
            name = row[3]
            if not name:
                name = f"Guest_{abs(int(row[5]))}"

            sightings.append({
                "id": row[0],
                "global_track_id": int(row[5]),
                "timestamp": int(row[1] * 1000),
                "camera": row[2],
                "name": name,
                "registered": bool(row[7] in ("confirmed", "denied")),
                "face_review_status": row[7] or "pending",
                "confidence": float(row[6]) if row[6] is not None else None,
                "bbox": bbox
            })
    except Exception as e:
        print(f"[ERROR] /api/sightings: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            
    return sightings

@app.get("/api/dashboard")
def get_dashboard_summary(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
        


    active_cameras = 0
    if hasattr(SHARED, "tracker") and SHARED.tracker and hasattr(SHARED.tracker, "stream_mgr"):
        active_cameras = sum(1 for cam in SHARED.tracker.stream_mgr.streams.values() if cam.enabled)

    # Get today's unknown count from in-memory counter (resets daily)
    with SHARED.lock:
        today_unknown = SHARED.today_unknown_count

    db = _get_db()
    active_persistent_incidents = db.count_active_security_incidents() if db is not None else 0
    with SHARED.lock:
        runtime_persistent_ids = {
            int(a["incident_id"])
            for a in SHARED.alerts
            if a.get("incident_id") is not None and a.get("status") != "dismissed"
        }
        runtime_alert_count = sum(
            1 for a in SHARED.alerts
            if a.get("status") != "dismissed" and a.get("incident_id") is None
        )

    # Runtime face-review alerts are already represented in the DB count, so
    # only add runtime alerts that do not have a persistent incident record.
    active_alerts = active_persistent_incidents + runtime_alert_count

    # Live behavior-risk summary for the Project-B dashboard presentation.
    risk_people = []
    try:
        with SHARED.lock:
            tracker = getattr(SHARED, "tracker", None)
            manager = getattr(tracker, "identity_manager", None) if tracker else None
            behavior = getattr(tracker, "behavior_analyzer", None) if tracker else None
            if manager is not None and behavior is not None:
                for pid, identity in manager.identities.items():
                    risk = behavior.score_global(int(pid), time.time())
                    reason = str(risk.get("reason", "normal activity"))
                    factors = []
                    for part in reason.split(", "):
                        m = re.match(r"^(.*) \+(\d+)$", part)
                        if m:
                            factors.append({"rule": m.group(1), "points": int(m.group(2))})
                    risk_people.append({
                        "person_id": int(pid),
                        "person_name": getattr(identity, "name", f"Guest_{pid}"),
                        "camera_id": getattr(identity, "last_seen_camera", ""),
                        "risk_score": int(risk.get("score", 0)),
                        "risk_tier": risk.get("tier", "none"),
                        "risk_factors": factors,
                    })
        risk_people.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
        risk_people = risk_people[:5]
    except Exception as exc:
        print(f"[WARN] Dashboard risk summary unavailable: {exc}")

    return {
        "activeCameras": active_cameras,
        "totalDetections": today_unknown,
        "activeAlerts": active_alerts,
        "systemHealth": 100,
        "fps": round(SHARED.fps, 1),
        "riskPeople": risk_people,
    }

@app.get("/api/behavior-rules")
def get_behavior_rules(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    """Expose the active, configurable behavior rules exactly as used by the tracker."""
    from behavior_analyzer import BehaviorAnalyzer
    cfg_all = _load_config()
    cfg = cfg_all.get("behavior", {})
    analyzer = BehaviorAnalyzer(
        watch_dwell_sec=cfg.get("watch_dwell_sec", 8.0),
        suspicious_dwell_sec=cfg.get("suspicious_dwell_sec", 20.0),
        high_risk_dwell_sec=cfg.get("high_risk_dwell_sec", 45.0),
        off_hours_start=cfg.get("off_hours_start", 22),
        off_hours_end=cfg.get("off_hours_end", 6),
        reentry_high_risk=cfg.get("reentry_high_risk", 3),
        zone_hop_window_sec=cfg.get("zone_hop_window_sec", 90.0),
        dwell_weight=cfg.get("dwell_weight", 30),
        reentry_weight=cfg.get("reentry_weight", 25),
        zone_weight=cfg.get("zone_weight", 20),
        off_hours_weight=cfg.get("off_hours_weight", 15),
        restricted_zone_weight=cfg.get("restricted_zone_weight", 35),
        reverse_movement_weight=cfg.get("reverse_movement_weight", 15),
        score_watch=cfg.get("score_watch", 30),
        score_suspicious=cfg.get("score_suspicious", 60),
        score_high=cfg.get("score_high", 80),
        graph_weight=cfg.get("graph_weight", 20),
        camera_zones={str(c.get("camera_id")): str(c.get("zone", c.get("name", c.get("camera_id", "")))) for c in cfg_all.get("cameras", [])},
        restricted_zones=tuple(cfg.get("restricted_zones", ["Zone C - Restricted", "Zone C", "Restricted"])),
    )
    return {
        "rules": analyzer.rule_summary(),
        "bands": [
            {"min": 0, "max": max(0, int(analyzer.score_watch) - 1), "label": "Normal"},
            {"min": int(analyzer.score_watch), "max": max(int(analyzer.score_watch), int(analyzer.score_suspicious) - 1), "label": "Watch"},
            {"min": int(analyzer.score_suspicious), "max": max(int(analyzer.score_suspicious), int(analyzer.score_high) - 1), "label": "Suspicious"},
            {"min": int(analyzer.score_high), "max": 100, "label": "High Risk"},
        ],
        "thresholds": {"watch": int(analyzer.score_watch), "suspicious": int(analyzer.score_suspicious), "high": int(analyzer.score_high)},
        "max_score": 100,
    }

@app.get("/api/stats")
def get_stats(user: dict = Depends(require_roles("viewer", "analyst", "admin"))):
    """Return full-day tracking analytics from persisted sighting telemetry."""
    cfg = _load_config()
    db_path = cfg.get("database", {}).get("db_path", "tracker.db")
    if not os.path.isabs(db_path):
        db_path = str(BASE_DIR / db_path)
    timeline_data=[]; camera_data=[]
    total=authorized=unknown=high_risk=0; avg_confidence=None
    try:
        conn=sqlite3.connect(db_path, timeout=5.0); conn.row_factory=sqlite3.Row
        today="date(datetime(sl.timestamp, 'unixepoch', 'localtime')) = date('now', 'localtime')"
        row=conn.execute(f"""SELECT COUNT(*) total,
          SUM(CASE WHEN ri.face_review_status='confirmed' THEN 1 ELSE 0 END) authorized,
          SUM(CASE WHEN ri.id IS NULL OR ri.face_review_status NOT IN ('confirmed','denied') THEN 1 ELSE 0 END) unknown,
          SUM(CASE WHEN ri.face_review_status='denied' THEN 1 ELSE 0 END) high_risk,
          AVG(sl.match_confidence) avg_conf
          FROM sighting_logs sl LEFT JOIN registered_identities ri ON sl.global_track_id=ri.id WHERE {today}""").fetchone()
        total=int(row['total'] or 0); authorized=int(row['authorized'] or 0); unknown=int(row['unknown'] or 0); high_risk=int(row['high_risk'] or 0)
        avg_confidence=float(row['avg_conf']) if row['avg_conf'] is not None else None
        rows=conn.execute(f"""SELECT strftime('%H:00', datetime(sl.timestamp,'unixepoch','localtime')) hour,
          COUNT(*) detections,
          SUM(CASE WHEN ri.face_review_status='confirmed' THEN 1 ELSE 0 END) authorized,
          SUM(CASE WHEN ri.id IS NULL OR ri.face_review_status NOT IN ('confirmed','denied') THEN 1 ELSE 0 END) unknown,
          SUM(CASE WHEN ri.face_review_status='denied' THEN 1 ELSE 0 END) high_risk
          FROM sighting_logs sl LEFT JOIN registered_identities ri ON sl.global_track_id=ri.id
          WHERE {today} GROUP BY hour ORDER BY hour""").fetchall()
        timeline_data=[{'hour':r['hour'],'detections':int(r['detections'] or 0),'authorized':int(r['authorized'] or 0),'unknown':int(r['unknown'] or 0),'high_risk':int(r['high_risk'] or 0),'alerts':0} for r in rows]
        rows=conn.execute(f"""SELECT sl.camera_id camera, COUNT(*) detections,
          SUM(CASE WHEN ri.face_review_status='confirmed' THEN 1 ELSE 0 END) authorized,
          SUM(CASE WHEN ri.id IS NULL OR ri.face_review_status NOT IN ('confirmed','denied') THEN 1 ELSE 0 END) unknown,
          SUM(CASE WHEN ri.face_review_status='denied' THEN 1 ELSE 0 END) high_risk
          FROM sighting_logs sl LEFT JOIN registered_identities ri ON sl.global_track_id=ri.id
          WHERE {today} GROUP BY sl.camera_id ORDER BY detections DESC""").fetchall()
        camera_data=[{'camera':r['camera'],'camera_id':r['camera'],'detections':int(r['detections'] or 0),'authorized':int(r['authorized'] or 0),'unknown':int(r['unknown'] or 0),'high_risk':int(r['high_risk'] or 0),'alerts':0} for r in rows]
    except Exception as e:
        print(f"[ERROR] /api/stats: {e}")
    finally:
        if 'conn' in locals(): conn.close()
    return {'timelineData':timeline_data,'cameraData':camera_data,'totalSightings':total,'authorizedDetections':authorized,'unknownGuests':unknown,'highRiskDetections':high_risk,'averageConfidence':round(avg_confidence*100,1) if avg_confidence is not None else None}


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard static serving
#
# sentinel_app.py opens http://127.0.0.1:8765 directly. The v7 server exposed
# only /api/* routes, so the browser correctly received FastAPI's 404 JSON at
# /. Keep all API routes unchanged and serve the existing React build for every
# non-API browser path, including React Router paths such as /dashboard,
# /persons, /tracking, etc.
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_dashboard_root():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse(status_code=500, content={"detail": "Dashboard build not found"})
    return FileResponse(str(index_path), media_type="text/html")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_dashboard_path(full_path: str):
    # API routes are declared above and take precedence. This fallback is only
    # for dashboard/static browser requests.
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    # Serve an actual file from dashboard/dist when present.
    requested = (STATIC_DIR / full_path).resolve()
    static_root = STATIC_DIR.resolve()
    try:
        requested.relative_to(static_root)
    except ValueError:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    if requested.is_file():
        return FileResponse(str(requested))

    # React Router uses browser history; unknown frontend paths should resolve
    # to index.html so the client router can render the correct page.
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return JSONResponse(status_code=500, content={"detail": "Dashboard build not found"})


# ──────────────────────────────────────────────────────────────────────────────
# Server launcher (called from sentinel_app.py)
# ──────────────────────────────────────────────────────────────────────────────

def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start uvicorn in the calling thread (blocking).

    SentinelAI launches FastAPI from a background thread, so signal handlers
    must be disabled.
    """
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        timeout_keep_alive=5,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server.run()
