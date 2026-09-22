from agent.main import create_research_agent, run_research_agent
from agent.schemas import validate_brief


def test_agent_tool_registration_has_no_trading_tools():
    a = create_research_agent()
    names = " ".join(a.registered_tools).lower()
    assert "order" not in names and "buy" not in names and "sell" not in names


def test_research_brief_schema_and_disabled_integrations(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("COGNEE_API_KEY", raising=False)
    b = run_research_agent("Analyze MU")
    assert validate_brief(b)
    assert b["external_evidence"][0]["available"] is False


def test_current_news_cannot_override_regime_gate(monkeypatch):
    from agent import main
    monkeypatch.setattr(main.market_tools, "get_market_regime", lambda: {"available": True, "risk_control": {"new_entries_allowed": False, "exposure_multiplier": 0.0}, "qqq": {"qqq_above_sma50": False}})
    monkeypatch.setattr(main.alpha_tools, "get_latest_rankings", lambda: {"available": True, "symbols": [{"symbol": "MU", "rank": 1, "signal": "candidate", "raw_signal": True, "score": 1}]})
    monkeypatch.setattr(main.brightdata_tools, "research_symbol", lambda s: {"available": True, "results": [{"title": "positive", "url": "u"}]})
    b = run_research_agent("Analyze MU")
    assert b["candidate_actions"][0]["status"] == "blocked_by_regime"


def test_unsupported_symbol_handled_safely():
    b = run_research_agent("Analyze XYZ")
    assert validate_brief(b)
    assert all(a["status"] in {"candidate", "watch", "blocked_by_regime", "needs_more_evidence"} for a in b["candidate_actions"])
