from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Set

import numpy as np


@dataclass
class ObjectObservation:
    class_id: int
    last_center: tuple[float, float]
    last_timestamp: float
    unattended_since: Optional[float] = None
    last_near_person: bool = False
    alerted: bool = False


class ObjectContextEngine:
    """Contextual object assessment.

    Object detection alone never creates a security alert.  Monitored objects
    become an alert only when the configured contextual rule is satisfied.
    The default rule is intended for unattended bags/luggage: the object must
    remain essentially stationary for a configurable period and have no nearby
    person for that same period.
    """

    def __init__(
        self,
        monitored_classes: Iterable[int] = (2, 24, 26, 28),
        contextual_alert_classes: Iterable[int] = (24, 26, 28),
        unattended_sec: float = 10.0,
        stationary_speed_px_sec: float = 18.0,
        person_proximity_ratio: float = 1.5,
    ) -> None:
        self.monitored_classes: Set[int] = {int(x) for x in monitored_classes}
        self.contextual_alert_classes: Set[int] = {int(x) for x in contextual_alert_classes}
        self.unattended_sec = float(unattended_sec)
        self.stationary_speed_px_sec = float(stationary_speed_px_sec)
        self.person_proximity_ratio = float(person_proximity_ratio)
        self._states: Dict[tuple[str, int], ObjectObservation] = {}

    @staticmethod
    def _center(box: np.ndarray) -> tuple[float, float]:
        x1, y1, x2, y2 = [float(v) for v in box]
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @staticmethod
    def _diag(box: np.ndarray) -> float:
        x1, y1, x2, y2 = [float(v) for v in box]
        return max(1.0, math.hypot(x2 - x1, y2 - y1))

    def _near_person(self, box: np.ndarray, person_boxes: Iterable[np.ndarray]) -> bool:
        cx, cy = self._center(box)
        threshold = max(80.0, self._diag(box) * self.person_proximity_ratio)
        for pbox in person_boxes:
            px, py = self._center(pbox)
            if math.hypot(cx - px, cy - py) <= threshold:
                return True
        return False

    def update(
        self,
        camera_id: str,
        track_id: int,
        class_id: int,
        bbox: np.ndarray,
        timestamp: float,
        person_boxes: Iterable[np.ndarray],
    ) -> dict:
        class_id = int(class_id)
        key = (str(camera_id), int(track_id))
        if class_id not in self.monitored_classes:
            return {"monitored": False, "context_alert": False, "reason": ""}

        center = self._center(bbox)
        previous = self._states.get(key)
        speed = 0.0
        if previous and previous.class_id == class_id:
            dt = max(0.001, float(timestamp) - previous.last_timestamp)
            speed = math.hypot(center[0] - previous.last_center[0], center[1] - previous.last_center[1]) / dt
        else:
            previous = ObjectObservation(class_id, center, float(timestamp))
            self._states[key] = previous

        near_person = self._near_person(bbox, person_boxes)
        stationary = speed <= self.stationary_speed_px_sec

        if class_id in self.contextual_alert_classes and stationary and not near_person:
            if previous.unattended_since is None:
                previous.unattended_since = float(timestamp)
        else:
            previous.unattended_since = None
            previous.alerted = False

        duration = 0.0
        context_alert = False
        if previous.unattended_since is not None:
            duration = max(0.0, float(timestamp) - previous.unattended_since)
            context_alert = duration >= self.unattended_sec and not previous.alerted

        previous.last_center = center
        previous.last_timestamp = float(timestamp)
        previous.last_near_person = near_person
        if context_alert:
            previous.alerted = True

        reason = (
            f"{duration:.1f}s stationary, no nearby person; "
            f"context threshold {self.unattended_sec:.1f}s"
            if duration > 0 else ""
        )
        return {
            "monitored": True,
            "context_alert": context_alert,
            "reason": reason,
            "duration_sec": duration,
            "near_person": near_person,
            "speed_px_sec": speed,
        }

    def cleanup(self, active_keys: Set[tuple[str, int]], camera_id: str | None = None) -> None:
        """Remove stale object tracks without touching other cameras."""
        for key in list(self._states):
            if camera_id is not None and key[0] != str(camera_id):
                continue
            if key not in active_keys:
                self._states.pop(key, None)
