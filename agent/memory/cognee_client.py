from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from agent.config import load_agent_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CogneeClient:
    """Small REST adapter for external Cognee memory.

    Credentials are read only from environment via ``load_agent_config`` unless explicitly
    injected by tests. Methods never print or return credentials.
    """

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
        return {"X-API-Key": str(self.api_key), "Content-Type": "application/json"}

    @property
    def dataset_name(self) -> str:
        import os
        return os.getenv("COGNEE_DATASET", "fin_trading_brain")

    def _url(self, path: str) -> str:
        assert self.endpoint is not None
        return f"{self.endpoint.rstrip('/')}/{path.lstrip('/')}"

    def healthcheck(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured"}
        try:
            resp = requests.get(self._url("health"), headers=self._headers(), timeout=10)
            if resp.status_code >= 400:
                return {"available": False, "status": "DEGRADED", "reason": f"Cognee healthcheck HTTP {resp.status_code}"}
            return {"available": True, "status": "READY", "endpoint_host": _safe_host(self.endpoint)}
        except Exception as exc:
            return {"available": False, "status": "DEGRADED", "reason": str(exc)}

    def remember_research(self, report: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "stored": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured"}
        compact = compact_research_summary(report)
        text = "FIN_TRADING_BRAIN_RESEARCH_MEMORY\n" + _json_dumps(compact)
        try:
            add_resp = requests.post(
                self._url("api/v1/add_text"),
                headers=self._headers(),
                json={"textData": [text], "datasetName": self.dataset_name, "nodeSet": ["fin_trading_research"]},
                timeout=30,
            )
            add_resp.raise_for_status()
            cog_resp = requests.post(
                self._url("api/v1/cognify"),
                headers=self._headers(),
                json={"datasets": [self.dataset_name], "runInBackground": False},
                timeout=120,
            )
            cog_resp.raise_for_status()
            return {"available": True, "stored": True, "status": "READY", "brief_id": compact.get("brief_id"), "symbol": compact.get("symbol"), "dataset": self.dataset_name}
        except Exception as exc:
            return {"available": False, "stored": False, "status": "DEGRADED", "reason": str(exc)}

    def recall_research(self, query: str, limit: int = 5) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured", "memories": []}
        payload = {"query": query, "datasets": [self.dataset_name], "searchType": "CHUNKS", "topK": limit, "onlyContext": True}
        try:
            resp = requests.post(self._url("api/v1/search"), headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            data = _safe_json(resp)
            memories = _extract_memories(data)
            return {"available": True, "status": "READY", "query": query, "dataset": self.dataset_name, "memories": memories[:limit], "retrieved_at": _utc_now()}
        except Exception as exc:
            return {"available": False, "status": "DEGRADED", "reason": str(exc), "memories": []}

    def remember_hypothesis(self, hypothesis: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "hypothesis", "hypothesis": hypothesis})

    def remember_outcome(self, outcome: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "outcome", "outcome": outcome})

    def remember_strategy_lesson(self, lesson: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "strategy_lesson", "lessons": lesson})


def compact_research_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Store compact structured summaries, not raw pages or secret-bearing logs."""
    ts = report.get("as_of") or report.get("timestamp") or report.get("generated_at") or _utc_now()
    candidates = report.get("candidates") or report.get("quantitative_candidates", []) or []
    actions = report.get("candidate_actions", []) or []
    symbol = report.get("symbol") or (actions[0].get("symbol") if actions else None) or (candidates[0].get("symbol") if candidates else "PORTFOLIO")
    evidence = []
    for item in (report.get("external_evidence", []) or [])[:8]:
        if item.get("available") is False:
            continue
        evidence.append({
            "symbol": item.get("symbol"),
            "title": item.get("title"),
            "url": item.get("url"),
            "source": item.get("source"),
            "published_at": item.get("published_at"),
            "retrieved_at": item.get("retrieved_at"),
        })
    risk = report.get("risk_state") or report.get("risk") or {}
    return {
        "brief_id": report.get("brief_id") or f"brief-{str(ts)[:19]}",
        "as_of": ts,
        "symbol": symbol,
        "regime": report.get("regime_state") or report.get("market_regime", {}).get("qqq", {}),
        "ranking": [{"rank": r.get("rank"), "symbol": r.get("symbol"), "signal": r.get("signal"), "as_of": r.get("as_of")} for r in candidates[:10]],
        "evidence_summary": evidence,
        "risk_summary": risk.get("notes", risk),
        "hypothesis": report.get("hypothesis") or report.get("synthesis") or "deterministic research brief",
        "outcome": report.get("outcome") or "unknown_research_only_no_trades",
        "lessons": report.get("lessons") or [],
    }


def _extract_memories(data: Any) -> list[dict[str, Any]]:
    def normalize(item: Any) -> dict[str, Any] | None:
        if isinstance(item, dict):
            text = item.get("search_result") or item.get("text") or item.get("content")
            out = dict(item)
            if text and isinstance(text, str):
                out["text"] = text
                parsed = _extract_embedded_json(text)
                if parsed:
                    out["research_memory"] = parsed
            return out
        if isinstance(item, str):
            out = {"text": item}
            parsed = _extract_embedded_json(item)
            if parsed:
                out["research_memory"] = parsed
            return out
        return None

    raw: Any = data
    if isinstance(data, dict):
        raw = data.get("results") or data.get("memories") or data.get("data") or data.get("items") or []
        if isinstance(raw, dict):
            raw = raw.get("results") or raw.get("items") or []
    if isinstance(raw, list):
        return [m for x in raw if (m := normalize(x)) is not None]
    one = normalize(raw)
    return [one] if one else []


def _extract_embedded_json(text: str) -> dict[str, Any] | None:
    marker = "FIN_TRADING_BRAIN_RESEARCH_MEMORY"
    idx = text.find(marker)
    if idx >= 0:
        text = text[idx + len(marker):].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            import json
            obj = json.loads(text[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _safe_json(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"text": getattr(resp, "text", "")[:1000]}


def _safe_host(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(endpoint).netloc
    except Exception:
        return None
