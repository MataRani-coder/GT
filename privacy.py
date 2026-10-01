"""Privacy-by-design controls for Ghost Trail.

The privacy layer is intentionally independent from the detection models. It
provides stable pseudonymous aliases, an auditable escalation ledger, and
retention enforcement. It never stores raw frames or embeddings in the ledger.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path
from typing import Dict, Optional


class PrivacyManager:
    def __init__(self, db, base_dir: str | Path, alias_secret: Optional[bytes] = None,
                 sighting_retention_hours: float = 24.0,
                 flagged_retention_hours: float = 168.0) -> None:
        self.db = db
        self.base_dir = Path(base_dir)
        self.sighting_retention_hours = max(1.0, float(sighting_retention_hours))
        self.flagged_retention_hours = max(1.0, float(flagged_retention_hours))
        secret = alias_secret or os.getenv("GHOST_TRAIL_PRIVACY_SECRET", "") .encode("utf-8")
        if not secret:
            secret_path = self.base_dir / ".ghost_trail_privacy_secret"
            if secret_path.exists():
                secret = secret_path.read_bytes()
            else:
                secret = os.urandom(32)
                try:
                    secret_path.write_bytes(secret)
                    secret_path.chmod(0o600)
                except Exception:
                    pass
        self._secret = secret

    def alias(self, global_id: int, timestamp: Optional[float] = None) -> str:
        """Return a rotating daily pseudonym; raw IDs are never exposed by this method."""
        ts = float(timestamp or time.time())
        day = time.strftime("%Y%m%d", time.localtime(ts))
        digest = hmac.new(self._secret, f"{day}:{int(global_id)}".encode(), hashlib.sha256).hexdigest()[:10]
        return f"G-{digest.upper()}"

    def record(self, event_type: str, global_id: int, reason: str = "",
               camera_id: str = "", actor: str = "system", timestamp: Optional[float] = None,
               metadata: Optional[Dict[str, object]] = None) -> int:
        alias = self.alias(global_id, timestamp)
        payload = dict(metadata or {})
        payload.pop("embedding", None)
        payload.pop("face_embedding", None)
        payload.pop("image", None)
        return self.db.create_privacy_event(event_type, alias, reason, camera_id, actor, payload)

    def purge_expired(self, now: Optional[float] = None) -> Dict[str, int]:
        now = float(now or time.time())
        sight_cutoff = now - self.sighting_retention_hours * 3600.0
        deleted_sightings = self.db.purge_sightings_before(sight_cutoff)
        deleted_guest_embeddings = 0
        try:
            deleted_guest_embeddings = self.db.purge_guest_embeddings_before(sight_cutoff)
        except Exception:
            pass
        deleted_flagged = 0
        # Flagged image paths are local relative paths; remove expired records and files.
        try:
            rows = self.db.list_flagged_persons(status=None)
            cutoff = now - self.flagged_retention_hours * 3600.0
            for row in rows:
                if float(row.get("timestamp", now)) >= cutoff:
                    continue
                path = Path(str(row.get("image_path", "")))
                if not path.is_absolute():
                    path = self.base_dir / path
                try:
                    if path.exists(): path.unlink()
                except OSError:
                    pass
                try:
                    self.db.delete_flagged_person(int(row["id"]))
                    deleted_flagged += 1
                except Exception:
                    pass
        except Exception:
            pass
        return {"sightings": deleted_sightings, "guest_embeddings": deleted_guest_embeddings, "flagged": deleted_flagged}

    def ledger(self) -> Dict[str, object]:
        counts = self.db.privacy_counts()
        events = self.db.list_privacy_events(limit=100)
        try:
            total_sightings = self.db.get_sighting_count()
        except Exception:
            total_sightings = 0
        face_escalations = counts.get("face_escalation", 0)
        return {
            "total_sightings": total_sightings,
            "face_escalations": face_escalations,
            "privacy_events": sum(counts.values()),
            "event_counts": counts,
            "anonymity_rate": round(max(0.0, 1.0 - (face_escalations / max(1, total_sightings))) * 100.0, 2),
            "sighting_retention_hours": self.sighting_retention_hours,
            "flagged_retention_hours": self.flagged_retention_hours,
            "recent_events": events[:25],
        }
