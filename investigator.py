"""Agentic analyst layer for Ghost Trail.

Uses Claude tool-use when ANTHROPIC_API_KEY is configured. Without a key, a
fully offline investigator still answers from the same structured tools so the
hackathon demo remains deterministic and does not pretend an LLM was called.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agent_tools import InvestigationTools


SYSTEM_PROMPT = """You are Ghost Trail's cybersecurity investigation assistant.\n\nAnalyze only structured telemetry supplied by tools. Do not infer identity, intent, guilt, or motive from appearance. Treat risk scores as signals, not proof. Explain evidence, timestamps, camera transitions, and uncertainty. Never expose raw embeddings, secrets, or biometric templates. Face escalation is a proposal requiring human approval.\n"""


class Investigator:
    def __init__(self, db, tracker=None) -> None:
        self.tools = InvestigationTools(db, tracker)
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.model = os.getenv("GHOST_TRAIL_CLAUDE_MODEL", "claude-sonnet-4-5")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _offline(self, query: str) -> Dict[str, Any]:
        """Deterministic fallback for demos without a Claude key."""
        import re
        gids = [int(x) for x in re.findall(r"(?:guest|track|person|id)\s*#?\s*(\d+)", query.lower())]
        gid = gids[0] if gids else None
        if gid is not None:
            risk = self.tools.get_risk_breakdown(gid)
            path = self.tools.get_track_path(gid)
            history = self.tools.compare_with_history(gid)
            summary = (f"Track {gid}: risk {risk.get('score', 0)}/100 ({risk.get('tier', 'unknown')}). "
                       f"Camera sequence: {' → '.join(path.get('camera_sequence', [])) or 'none'}. "
                       f"Recent sightings: {history.get('sighting_count', 0)}. "
                       f"Factors: {risk.get('reason', 'not available')}.")
            return {"answer": summary, "tools_used": ["get_risk_breakdown", "get_track_path", "compare_with_history"], "llm": False}
        rows = self.tools.query_sightings(minutes=60, limit=20)
        return {"answer": f"The last hour contains {rows['count']} structured sightings. Ask about a specific track ID, camera, or time window for a focused investigation.", "tools_used": ["query_sightings"], "llm": False}

    def run(self, query: str) -> Dict[str, Any]:
        query = str(query).strip()
        if not query:
            return {"answer": "Enter an investigation question.", "tools_used": [], "llm": False}
        if not self.api_key:
            return self._offline(query)

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]
            used: List[str] = []
            for _ in range(6):
                response = client.messages.create(
                    model=self.model, max_tokens=1200, system=SYSTEM_PROMPT,
                    tools=self.tools.definitions(), messages=messages,
                )
                tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
                text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text" and getattr(b, "text", "").strip()]
                if not tool_uses:
                    return {"answer": "\n".join(text_parts).strip(), "tools_used": used, "llm": True, "model": self.model}
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in tool_uses:
                    used.append(block.name)
                    try:
                        result = self.tools.call(block.name, dict(block.input or {}))
                    except Exception as exc:
                        result = {"error": str(exc)}
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)})
                messages.append({"role": "user", "content": tool_results})
            return {"answer": "Investigation reached the tool-call limit; review the collected evidence.", "tools_used": used, "llm": True, "model": self.model}
        except Exception as exc:
            fallback = self._offline(query)
            fallback["llm_error"] = str(exc)
            return fallback
