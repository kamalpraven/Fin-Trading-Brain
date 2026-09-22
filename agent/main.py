from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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
            self.strands_agent = Agent(system_prompt=SYSTEM_PROMPT)
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


def _external_evidence(query: str, symbols: list[str]) -> list[dict[str, Any]]:
    evidence = []
    if symbols:
        for sym in symbols[:3]:
            res = brightdata_tools.research_symbol(sym)
            if res.get("available"):
                for item in res.get("results", []):
                    evidence.append({"symbol": sym, **item})
            else:
                evidence.append({"symbol": sym, "available": False, "reason": res.get("reason")})
    else:
        res = brightdata_tools.get_recent_semiconductor_news()
        if res.get("available"):
            evidence.extend(res.get("results", []))
        else:
            evidence.append({"available": False, "reason": res.get("reason")})
    return evidence


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
    evidence = _external_evidence(query, target_symbols)
    memory = _memory_context(query, symbol)
    actions = _candidate_actions(rankings, regime, symbol)
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
        synthesis=_synthesis(query, regime, rankings, evidence, memory),
        limitations=["Research-only; no order execution tools exist", "Bright Data/Cognee may be unavailable if credentials are not configured", "Web evidence is not a direct trading signal"],
        integration_status=agent.integration_status,
    )
    return brief


def run_research_agent(query: str, agent: ResearchAgent | None = None, persist: bool = False, save: bool = False) -> dict[str, Any]:
    brief = build_research_brief(query, agent)
    obj = brief.to_dict()
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
    lines = ["SEMICONDUCTOR RESEARCH BRIEF", "", "REGIME"]
    lines.append(f"QQQ > SMA50: {qqq.get('qqq_above_sma50')}")
    lines.append(f"New entries: {'allowed' if regime.get('new_entries_allowed') else 'blocked'}")
    lines += ["", "QUANTITATIVE RANKING"]
    for r in brief.get("quantitative_candidates", [])[:5]:
        lines.append(f"{r.get('rank')}. {r.get('symbol')} - {r.get('signal')}")
    lines += ["", "CURRENT EVIDENCE"]
    ev = brief.get("external_evidence", [])
    if ev and ev[0].get("available", True) is False:
        lines.append(f"Unavailable: {ev[0].get('reason')}")
    else:
        for item in ev[:5]:
            lines.append(f"- {item.get('symbol', '')} {item.get('title')} ({item.get('url')})")
    lines += ["", "MEMORY"]
    mem = brief.get("memory_context", [])
    lines.append("Unavailable: " + str(mem[0].get("reason")) if mem and mem[0].get("available") is False else f"{len(mem)} memory items")
    lines += ["", "RISK"]
    for n in brief.get("risk", {}).get("notes", []):
        lines.append(f"- {n}")
    lines += ["", "RESEARCH STATUS"]
    for a in brief.get("candidate_actions", []):
        lines.append(f"{a.get('symbol')}: {a.get('status')}")
    lines += ["", "No trades executed."]
    return "\n".join(lines)
