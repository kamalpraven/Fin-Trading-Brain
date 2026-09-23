from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from typing import Any

from agent.config import integration_status, load_agent_config
from agent.prompts import DAILY_RESEARCH_QUERY, SYSTEM_PROMPT
from agent.schemas import ResearchBrief, validate_brief
from agent.tools import alpha_tools, brightdata_tools, market_tools, memory_tools

SUPPORTED_ACTIONS = {"candidate", "watch", "blocked_by_regime", "needs_more_evidence"}
REGISTERED_TOOLS = [
    "get_strategy_config", "get_semiconductor_universe", "get_latest_rankings", "get_signal_for_symbol",
    "get_market_regime", "get_qqq_regime", "get_exposure_multiplier",
    "search_web", "research_symbol", "recall_similar_setups", "store_daily_research",
]


class ResearchAgent:
    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT
        self.integration_status = integration_status()
        self.strands_agent = None
        try:
            from strands import Agent  # type: ignore
            cfg = load_agent_config()
            kwargs = {"system_prompt": SYSTEM_PROMPT}
            if cfg.strands_model_id:
                kwargs["model"] = cfg.strands_model_id
            self.strands_agent = Agent(**kwargs)
            self.integration_status["strands"] = {"available": True, "mode": "strands"}
        except Exception as exc:
            self.integration_status["strands"] = {"available": False, "mode": "local_fallback", "reason": str(exc)}

    @property
    def registered_tools(self) -> list[str]:
        return REGISTERED_TOOLS.copy()

    def run(self, query: str) -> dict[str, Any]:
        return run_research_agent(query, agent=self)


def create_research_agent() -> ResearchAgent:
    return ResearchAgent()


def _extract_symbol(query: str) -> str | None:
    universe = alpha_tools.get_semiconductor_universe().get("symbols", [])
    tokens = re.findall(r"\b[A-Z]{2,5}\b", query.upper())
    for token in tokens:
        if token in universe:
            return token
    return None


