"""Read-only investigation tools exposed to the Ghost Trail analyst agent.

The tools intentionally return structured telemetry only. They do not expose raw
frames, face embeddings, passwords, or biometric templates to the LLM.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class InvestigationTools:
    def __init__(self, db, tracker=None) -> None:
        self.db = db
        self.tracker = tracker

    def query_sightings(self, camera_id: Optional[str] = None, global_id: Optional[int] = None,
                        minutes: int = 60, limit: int = 200) -> Dict[str, Any]:
        since = time.time() - max(1, min(int(minutes), 10080)) * 60
        rows = self.db.get_sightings_since(since, limit=max(1, min(int(limit), 1000)))
        if camera_id:
            rows = [r for r in rows if str(r.get("camera_id")) == str(camera_id)]
        if global_id is not None:
            rows = [r for r in rows if int(r.get("global_track_id", -1)) == int(global_id)]
        return {"count": len(rows), "sightings": rows}

    def get_track_path(self, global_id: int, limit: int = 200) -> Dict[str, Any]:
        rows = self.db.get_sightings_for_identity(int(global_id), limit)
        path = [{"timestamp": r["timestamp"], "camera_id": r["camera_id"]} for r in rows]
        return {"global_id": int(global_id), "points": path, "camera_sequence": [p["camera_id"] for p in path]}

    def get_risk_breakdown(self, global_id: int) -> Dict[str, Any]:
        if self.tracker is not None:
            behavior = getattr(self.tracker, "behavior_analyzer", None)
            if behavior is not None:
                return behavior.score_global(int(global_id), time.time())
        return {"score": 0, "tier": "unknown", "reason": "runtime behavior analyzer unavailable"}

    def compare_with_history(self, global_id: int, hours: int = 24) -> Dict[str, Any]:
        rows = self.db.get_sightings_for_identity(int(global_id), limit=5000)
        cutoff = time.time() - max(1, int(hours)) * 3600
        recent = [r for r in rows if float(r["timestamp"]) >= cutoff]
        cameras = []
        for r in recent:
            c = str(r["camera_id"])
            if c not in cameras: cameras.append(c)
        return {"global_id": int(global_id), "hours": int(hours), "sighting_count": len(recent), "cameras": cameras}

    def request_face_escalation(self, global_id: int, reason: str) -> Dict[str, Any]:
        """Create a human-review proposal. This tool never runs face recognition itself."""
        evidence = {"requested_by": "investigator_agent", "reason": str(reason), "global_id": int(global_id)}
        case_id = self.db.create_investigation_case(
            title=f"Face escalation proposal — Guest {int(global_id)}",
            summary="The analyst agent proposed biometric review; human approval is required before face processing.",
            severity="high", person_id=int(global_id), evidence=evidence, status="awaiting_human_approval",
        )
        return {"case_id": case_id, "status": "awaiting_human_approval", "global_id": int(global_id)}

    def draft_incident_report(self, global_id: int, title: str = "Automated investigation") -> Dict[str, Any]:
        risk = self.get_risk_breakdown(global_id)
        path = self.get_track_path(global_id)
        history = self.compare_with_history(global_id)
        summary = (
            f"Track {global_id}: risk {risk.get('score', 0)}/100 ({risk.get('tier', 'unknown')}). "
            f"Observed across {len(history.get('cameras', []))} cameras with {len(path.get('points', []))} logged sightings. "
            f"Factors: {risk.get('reason', 'not available')}."
        )
        evidence = {"risk": risk, "path": path, "history": history}
        case_id = self.db.create_investigation_case(title, summary, severity=str(risk.get("tier", "info")),
                                                     person_id=int(global_id), evidence=evidence)
        return {"case_id": case_id, "summary": summary, "evidence": evidence}

    def definitions(self) -> List[Dict[str, Any]]:
        return [
            {"name": "query_sightings", "description": "Query recent structured sightings. Never returns biometric embeddings or images.", "input_schema": {"type": "object", "properties": {"camera_id": {"type": "string"}, "global_id": {"type": "integer"}, "minutes": {"type": "integer"}, "limit": {"type": "integer"}}}},
            {"name": "get_track_path", "description": "Return the camera sequence and timestamps for one pseudonymous track.", "input_schema": {"type": "object", "properties": {"global_id": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["global_id"]}},
            {"name": "get_risk_breakdown", "description": "Return the current explainable behavioral risk score.", "input_schema": {"type": "object", "properties": {"global_id": {"type": "integer"}}, "required": ["global_id"]}},
            {"name": "compare_with_history", "description": "Compare a track's recent sightings with its own history.", "input_schema": {"type": "object", "properties": {"global_id": {"type": "integer"}, "hours": {"type": "integer"}}, "required": ["global_id"]}},
            {"name": "request_face_escalation", "description": "Propose human-approved biometric review. Does not execute face recognition.", "input_schema": {"type": "object", "properties": {"global_id": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["global_id", "reason"]}},
            {"name": "draft_incident_report", "description": "Create a structured case file from existing telemetry.", "input_schema": {"type": "object", "properties": {"global_id": {"type": "integer"}, "title": {"type": "string"}}, "required": ["global_id"]}},
        ]

    def call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_"):
            raise ValueError(f"Unknown investigation tool: {name}")
        return fn(**args)
