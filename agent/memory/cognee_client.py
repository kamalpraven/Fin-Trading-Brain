from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from agent.config import load_agent_config


@dataclass
class CogneeClient:
    endpoint: str | None = None
    api_key: str | None = None

    def __post_init__(self):
        cfg = load_agent_config()
        if self.endpoint is None:
            self.endpoint = cfg.cognee_endpoint
        if self.api_key is None:
            self.api_key = cfg.cognee_api_key

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def healthcheck(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "reason": "COGNEE credentials not configured"}
        try:
            resp = requests.get(f"{self.endpoint.rstrip('/')}/health", headers=self._headers(), timeout=10)
            if resp.status_code >= 400:
                return {"available": False, "reason": f"Cognee healthcheck HTTP {resp.status_code}"}
            return {"available": True, "status": "READY"}
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

    def remember_research(self, report: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "stored": False, "reason": "COGNEE credentials not configured"}
        try:
            resp = requests.post(f"{self.endpoint.rstrip('/')}/memory", headers=self._headers(), json={"type": "research", "content": report}, timeout=20)
            resp.raise_for_status()
            return {"available": True, "stored": True, "response": _safe_json(resp)}
        except Exception as exc:
            return {"available": False, "stored": False, "reason": str(exc)}

    def recall_research(self, query: str, limit: int = 5) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "reason": "COGNEE credentials not configured", "memories": []}
        try:
            resp = requests.post(f"{self.endpoint.rstrip('/')}/search", headers=self._headers(), json={"query": query, "limit": limit}, timeout=20)
            resp.raise_for_status()
            data = _safe_json(resp)
            memories = data.get("results") if isinstance(data, dict) else data
            return {"available": True, "query": query, "memories": memories if isinstance(memories, list) else []}
        except Exception as exc:
            return {"available": False, "reason": str(exc), "memories": []}

    def remember_hypothesis(self, hypothesis: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "hypothesis", "content": hypothesis})

    def remember_outcome(self, outcome: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "outcome", "content": outcome})

    def remember_strategy_lesson(self, lesson: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "strategy_lesson", "content": lesson})


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text[:1000]}
