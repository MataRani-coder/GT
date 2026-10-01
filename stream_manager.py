from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


@dataclass
class FramePacket:
    camera_id: str
    frame: np.ndarray
    timestamp: float
    frame_index: int


class CameraStream:
    """
    Threaded camera reader.

    Windows webcams are opened with a small backend fallback chain because
    some drivers work with DirectShow while others only work reliably through
    Media Foundation. A failed backend is retried rather than leaving the
    dashboard stuck on "NO SIGNAL" forever.
    """

    def __init__(
        self,
        camera_id: str,
        source: Any,
        target_fps: float = 20.0,
        reconnect_interval_sec: float = 2.0,
        queue_size: int = 2,
        rotation: int = 0,
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.target_fps = max(1.0, float(target_fps))
        self.reconnect_interval_sec = max(0.5, float(reconnect_interval_sec))
        self.frame_queue: "queue.Queue[FramePacket]" = queue.Queue(maxsize=max(1, queue_size))

        self._capture: Optional[cv2.VideoCapture] = None
        self._backend_name = "none"
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frame_index = 0
        self._last_ok_time = 0.0
        self.connected: bool = False
        self.enabled: bool = True
        self.rotation = int(rotation)
        self.last_error: Optional[str] = None
        self.actual_source: Any = source
        self._pause_event = threading.Event()
        self._capture_lock = threading.RLock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"stream-{self.camera_id}", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        """Release the capture device without terminating the stream worker."""
        self._pause_event.set()
        # Serialize release against an in-flight read/open so the browser can
        # acquire the physical webcam without a competing OpenCV handle.
        with self._capture_lock:
            self._release_capture()
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

    def resume(self) -> None:
        """Allow the worker to reacquire the camera after an exclusive browser session."""
        self._pause_event.clear()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._release_capture()
        self.connected = False

    def read_latest(self) -> Optional[FramePacket]:
        latest: Optional[FramePacket] = None
        while True:
            try:
                latest = self.frame_queue.get_nowait()
            except queue.Empty:
                break
        return latest

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(0.05)
                continue
            if self._capture is None or not self._capture.isOpened():
                self._open_capture()
                if self._capture is None or not self._capture.isOpened():
                    self.connected = False
                    time.sleep(self.reconnect_interval_sec)
                    continue

            started = time.monotonic()
            with self._capture_lock:
                cap = self._capture
                if cap is None:
                    continue
                ok, frame = cap.read()

            if not ok or frame is None or frame.size == 0:
                self.connected = False
                self.last_error = (
                    f"{self._backend_name} could not read a frame from source "
                    f"{self.actual_source!r}"
                )
                self._release_capture()
                time.sleep(self.reconnect_interval_sec)
                continue

            if self.rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation in (270, -90):
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            self._frame_index += 1
            packet = FramePacket(
                camera_id=self.camera_id,
                frame=frame,
                timestamp=time.time(),
                frame_index=self._frame_index,
            )
            self._last_ok_time = packet.timestamp
            self.connected = True
            self.last_error = None
            self._put_latest(packet)

            # Respect configured target FPS without creating a large capture
            # backlog. The queue always retains only the newest frame.
            elapsed = time.monotonic() - started
            delay = max(0.0, (1.0 / self.target_fps) - elapsed)
            if delay:
                time.sleep(delay)

    def _check_reachability(self) -> bool:
        if isinstance(self.source, str) and self.source.lower().startswith(("http://", "https://", "rtsp://")):
            try:
                import socket
                import urllib.parse
                parsed = urllib.parse.urlparse(self.source)
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == "https" else (554 if parsed.scheme == "rtsp" else 80))
                if host:
                    with socket.create_connection((host, port), timeout=2.0):
                        return True
            except Exception as exc:
                self.last_error = f"Network source unreachable: {exc}"
                print(f"[WARN] Camera {self.camera_id}: {self.last_error}")
                return False
        return True

    @staticmethod
    def _is_local_source(source: Any) -> bool:
        return isinstance(source, int) or (isinstance(source, str) and source.strip().isdigit())

    def _open_local_camera(self, index: int) -> bool:
        # Try the Windows backends in a deliberate order. Some laptop camera
        # drivers reject CAP_DSHOW while working perfectly with CAP_MSMF.
        candidates = [
            (cv2.CAP_DSHOW, "DirectShow"),
            (cv2.CAP_MSMF, "MediaFoundation"),
            (cv2.CAP_ANY, "OpenCV-default"),
        ]
        for backend, backend_name in candidates:
            cap = None
            try:
                cap = cv2.VideoCapture(index, backend)
                if not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    continue

                # Ask for a common webcam format, but do not require it.
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                ok, frame = cap.read()
                if ok and frame is not None and frame.size:
                    self._capture = cap
                    self._backend_name = backend_name
                    self.actual_source = index
                    self.last_error = None
                    print(
                        f"[CAMERA] {self.camera_id}: opened local camera {index} "
                        f"using {backend_name} ({frame.shape[1]}x{frame.shape[0]})"
                    )
                    # Put the first successful frame into the queue immediately.
                    self._frame_index += 1
                    self._put_latest(FramePacket(
                        camera_id=self.camera_id,
                        frame=frame,
                        timestamp=time.time(),
                        frame_index=self._frame_index,
                    ))
                    self.connected = True
                    return True
                cap.release()
            except Exception as exc:
                if cap is not None:
                    cap.release()
                self.last_error = f"{backend_name}: {exc}"
        return False

    def _open_capture(self) -> None:
        self._release_capture()

        if not self._check_reachability():
            return

        if self._is_local_source(self.source):
            configured_index = int(self.source)
            # First respect the configured camera. If Windows exposes the
            # webcam at another index, try a couple of nearby indices as a
            # recovery path. The dashboard reports the actual source used.
            candidates = [configured_index]
            for index in (0, 1, 2, 3):
                if index not in candidates:
                    candidates.append(index)

            for index in candidates:
                if self._open_local_camera(index):
                    return

            self.connected = False
            self.last_error = (
                f"No usable local camera found. Tried indices {candidates}. "
                "Check Windows Camera privacy permissions and whether another app is using the webcam."
            )
            print(f"[ERROR] Camera {self.camera_id}: {self.last_error}")
            return

        try:
            import os
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "timeout;5000|rw_timeout;5000|flags;low_delay|fflags;nobuffer|analyzeduration;0|probesize;32"
            )
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                # Some HTTP/MJPEG sources work better with the default backend.
                cap = cv2.VideoCapture(self.source, cv2.CAP_ANY)

            if cap.isOpened():
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self._capture = cap
                self._backend_name = "FFMPEG/default"
                self.actual_source = self.source
                self.last_error = None
                self.connected = True
                print(f"[CAMERA] {self.camera_id}: opened stream {self.source}")
            else:
                cap.release()
                self.connected = False
                self.last_error = f"OpenCV could not open network/video source {self.source!r}"
                print(f"[ERROR] Camera {self.camera_id}: {self.last_error}")
        except Exception as exc:
            self.connected = False
            self.last_error = f"Failed to open source {self.source!r}: {exc}"
            print(f"[ERROR] Camera {self.camera_id}: {self.last_error}")

    def _release_capture(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None
        self.connected = False

    def _put_latest(self, packet: FramePacket) -> None:
        if self.frame_queue.full():
            try:
                _ = self.frame_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self.frame_queue.put_nowait(packet)
        except queue.Full:
            pass


class StreamManager:
    def __init__(self, camera_configs: List[Dict[str, Any]], stream_cfg: Dict[str, Any]) -> None:
        self.streams: Dict[str, CameraStream] = {}
        for camera_cfg in camera_configs:
            camera_id = str(camera_cfg["camera_id"])
            source = camera_cfg["source"]
            self.streams[camera_id] = CameraStream(
                camera_id=camera_id,
                source=source,
                target_fps=stream_cfg.get("target_fps", 20),
                reconnect_interval_sec=stream_cfg.get("reconnect_interval_sec", 2.0),
                queue_size=stream_cfg.get("queue_size", 2),
                rotation=camera_cfg.get("rotation", 0),
            )

    def start_all(self) -> None:
        for stream in self.streams.values():
            stream.start()

    def stop_all(self) -> None:
        for stream in self.streams.values():
            stream.stop()

    def pause_local_cameras(self) -> List[str]:
        paused = []
        for camera_id, stream in self.streams.items():
            if stream._is_local_source(stream.source) and not stream._pause_event.is_set():
                stream.pause()
                paused.append(camera_id)
        return paused

    def resume_cameras(self, camera_ids: List[str]) -> None:
        for camera_id in camera_ids:
            stream = self.streams.get(str(camera_id))
            if stream is not None:
                stream.resume()

    def get_latest_frames(self) -> Dict[str, FramePacket]:
        latest: Dict[str, FramePacket] = {}
        for camera_id, stream in self.streams.items():
            packet = stream.read_latest()
            if packet is not None:
                latest[camera_id] = packet
        return latest