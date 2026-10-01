"""
behavior_analyzer.py
=====================
Ghost Trail's behavior-anomaly layer.

This is the piece that turns a generic "person tracker" into Ghost Trail:
instead of alerting on every anonymous person the cameras see, it scores
*behavior* — dwell time, loitering, repeat passes, cross-camera zone-hopping,
off-hours presence — into an explainable risk tier, and only then decides
whether to (a) escalate the track to face recognition against the watchlist,
and (b) raise an alert, with a plain-language reason attached.

"Anonymous until it matters."

Two granularities:
  - LOCAL  (camera_id, track_id): cheap, available before cross-camera Re-ID
    has resolved a global identity. Used to gate whether face recognition is
    even attempted for a track — most people passing through stay anonymous
    (body-embedding only) and never reach this stage.
  - GLOBAL (global_id): available once GlobalIdentityManager has stitched the
    track across cameras. Used to catch loitering and zone-hopping across the
    whole perimeter, and to decide whether to raise a dashboard alert.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ── Risk tiers ────────────────────────────────────────────────────────────
RISK_NONE = "none"
RISK_WATCH = "watch"
RISK_SUSPICIOUS = "suspicious"
RISK_HIGH = "high_risk"

_RISK_ORDER = {RISK_NONE: 0, RISK_WATCH: 1, RISK_SUSPICIOUS: 2, RISK_HIGH: 3}

RISK_LABELS = {
    RISK_NONE: "Normal",
    RISK_WATCH: "Watch",
    RISK_SUSPICIOUS: "Suspicious",
    RISK_HIGH: "High Risk",
}

# Explainable score bands. The score is the single source of truth for
# behavioral escalation; tiers are presentation labels derived from it.
RISK_SCORE_WATCH = 30
RISK_SCORE_SUSPICIOUS = 60
RISK_SCORE_HIGH = 80
RISK_SCORE_MAX = 100


@dataclass
class _TrackRecord:
    first_seen_ts: float
    last_seen_ts: float
    zones_visited: List[Tuple[str, float]] = field(default_factory=list)  # (camera_id, ts)
    reentry_count: int = 0
    reverse_movement_count: int = 0
    last_camera: str = ""
    previous_camera: str = ""
    last_alerted_tier: str = RISK_NONE


class BehaviorAnalyzer:
    """
    Explainable behavior-anomaly scorer.

    All thresholds are intentionally short here (seconds, not minutes) so the
    effect is visible in a live demo; tune them up for real deployment via
    the `behavior:` section of config.yaml.
    """

    def __init__(
        self,
        watch_dwell_sec: float = 8.0,
        suspicious_dwell_sec: float = 20.0,
        high_risk_dwell_sec: float = 45.0,
        off_hours_start: int = 22,  # 22:00
        off_hours_end: int = 6,     # 06:00
        reentry_high_risk: int = 3,
        zone_hop_window_sec: float = 90.0,
        dwell_weight: int = 30,
        reentry_weight: int = 25,
        zone_weight: int = 20,
        off_hours_weight: int = 15,
        restricted_zone_weight: int = 35,
        reverse_movement_weight: int = 15,
        score_watch: int = RISK_SCORE_WATCH,
        score_suspicious: int = RISK_SCORE_SUSPICIOUS,
        score_high: int = RISK_SCORE_HIGH,
        graph_weight: int = 20,
        restricted_zones: Tuple[str, ...] = ("Zone C - Restricted", "Zone C", "Restricted"),
        camera_zones: Dict[str, str] | None = None,
    ) -> None:
        self.watch_dwell_sec = watch_dwell_sec
        self.suspicious_dwell_sec = suspicious_dwell_sec
        self.high_risk_dwell_sec = high_risk_dwell_sec
        self.off_hours_start = off_hours_start
        self.off_hours_end = off_hours_end
        self.reentry_high_risk = reentry_high_risk
        self.zone_hop_window_sec = zone_hop_window_sec
        self.dwell_weight = max(0, int(dwell_weight))
        self.reentry_weight = max(0, int(reentry_weight))
        self.zone_weight = max(0, int(zone_weight))
        self.off_hours_weight = max(0, int(off_hours_weight))
        self.restricted_zone_weight = max(0, int(restricted_zone_weight))
        self.reverse_movement_weight = max(0, int(reverse_movement_weight))
        self.restricted_zones = tuple(str(z).strip().lower() for z in restricted_zones)
        self.camera_zones = {str(k): str(v) for k, v in (camera_zones or {}).items()}
        self.score_watch = max(0, int(score_watch))
        self.score_suspicious = max(self.score_watch, int(score_suspicious))
        self.score_high = max(self.score_suspicious, int(score_high))
        self.graph_weight = max(0, int(graph_weight))
        self._graph_scores: Dict[int, dict] = {}

        self._local: Dict[Tuple[str, int], _TrackRecord] = {}
        self._global: Dict[int, _TrackRecord] = {}

    # ------------------------------------------------------------------
    def rule_summary(self) -> List[dict]:
        """Return the currently active behavior rules for the dashboard UI."""
        rules = [
            {"rule": "Restricted-zone entry", "trigger": "Person enters a configured restricted zone", "max_points": self.restricted_zone_weight},
            {"rule": "Extended loitering", "trigger": f">{self.suspicious_dwell_sec:g} seconds in the monitored zone", "max_points": self.dwell_weight},
            {"rule": "Repeated entry", "trigger": f"Leaves and re-enters; {self.reentry_high_risk}+ re-entries reaches maximum", "max_points": self.reentry_weight},
            {"rule": "Reverse movement", "trigger": f"A → B → A within {self.zone_hop_window_sec:g} seconds", "max_points": self.reverse_movement_weight},
            {"rule": "Off-hours", "trigger": f"{self.off_hours_start:02d}:00–{self.off_hours_end:02d}:00", "max_points": self.off_hours_weight},
            {"rule": "Cross-camera movement", "trigger": "2+ cameras in the rolling window", "max_points": self.zone_weight},
        ]
        if self.graph_weight > 0:
            rules.append({"rule": "Learned path anomaly", "trigger": "Graph movement pattern deviates from learned baseline", "max_points": self.graph_weight})
        return rules

    # ------------------------------------------------------------------
    def _is_off_hours(self, ts: float) -> bool:
        hour = time.localtime(ts).tm_hour
        if self.off_hours_start > self.off_hours_end:
            return hour >= self.off_hours_start or hour < self.off_hours_end
        return self.off_hours_start <= hour < self.off_hours_end

    # ------------------------------------------------------------------
    def _zone_name(self, camera_id: str) -> str:
        return self.camera_zones.get(str(camera_id), str(camera_id))

    # ------------------------------------------------------------------
    def _score(self, rec: _TrackRecord, ts: float) -> Tuple[str, str]:
        """Return the explainable 0-100 behavioral risk score and tier.

        Each factor is independently capped, so one noisy signal cannot
        dominate the whole decision. The returned reason preserves the
        factor breakdown for the dashboard and audit trail.
        """
        dwell = max(0.0, ts - rec.first_seen_ts)
        n_zones = len({z for z, _ in rec.zones_visited})
        current_camera = str(rec.zones_visited[-1][0]) if rec.zones_visited else ""
        current_zone = self._zone_name(current_camera).lower()

        factors: List[Tuple[str, int]] = []

        # Dwell contribution: 0 -> watch threshold -> suspicious -> high.
        if dwell >= self.high_risk_dwell_sec:
            dwell_points = self.dwell_weight
        elif dwell >= self.suspicious_dwell_sec:
            span = max(1.0, self.high_risk_dwell_sec - self.suspicious_dwell_sec)
            dwell_points = int(round(self.dwell_weight * (0.67 + 0.33 * min(1.0, (dwell - self.suspicious_dwell_sec) / span))))
        elif dwell >= self.watch_dwell_sec:
            span = max(1.0, self.suspicious_dwell_sec - self.watch_dwell_sec)
            dwell_points = int(round(self.dwell_weight * 0.33 * min(1.0, (dwell - self.watch_dwell_sec) / span)))
        else:
            dwell_points = 0
        if dwell_points:
            factors.append((f"Dwell time ({dwell:.0f}s)", dwell_points))

        # Repeat passes: scale toward the configured maximum.
        if rec.reentry_count > 0:
            repeat_points = min(
                self.reentry_weight,
                int(round(self.reentry_weight * min(1.0, rec.reentry_count / max(1, self.reentry_high_risk))))
            )
            factors.append((f"Repeat passes ({rec.reentry_count})", repeat_points))

        # B's perimeter-probing signal: A -> B -> A in the rolling window.
        if rec.reverse_movement_count > 0:
            reverse_points = min(self.reverse_movement_weight, rec.reverse_movement_count * 8)
            factors.append((f"Reverse movement ({rec.reverse_movement_count})", reverse_points))

        # Restricted-zone entry is a strong contextual signal, but remains one
        # bounded factor so it cannot by itself exceed the configured maximum.
        if any(marker in current_zone for marker in self.restricted_zones):
            factors.append(("Restricted-zone entry", self.restricted_zone_weight))

        # Cross-camera movement: each additional zone contributes proportionally.
        if n_zones >= 2:
            zone_points = min(self.zone_weight, (n_zones - 1) * max(1, self.zone_weight // 2))
            factors.append((f"Cross-camera movement ({n_zones} zones)", zone_points))

        # Off-hours is contextual evidence, not a standalone escalation signal.
        base_points = sum(points for _, points in factors)
        if self._is_off_hours(ts) and base_points > 0:
            factors.append(("Off-hours activity", self.off_hours_weight))

        # Learned graph anomaly is an additional bounded factor. It is only
        # available at GLOBAL scope, so local face-gating remains deterministic
        # and independent of the learned model.
        graph = self._graph_scores.get(getattr(rec, "global_id", -1))
        if graph and self.graph_weight > 0:
            graph_score = float(graph.get("score", 0.0))
            graph_points = int(round(self.graph_weight * min(1.0, graph_score / 100.0)))
            if graph_points > 0:
                factors.append((f"Learned path anomaly ({graph_score:.0f}/100)", graph_points))

        score = min(RISK_SCORE_MAX, sum(points for _, points in factors))

        if score >= self.score_high:
            tier = RISK_HIGH
        elif score >= self.score_suspicious:
            tier = RISK_SUSPICIOUS
        elif score >= self.score_watch:
            tier = RISK_WATCH
        else:
            tier = RISK_NONE

        if factors:
            reason = ", ".join(f"{label} +{points}" for label, points in factors)
        else:
            reason = "normal activity"
        return tier, reason

    def score_local(self, camera_id: str, track_id: int, timestamp: float) -> dict:
        """Return the complete local risk decision for UI/API consumers."""
        key = (camera_id, track_id)
        rec = self._local.get(key)
        if rec is None:
            rec = _TrackRecord(first_seen_ts=timestamp, last_seen_ts=timestamp)
            self._local[key] = rec
        rec.last_seen_ts = timestamp
        if not rec.zones_visited or rec.zones_visited[-1][0] != camera_id:
            rec.zones_visited.append((camera_id, timestamp))
        tier, reason = self._score(rec, timestamp)
        score = self._score_value(rec, timestamp)
        return {
            "score": score,
            "tier": tier,
            "label": RISK_LABELS[tier],
            "reason": reason,
        }

    def _score_value(self, rec: _TrackRecord, ts: float) -> int:
        """Return the numeric score using the exact same factors as _score."""
        _tier, reason = self._score(rec, ts)
        total = 0
        for part in reason.split(", "):
            if " +" in part:
                try:
                    total += int(part.rsplit(" +", 1)[1])
                except ValueError:
                    pass
        return min(RISK_SCORE_MAX, total)

    def score_breakdown(self, global_id: int, timestamp: float) -> dict:
        """Return structured factor data for the dashboard/audit layer."""
        rec = self._global.get(int(global_id))
        if rec is None:
            return {"score": 0, "tier": RISK_NONE, "label": RISK_LABELS[RISK_NONE], "factors": []}
        tier, reason = self._score(rec, timestamp)
        factors = []
        for part in reason.split(", "):
            if " +" in part:
                label, points = part.rsplit(" +", 1)
                try:
                    factors.append({"rule": label, "points": int(points)})
                except ValueError:
                    pass
        return {
            "score": self._score_value(rec, timestamp),
            "tier": tier,
            "label": RISK_LABELS[tier],
            "factors": factors,
        }

    def set_global_anomaly(self, global_id: int, anomaly: dict) -> None:
        """Attach a learned graph anomaly result to a global track."""
        rec = self._global.get(int(global_id))
        if rec is not None:
            rec.global_id = int(global_id)
        self._graph_scores[int(global_id)] = dict(anomaly or {})

    # ------------------------------------------------------------------
    # LOCAL (pre-identity) — gates whether face recognition runs at all
    # ------------------------------------------------------------------
    def update_local(self, camera_id: str, track_id: int, timestamp: float) -> Tuple[str, str]:
        key = (camera_id, track_id)
        rec = self._local.get(key)
        if rec is None:
            rec = _TrackRecord(first_seen_ts=timestamp, last_seen_ts=timestamp)
            self._local[key] = rec
        rec.last_seen_ts = timestamp
        if not rec.zones_visited or rec.zones_visited[-1][0] != camera_id:
            rec.zones_visited.append((camera_id, timestamp))
        return self._score(rec, timestamp)

    def should_escalate_to_face(self, camera_id: str, track_id: int, timestamp: float) -> bool:
        """True once a track's LOCAL behavior alone earns suspicion.
        Below this, the track is never run through face recognition —
        it stays a fully anonymous body-embedding-only Guest."""
        decision = self.score_local(camera_id, track_id, timestamp)
        return decision["score"] >= self.score_suspicious

    # ------------------------------------------------------------------
    # GLOBAL (post cross-camera stitching) — drives alerts
    # ------------------------------------------------------------------
    def update_global(self, global_id: int, camera_id: str, timestamp: float) -> Tuple[str, str]:
        rec = self._global.get(global_id)
        if rec is None:
            rec = _TrackRecord(first_seen_ts=timestamp, last_seen_ts=timestamp, last_camera=str(camera_id))
            rec.global_id = int(global_id)
            self._global[global_id] = rec

        camera_id = str(camera_id)
        if rec.last_camera and camera_id != rec.last_camera:
            visited_before = {z for z, _ in rec.zones_visited}
            if camera_id in visited_before:
                rec.reentry_count += 1
            # A -> B -> A is a deliberate reverse/probing pattern.
            if rec.previous_camera and camera_id == rec.previous_camera:
                rec.reverse_movement_count += 1
            rec.previous_camera = rec.last_camera
            rec.last_camera = camera_id

        rec.zones_visited.append((camera_id, timestamp))
        cutoff = timestamp - self.zone_hop_window_sec
        rec.zones_visited = [(z, t) for z, t in rec.zones_visited if t >= cutoff]
        rec.last_seen_ts = timestamp

        return self._score(rec, timestamp)

    def score_global(self, global_id: int, timestamp: float) -> dict:
        """Return the latest global score and explainable decision."""
        rec = self._global.get(global_id)
        if rec is None:
            return {"score": 0, "tier": RISK_NONE, "label": RISK_LABELS[RISK_NONE], "reason": "no activity recorded"}
        tier, reason = self._score(rec, timestamp)
        return {"score": self._score_value(rec, timestamp), "tier": tier, "label": RISK_LABELS[tier], "reason": reason}

    # ------------------------------------------------------------------
    def should_alert(self, global_id: int, tier: str) -> bool:
        """De-duped: fires only the first time a track reaches a NEW,
        higher risk tier — not every frame it stays there."""
        rec = self._global.get(global_id)
        if rec is None:
            return False
        if _RISK_ORDER[tier] >= _RISK_ORDER[RISK_SUSPICIOUS] and _RISK_ORDER[tier] > _RISK_ORDER[rec.last_alerted_tier]:
            rec.last_alerted_tier = tier
            return True
        return False

    # ------------------------------------------------------------------
    def cleanup_local(self, camera_id: str, active_track_ids: List[int]) -> None:
        active = {(camera_id, tid) for tid in active_track_ids}
        stale = [k for k in self._local if k[0] == camera_id and k not in active]
        for k in stale:
            self._local.pop(k, None)
