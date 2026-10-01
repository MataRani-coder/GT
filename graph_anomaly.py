"""Learned movement anomaly model for Ghost Trail.

The model learns normal camera-to-camera transitions and dwell durations from
historical sighting telemetry.  It scores a new observation *before* updating
its statistics, avoiding the common mistake of making the current event look
normal simply because it was just inserted into the model.

No video, face embedding, or name is required.  Only camera IDs, timestamps,
and pseudonymous track IDs are used.
"""
from __future__ import annotations

import math
import threading
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple


class GraphAnomalyDetector:
    def __init__(self, bucket_minutes: int = 60, smoothing: float = 1.0,
                 warmup_observations: int = 8, anomaly_threshold: float = 2.5) -> None:
        self.bucket_minutes = max(1, int(bucket_minutes))
        self.smoothing = max(0.01, float(smoothing))
        self.warmup_observations = max(1, int(warmup_observations))
        self.anomaly_threshold = max(0.1, float(anomaly_threshold))
        self._transitions: Dict[Tuple[str, str, int], int] = defaultdict(int)
        self._outgoing: Dict[Tuple[str, int], int] = defaultdict(int)
        self._dwell_values: Dict[Tuple[str, int], List[float]] = defaultdict(list)
        self._last_seen: Dict[int, Tuple[str, float]] = {}
        self._observations = 0
        self._lock = threading.RLock()

    def _bucket(self, ts: float) -> int:
        return (int(__import__('time').localtime(ts).tm_hour) * 60 +
                int(__import__('time').localtime(ts).tm_min)) // self.bucket_minutes

    def fit(self, rows: Iterable[Dict[str, object]]) -> None:
        """Learn from chronological sighting rows."""
        ordered = sorted(rows, key=lambda r: float(r.get("timestamp", 0.0)))
        with self._lock:
            self._last_seen.clear()
            for row in ordered:
                gid = int(row.get("global_track_id", -1))
                camera = str(row.get("camera_id", ""))
                ts = float(row.get("timestamp", 0.0))
                if gid < 0 or not camera or ts <= 0:
                    continue
                previous = self._last_seen.get(gid)
                if previous:
                    prev_camera, prev_ts = previous
                    dt = max(0.0, ts - prev_ts)
                    bucket = self._bucket(ts)
                    if prev_camera != camera:
                        self._transitions[(prev_camera, camera, bucket)] += 1
                        self._outgoing[(prev_camera, bucket)] += 1
                    if dt > 0 and dt < 3600:
                        vals = self._dwell_values[(camera, bucket)]
                        vals.append(dt)
                        if len(vals) > 200:
                            del vals[:-200]
                self._last_seen[gid] = (camera, ts)
                self._observations += 1

    def observe(self, global_id: int, camera_id: str, timestamp: float) -> Dict[str, object]:
        """Score a movement and then learn from it."""
        gid = int(global_id)
        camera = str(camera_id)
        ts = float(timestamp)
        with self._lock:
            previous = self._last_seen.get(gid)
            bucket = self._bucket(ts)
            score = 0.0
            reasons: List[str] = []
            transition_prob = None
            dwell_z = 0.0

            if previous:
                prev_camera, prev_ts = previous
                dt = max(0.0, ts - prev_ts)
                if prev_camera != camera:
                    outgoing = self._outgoing.get((prev_camera, bucket), 0)
                    edge = self._transitions.get((prev_camera, camera, bucket), 0)
                    # Laplace smoothing across observed destinations.
                    destinations = {k[1] for k in self._transitions if k[0] == prev_camera and k[2] == bucket}
                    denom = outgoing + self.smoothing * max(1, len(destinations) + 1)
                    transition_prob = (edge + self.smoothing) / max(self.smoothing, denom)
                    surprisal = -math.log(max(1e-6, transition_prob))
                    if self._observations >= self.warmup_observations:
                        score += min(70.0, surprisal * 18.0)
                    if transition_prob < 0.15:
                        reasons.append(f"rare transition {prev_camera}→{camera} ({transition_prob:.2f})")

                if 0 < dt < 3600:
                    vals = self._dwell_values.get((camera, bucket), [])
                    if len(vals) >= 5:
                        mean = sum(vals) / len(vals)
                        variance = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
                        std = max(1.0, variance ** 0.5)
                        dwell_z = abs(dt - mean) / std
                        if self._observations >= self.warmup_observations:
                            score += min(30.0, max(0.0, dwell_z - 1.5) * 8.0)
                        if dwell_z >= 3.0:
                            reasons.append(f"unusual dwell {dt:.0f}s (z={dwell_z:.1f})")

                if dt > 0 and dt < 3600:
                    vals = self._dwell_values[(camera, bucket)]
                    vals.append(dt)
                    if len(vals) > 200:
                        del vals[:-200]

                if prev_camera != camera:
                    self._transitions[(prev_camera, camera, bucket)] += 1
                    self._outgoing[(prev_camera, bucket)] += 1

            self._last_seen[gid] = (camera, ts)
            self._observations += 1
            score = max(0.0, min(100.0, score))
            if score >= 70:
                tier = "high"
            elif score >= 45:
                tier = "anomalous"
            elif score >= 20:
                tier = "watch"
            else:
                tier = "normal"
            if not reasons:
                reasons.append("movement matches learned baseline")
            return {
                "score": round(score, 1),
                "tier": tier,
                "reason": "; ".join(reasons),
                "transition_probability": round(transition_prob, 4) if transition_prob is not None else None,
                "dwell_z": round(dwell_z, 2),
                "observations": self._observations,
                "learned": self._observations >= self.warmup_observations,
            }

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "observations": self._observations,
                "learned": self._observations >= self.warmup_observations,
                "nodes": len({k[0] for k in self._transitions} | {k[1] for k in self._transitions}),
                "edges": len(self._transitions),
                "warmup_observations": self.warmup_observations,
                "bucket_minutes": self.bucket_minutes,
            }
