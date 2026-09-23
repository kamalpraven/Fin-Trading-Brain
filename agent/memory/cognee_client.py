from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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

    def remember_research(self, report: dict[str, Any], environment: str = "production") -> dict[str, Any]:
        if not self.available:
            return {"available": False, "stored": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured"}
        compact = compact_research_summary(report)
        structured = build_structured_research_memories(report, environment=environment)
        text_items = ["FIN_TRADING_BRAIN_RESEARCH_MEMORY\n" + _json_dumps(compact)] + [memory_to_cognee_text(m) for m in structured]
        try:
            add_resp = requests.post(
                self._url("api/v1/add_text"),
                headers=self._headers(),
                json={"textData": text_items, "datasetName": self.dataset_name, "nodeSet": ["fin_trading_research"]},
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
            evidence_count = sum(1 for m in structured if m.get("memory_type") == "Evidence")
            symbols = sorted({m.get("symbol") for m in structured if m.get("symbol") and m.get("memory_type") == "SymbolMemory"})
            source_urls = sorted({u for m in structured for u in m.get("source_urls", []) if u})
            return {
                "available": True,
                "stored": True,
                "status": "READY",
                "brief_id": compact.get("brief_id"),
                "symbol": compact.get("symbol"),
                "dataset": self.dataset_name,
                "structured_memories": len(structured),
                "evidence_objects": evidence_count,
                "symbols": symbols,
                "source_urls": source_urls,
                "environment": environment,
            }
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

    def list_datasets(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured", "datasets": []}
        try:
            resp = requests.get(self._url("api/v1/datasets/"), headers=self._headers(), timeout=20)
            resp.raise_for_status()
            data = _safe_json(resp)
            datasets = data if isinstance(data, list) else []
            safe = [{"id": d.get("id"), "name": d.get("name"), "createdAt": d.get("createdAt"), "updatedAt": d.get("updatedAt")} for d in datasets if isinstance(d, dict)]
            return {"available": True, "status": "READY", "datasets": safe}
        except Exception as exc:
            return {"available": False, "status": "DEGRADED", "reason": str(exc), "datasets": []}

    def dataset_id(self, dataset_name: str | None = None) -> str | None:
        name = dataset_name or self.dataset_name
        res = self.list_datasets()
        for ds in res.get("datasets", []):
            if ds.get("name") == name:
                return ds.get("id")
        return None

    def visualize_graph_json(self, query: str | None = None, max_nodes: int = 300, depth: int = 2, dataset_name: str | None = None) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured", "nodes": [], "links": []}
        dsid = self.dataset_id(dataset_name)
        if not dsid:
            return {"available": False, "status": "DEGRADED", "reason": f"Cognee dataset not found: {dataset_name or self.dataset_name}", "nodes": [], "links": []}
        params = {"dataset_id": dsid, "max_nodes": max(1, int(max_nodes)), "neighborhood_depth": max(1, int(depth)), "full": False}
        if query:
            params["query"] = query
        try:
            resp = requests.get(self._url("api/v1/visualize/json"), headers=self._headers(), params=params, timeout=60)
            resp.raise_for_status()
            data = _safe_json(resp)
            if not isinstance(data, dict):
                return {"available": False, "status": "DEGRADED", "reason": "Malformed Cognee graph JSON response", "nodes": [], "links": [], "dataset_id": dsid, "dataset": dataset_name or self.dataset_name}
            nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
            links = data.get("links") if isinstance(data.get("links"), list) else []
            capped_nodes, capped_links = _cap_graph(nodes, links, max_nodes)
            return {"available": True, "status": "READY", "dataset_id": dsid, "dataset": dataset_name or self.dataset_name, "query": query, "nodes": capped_nodes, "links": capped_links, "raw_keys": sorted(data.keys())}
        except Exception as exc:
            return {"available": False, "status": "DEGRADED", "reason": str(exc), "nodes": [], "links": [], "dataset_id": dsid, "dataset": dataset_name or self.dataset_name}

    def visualize_graph_html(self, query: str | None = None, max_nodes: int = 300, depth: int = 2, dataset_name: str | None = None) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured", "html": ""}
        dsid = self.dataset_id(dataset_name)
        if not dsid:
            return {"available": False, "status": "DEGRADED", "reason": f"Cognee dataset not found: {dataset_name or self.dataset_name}", "html": ""}
        params = {"dataset_id": dsid, "max_nodes": max(1, int(max_nodes)), "neighborhood_depth": max(1, int(depth)), "full": False}
        if query:
            params["query"] = query
        try:
            resp = requests.get(self._url("api/v1/visualize"), headers=self._headers(), params=params, timeout=60)
            resp.raise_for_status()
            html = resp.text if isinstance(resp.text, str) else ""
            if "<html" not in html.lower():
                return {"available": False, "status": "DEGRADED", "reason": "Cognee visualize endpoint did not return HTML", "html": "", "dataset_id": dsid}
            return {"available": True, "status": "READY", "dataset_id": dsid, "dataset": dataset_name or self.dataset_name, "query": query, "html": html}
        except Exception as exc:
            return {"available": False, "status": "DEGRADED", "reason": str(exc), "html": "", "dataset_id": dsid}

    def remember_hypothesis(self, hypothesis: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "hypothesis", "hypothesis": hypothesis})

    def remember_outcome(self, outcome: dict[str, Any] | str) -> dict[str, Any]:
        return self.remember_research({"type": "outcome", "outcome": outcome})

    def remember_outcome_record(self, brief_id: str, symbol: str, outcome: str, lesson: str | None = None, observed_at: str | None = None, environment: str = "production") -> dict[str, Any]:
        record = build_outcome_memory(brief_id=brief_id, symbol=symbol, outcome=outcome, lesson=lesson, observed_at=observed_at, environment=environment)
        if not self.available:
            return {"available": False, "stored": False, "status": "DEGRADED", "reason": "COGNEE credentials not configured"}
        try:
            resp = requests.post(
                self._url("api/v1/add_text"),
                headers=self._headers(),
                json={"textData": [memory_to_cognee_text(record)], "datasetName": self.dataset_name, "nodeSet": ["fin_trading_research"]},
                timeout=30,
            )
            resp.raise_for_status()
            cog_resp = requests.post(self._url("api/v1/cognify"), headers=self._headers(), json={"datasets": [self.dataset_name], "runInBackground": False}, timeout=120)
            cog_resp.raise_for_status()
            return {"available": True, "stored": True, "status": "READY", "brief_id": brief_id, "symbol": symbol, "memory_type": "OutcomeLesson", "environment": environment}
        except Exception as exc:
            return {"available": False, "stored": False, "status": "DEGRADED", "reason": str(exc)}

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


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(str(url))
    if p.scheme not in {"http", "https"} or not p.netloc:
        return None
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", urlencode(qs), ""))


def _evidence_type(item: dict[str, Any]) -> str | None:
    import re
    text = " ".join(str(item.get(k) or "") for k in ["title", "snippet"]).lower()
    if not text:
        return None
    tokens = set(re.findall(r"[a-z0-9]+", text))
    if tokens & {"earnings", "guidance", "revenue", "forecast"}:
        return "earnings_guidance"
    if tokens & {"hbm", "ai", "datacenter"} or "data center" in text:
        return "ai_datacenter_demand"
    if tokens & {"export", "ban", "china", "restriction", "restrictions"}:
        return "policy_export_risk"
    return None


def build_structured_research_memories(report: dict[str, Any], environment: str = "production") -> list[dict[str, Any]]:
    brief_id = report.get("brief_id") or f"brief-{_utc_now()}"
    as_of = report.get("as_of") or report.get("timestamp") or report.get("generated_at")
    regime = report.get("regime_state") or report.get("market_regime") or {}
    qqq = regime.get("qqq", regime) if isinstance(regime, dict) else {}
    risk = report.get("risk_state") or report.get("risk") or {}
    hypothesis = report.get("hypothesis") or report.get("synthesis")
    recommendation_state = report.get("recommendation_state")
    memories: list[dict[str, Any]] = []

    memories.append({
        "environment": environment,
        "memory_type": "ResearchBrief",
        "brief_id": brief_id,
        "as_of": as_of,
        "relations": {"generated_under": "Regime:QQQ:SMA50", "contains_hypothesis": bool(hypothesis), "contains_risk": True},
        "hypothesis": hypothesis,
        "recommendation_state": recommendation_state,
    })

    allow_entries = None
    if isinstance(regime, dict):
        allow_entries = regime.get("risk_control", {}).get("new_entries_allowed")
    state = None
    if isinstance(qqq, dict):
        if qqq.get("qqq_above_sma50") is not None:
            state = "above_sma50" if qqq.get("qqq_above_sma50") else "below_sma50"
    memories.append({
        "environment": environment,
        "memory_type": "Regime",
        "regime_id": f"regime-{brief_id}-QQQ-SMA50",
        "brief_id": brief_id,
        "as_of": qqq.get("as_of") if isinstance(qqq, dict) else as_of,
        "benchmark": "QQQ",
        "indicator": "SMA50",
        "state": state,
        "allow_entries": allow_entries,
        "source": "deterministic_alpha_lab",
    })

    seen: set[str] = set()
    evidence_by_symbol: dict[str, list[str]] = {}
    evidence_urls_by_symbol: dict[str, list[str]] = {}
    for i, item in enumerate(report.get("external_evidence", []) or []):
        if not isinstance(item, dict) or item.get("available") is False:
            continue
        canon = canonical_url(item.get("url"))
        if not canon or canon in seen:
            continue
        seen.add(canon)
        sym = item.get("symbol")
        evidence_id = f"evidence-{brief_id}-{len(seen):03d}"
        evidence_by_symbol.setdefault(str(sym), []).append(evidence_id) if sym else None
        evidence_urls_by_symbol.setdefault(str(sym), []).append(canon) if sym else None
        etype = _evidence_type(item)
        memories.append({
            "environment": environment,
            "memory_type": "Evidence",
            "evidence_id": evidence_id,
            "brief_id": brief_id,
            "symbol": sym,
            "title": item.get("title"),
            "url": canon,
            "source": item.get("source"),
            "publisher": item.get("source"),
            "snippet": item.get("snippet"),
            "published_at": item.get("published_at"),
            "retrieved_at": item.get("retrieved_at"),
            "evidence_type": etype,
            "catalyst_type": etype,
            "query": item.get("query") or report.get("query"),
            "relevance_context": f"{sym} external evidence for {brief_id}" if sym else f"external evidence for {brief_id}",
            "relations": {"sourced_from": canon, "may_support": "Hypothesis" if hypothesis else None},
            "source_urls": [canon],
        })

    candidates = report.get("candidates") or report.get("quantitative_candidates") or []
    for row in candidates:
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        sym = str(row.get("symbol"))
        memories.append({
            "environment": environment,
            "memory_type": "SymbolMemory",
            "brief_id": brief_id,
            "symbol": sym,
            "as_of": row.get("as_of") or as_of,
            "rank": row.get("rank"),
            "signal_state": row.get("signal"),
            "regime_indicator": "QQQ_SMA50",
            "qqq_regime_state": state,
            "risk_summary": risk.get("notes", risk) if isinstance(risk, dict) else risk,
            "recommendation_state": recommendation_state,
            "hypothesis": hypothesis,
            "evidence_ids": evidence_by_symbol.get(sym, []),
            "source_urls": evidence_urls_by_symbol.get(sym, []),
            "outcome": report.get("outcome"),
            "lesson": report.get("lesson") or report.get("lessons"),
            "relations": {"evaluated_by": brief_id, "has_signal": row.get("signal"), "ranked_as": row.get("rank"), "generated_under": "Regime:QQQ:SMA50"},
        })
    return memories


def build_outcome_memory(brief_id: str, symbol: str, outcome: str, lesson: str | None = None, observed_at: str | None = None, environment: str = "production") -> dict[str, Any]:
    return {
        "environment": environment,
        "memory_type": "OutcomeLesson",
        "brief_id": brief_id,
        "symbol": symbol,
        "observed_at": observed_at or _utc_now(),
        "outcome": outcome,
        "lesson": lesson,
        "relations": {"evaluates": "Hypothesis", "produces": "Lesson" if lesson else None},
    }


def memory_to_cognee_text(memory: dict[str, Any]) -> str:
    mt = memory.get("memory_type", "Memory")
    parts = [f"FIN_TRADING_BRAIN_STRUCTURED_MEMORY memory_type={mt}", f"environment={memory.get('environment')}"]
    for key in ["brief_id", "symbol", "as_of", "regime_id", "benchmark", "indicator", "state", "allow_entries", "rank", "signal_state", "recommendation_state", "evidence_id", "title", "url", "source", "evidence_type", "hypothesis", "outcome", "lesson"]:
        val = memory.get(key)
        if val not in (None, "", []):
            parts.append(f"{key}={val}")
    rel = memory.get("relations")
    if isinstance(rel, dict):
        for k, v in rel.items():
            if v not in (None, "", []):
                parts.append(f"relation {mt} {k} {v}")
    return "\n".join(parts) + "\nJSON=" + _json_dumps(memory)


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


def _cap_graph(nodes: list[Any], links: list[Any], max_nodes: int) -> tuple[list[Any], list[Any]]:
    capped = nodes[: max(1, int(max_nodes))]
    ids = {str(n.get("id")) for n in capped if isinstance(n, dict) and n.get("id") is not None}
    if not ids:
        return capped, []
    capped_links = []
    for link in links:
        if not isinstance(link, dict):
            continue
        if str(link.get("source")) in ids and str(link.get("target")) in ids:
            capped_links.append(link)
    return capped, capped_links


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