def _external_evidence(query: str, symbols: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence = []
    failures = []
    attempted_at = datetime.now(timezone.utc).isoformat()
    if symbols:
        for sym in symbols[:3]:
            res = brightdata_tools.research_symbol(sym)
            if res.get("available"):
                for item in res.get("results", []):
                    evidence.append({"symbol": sym, **item})
            else:
                failures.append({"symbol": sym, "reason": res.get("reason"), "status": res.get("status", "DEGRADED")})
    else:
        res = brightdata_tools.get_recent_semiconductor_news()
        if res.get("available"):
            evidence.extend(res.get("results", []))
        else:
            failures.append({"reason": res.get("reason"), "status": res.get("status", "DEGRADED")})
    if evidence:
        brightdata_tools.save_last_good_evidence(evidence, query=query)
        return evidence, {"brightdata_status": "READY", "brightdata_attempted_at": attempted_at, "brightdata_failure_reason": None, "evidence_freshness_summary": {"fresh": len(evidence), "stale_fallback": 0, "unknown": 0}}
    reason = "; ".join(f.get("reason") or "unknown" for f in failures) or "Bright Data unavailable"
    has_config_fail = any(f.get("status") == "FAIL" and "credentials not configured" in str(f.get("reason")) for f in failures)
    if not has_config_fail:
        stale = brightdata_tools.mark_stale_fallback(brightdata_tools.load_last_good_evidence(), attempted_at, reason)
        if stale:
            return stale, {"brightdata_status": "DEGRADED", "brightdata_attempted_at": attempted_at, "brightdata_failure_reason": reason, "evidence_freshness_summary": {"fresh": 0, "stale_fallback": len(stale), "unknown": 0}}
    return [{"available": False, "reason": reason}], {"brightdata_status": "DEGRADED", "brightdata_attempted_at": attempted_at, "brightdata_failure_reason": reason, "evidence_freshness_summary": {"fresh": 0, "stale_fallback": 0, "unknown": 0}}


def _memory_context(query: str, symbol: str | None) -> list[dict[str, Any]]:
    res = memory_tools.recall_symbol_history(symbol) if symbol else memory_tools.recall_similar_setups(query)
    if res.get("available"):
        return res.get("memories", [])
    return [{"available": False, "reason": res.get("reason")}]


def _candidate_actions(rankings: dict[str, Any], regime: dict[str, Any], symbol: str | None = None) -> list[dict[str, Any]]:
    allowed = bool(regime.get("risk_control", {}).get("new_entries_allowed", False))
    rows = rankings.get("symbols", []) if rankings.get("available") else []
    if symbol:
        rows = [r for r in rows if r.get("symbol") == symbol]
    out = []
    for row in rows[:5]:
        if not allowed:
            status = "blocked_by_regime"
            rationale = "QQQ SMA50 gate currently blocks new long entries; existing positions would follow deterministic exits."
        elif row.get("raw_signal"):
            status = "candidate"
            rationale = "Deterministic strategy signal is active and QQQ SMA50 gate permits new entries."
        else:
            status = "watch"
            rationale = "Supported symbol, but latest deterministic entry signal is not active."
        out.append({"symbol": row.get("symbol"), "status": status, "rationale": rationale})
    if symbol and not out:
        out.append({"symbol": symbol, "status": "needs_more_evidence", "rationale": "Symbol is unsupported or quantitative state unavailable."})
    return out


def _extract_catalysts(evidence: list[dict[str, Any]], symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    out = {s: [] for s in symbols}
    for item in evidence:
        sym = item.get("symbol")
        if sym not in out or item.get("available") is False:
            continue
        text = " ".join([str(item.get("title") or ""), str(item.get("snippet") or "")]).strip()
        out[sym].append({"catalyst": text[:240] or "External evidence item", "evidence": item.get("snippet"), "source": item.get("url"), "published_at": item.get("published_at"), "retrieved_at": item.get("retrieved_at"), "source_quality": item.get("source_quality")})
    return {k: v[:3] for k, v in out.items()}


def _detect_conflicts(evidence: list[dict[str, Any]], symbols: list[str]) -> dict[str, dict[str, list[str]]]:
    pos_words = ["demand", "growth", "beat", "raise", "expansion", "strong", "ai", "hbm"]
    neg_words = ["weak", "cut", "miss", "lower", "guidance", "delay", "ban", "export", "decline"]
    out: dict[str, dict[str, list[str]]] = {}
    for sym in symbols:
        pos: list[str] = []; neg: list[str] = []
        for item in evidence:
            if item.get("symbol") != sym or item.get("available") is False: continue
            text = " ".join([str(item.get("title") or ""), str(item.get("snippet") or "")]).lower()
            title = str(item.get("title") or item.get("url"))[:180]
            if any(w in text for w in pos_words): pos.append(title)
            if any(w in text for w in neg_words): neg.append(title)
        if pos or neg:
            out[sym] = {"positive": pos[:3], "negative": neg[:3]}
    return out


def _strands_synthesis(agent: ResearchAgent, facts: dict[str, Any]) -> str | None:
    if not agent.strands_agent:
        return None
    prompt = "Synthesize only from these tool-provided facts. Do not add quantitative facts. Research-only, no orders.\n" + json.dumps(facts, default=str)[:12000]
    try:
        return str(agent.strands_agent(prompt))
    except Exception as exc:
        agent.integration_status["strands"] = {"available": False, "mode": "local_fallback", "reason": str(exc)}
        return None


def _synthesis(query: str, regime: dict[str, Any], rankings: dict[str, Any], evidence: list[dict[str, Any]], memory: list[dict[str, Any]]) -> str:
    allowed = regime.get("risk_control", {}).get("new_entries_allowed")
    gate = "allows" if allowed else "blocks"
    top = rankings.get("symbols", [])[:3] if rankings.get("available") else []
    top_txt = ", ".join([f"{r['symbol']}({r['signal']})" for r in top]) or "unavailable"
    ext = "available" if evidence and evidence[0].get("available", True) else "unavailable"
    mem = "available" if memory and memory[0].get("available", True) else "unavailable"
    return f"Deterministic Alpha Lab state ranks: {top_txt}. The validated QQQ SMA50 risk gate currently {gate} new entries. External Bright Data evidence is {ext}; Cognee memory is {mem}. This is research context only; no trades executed."


def build_research_brief(query: str, agent: ResearchAgent | None = None) -> ResearchBrief:
    agent = agent or create_research_agent()
    symbol = _extract_symbol(query)
    regime = market_tools.get_market_regime()
    rankings = alpha_tools.get_latest_rankings()
    quant_state = {
        "strategy_config": alpha_tools.get_strategy_config(),
        "latest_rankings_available": rankings.get("available", False),
        "backtest_summary": alpha_tools.get_backtest_summary(),
        "cost_sensitivity": alpha_tools.get_cost_sensitivity_summary(),
    }
    target_symbols = [symbol] if symbol else [r["symbol"] for r in rankings.get("symbols", [])[:3]]
    evidence, brightdata_meta = _external_evidence(query, target_symbols)
    memory = _memory_context(query, symbol)
    actions = _candidate_actions(rankings, regime, symbol)
    top_symbols = [r.get("symbol") for r in rankings.get("symbols", [])[:5] if r.get("symbol")]
    catalysts = _extract_catalysts(evidence, top_symbols)
    conflicts = _detect_conflicts(evidence, top_symbols)
    facts = {"query": query, "regime": regime, "rankings": rankings, "evidence": evidence[:10], "memory": memory[:5], "catalysts": catalysts, "conflicts": conflicts}
    synthesis = _strands_synthesis(agent, facts) or _synthesis(query, regime, rankings, evidence, memory)
    quant_as_of = rankings.get("as_of") or regime.get("qqq", {}).get("as_of")
    external_retrieved = [x.get("retrieved_at") for x in evidence if x.get("retrieved_at")]
    brief = ResearchBrief(
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=query,
        market_regime=regime,
        quantitative_state=quant_state,
        quantitative_candidates=rankings.get("symbols", []) if rankings.get("available") else [],
        external_evidence=evidence,
        memory_context=memory,
        risk={"primary_rule": "qqq_sma50_gate", "no_trading": True, "notes": ["Semiconductor sector concentration", "Strategy remains cost-sensitive", "News is contextual only"]},
        candidate_actions=actions,
        synthesis=synthesis,
        catalysts=catalysts,
        conflicts=conflicts,
        data_freshness={"quant_data_as_of": quant_as_of, "quant_data_status": "historical/cached Alpha Lab data", "external_research_retrieved_at": max(external_retrieved) if external_retrieved else None, "external_research_status": "current live web retrieval when Bright Data available; stale_fallback is explicitly labeled", "memory_status": "prior research recalled from Cognee when available", **brightdata_meta},
        limitations=["Research-only; no order execution tools exist", "Bright Data/Cognee may be unavailable if credentials are not configured", "Web evidence is not a direct trading signal", "Quant rankings are historical/cached unless data artifacts are refreshed"] + (["Live Bright Data unavailable; using explicitly labeled stale fallback evidence" if brightdata_meta.get("evidence_freshness_summary", {}).get("stale_fallback") else "Live Bright Data unavailable; no external evidence included"] if brightdata_meta.get("brightdata_status") == "DEGRADED" else []),
        integration_status=agent.integration_status,
    )
    return brief


def _daily_recommendation_state(actions: list[dict[str, Any]]) -> str:
    statuses = {str(a.get("status", "")).lower() for a in actions}
    if "blocked_by_regime" in statuses:
        return "BLOCKED"
    if "candidate" in statuses:
        return "CANDIDATE"
    return "WATCH"


def _source_list(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for item in evidence:
        url = item.get("url")
        if not url or url in seen or item.get("available") is False:
            continue
        seen.add(url)
        out.append({"title": item.get("title"), "url": url, "source": item.get("source"), "published_at": item.get("published_at"), "retrieved_at": item.get("retrieved_at")})
    return out


def run_research_agent(query: str, agent: ResearchAgent | None = None, persist: bool = False, save: bool = False) -> dict[str, Any]:
    brief = build_research_brief(query, agent)
    obj = brief.to_dict()
    generated_at = datetime.now(timezone.utc).isoformat()
    obj["brief_id"] = f"brief-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    obj["generated_at"] = generated_at
    obj["as_of"] = obj.get("data_freshness", {}).get("quant_data_as_of") or generated_at
    obj["quant_state"] = obj.get("quantitative_state", {})
    obj["regime_state"] = obj.get("market_regime", {})
    obj["risk_state"] = obj.get("risk", {})
    obj["candidates"] = obj.get("quantitative_candidates", [])
    obj["recommendation_state"] = _daily_recommendation_state(obj.get("candidate_actions", []))
    obj["sources"] = _source_list(obj.get("external_evidence", []))
    fresh = obj.get("data_freshness", {})
    obj["brightdata_status"] = fresh.get("brightdata_status")
    obj["brightdata_attempted_at"] = fresh.get("brightdata_attempted_at")
    obj["brightdata_failure_reason"] = fresh.get("brightdata_failure_reason")
    obj["evidence_freshness_summary"] = fresh.get("evidence_freshness_summary")
    obj["hypothesis"] = obj.get("synthesis", "")
    obj["outcome"] = "research_only_no_trades"
    obj["lessons"] = []
    if not validate_brief(obj):
        raise ValueError("research brief failed schema validation")
    if persist:
        obj["memory_store_result"] = memory_tools.store_daily_research(obj)
    if save:
        obj["artifact_path"] = save_brief(obj)
    return obj


def run_daily_research(persist: bool = True, save: bool = True) -> dict[str, Any]:
    return run_research_agent(DAILY_RESEARCH_QUERY, persist=persist, save=save)


def save_brief(brief: dict[str, Any]) -> str:
    cfg = load_agent_config()
    out = Path(cfg.results_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out / f"daily_research_{ts}.json"
    path.write_text(json.dumps(brief, indent=2, default=str), encoding="utf-8")
    return str(path)


def format_brief(brief: dict[str, Any]) -> str:
    regime = brief.get("market_regime", {}).get("risk_control", {})
    qqq = brief.get("market_regime", {}).get("qqq", {})
    fresh = brief.get("data_freshness", {})
    lines = ["FIN TRADING BRAIN", "", "AS OF", f"Quant data: {fresh.get('quant_data_as_of')} ({fresh.get('quant_data_status')})", f"External research retrieved: {fresh.get('external_research_retrieved_at')}", "", "MARKET REGIME"]
    lines.append(f"QQQ > SMA50: {qqq.get('qqq_above_sma50')}")
    lines.append(f"New entries: {'allowed' if regime.get('new_entries_allowed') else 'blocked'}")
    lines += ["", "QUANTITATIVE RANKING"]
    for r in brief.get("quantitative_candidates", [])[:5]:
        lines.append(f"{r.get('rank')}. {r.get('symbol')} - {r.get('signal')}")
    lines += ["", "CURRENT CATALYSTS / EVIDENCE"]
    ev = brief.get("external_evidence", [])
    if ev and ev[0].get("available", True) is False:
        lines.append(f"Unavailable: {ev[0].get('reason')}")
    else:
        for item in ev[:5]:
            lines.append(f"- {item.get('symbol', '')} {item.get('title')} ({item.get('url')})")
    lines += ["", "MEMORY"]
    mem = brief.get("memory_context", [])
    lines.append("Unavailable: " + str(mem[0].get("reason")) if mem and mem[0].get("available") is False else f"{len(mem)} memory items")
    if brief.get("conflicts"):
        lines += ["", "CONFLICTS"]
        for sym, c in brief.get("conflicts", {}).items():
            if c.get("positive") and c.get("negative"):
                lines.append(f"{sym}: positive={len(c.get('positive', []))}, negative={len(c.get('negative', []))}")
    lines += ["", "SYSTEM RISK"]
    for n in brief.get("risk", {}).get("notes", []):
        lines.append(f"- {n}")
    lines += ["", "RESEARCH STATUS"]
    for a in brief.get("candidate_actions", []):
        lines.append(f"{a.get('symbol')}: {a.get('status')}")
    lines += ["", "No trades executed."]
    return "\n".join(lines)
