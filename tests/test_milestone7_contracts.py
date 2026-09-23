import json
from pathlib import Path

from agent.config import integration_status, load_agent_config
from agent.main import create_research_agent, run_daily_research, run_research_agent
from agent.memory.cognee_client import compact_research_summary
from agent.tools import brightdata_tools


class Resp:
    def __init__(self, status_code=200, payload=None, text="ok"):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")
    def json(self):
        return self._payload


def test_aws_bedrock_not_required(monkeypatch):
    for k in ["AWS_REGION", "AWS_PROFILE", "STRANDS_MODEL_ID"]:
        monkeypatch.delenv(k, raising=False)
    status = integration_status()
    assert status["aws_bedrock"]["required"] is False
    assert run_research_agent("Analyze MU")["synthesis"]


def test_cognee_persistence_contract_contains_required_fields():
    summary = compact_research_summary({
        "brief_id": "b1", "as_of": "2026-09-23T00:00:00Z", "candidates": [{"rank": 1, "symbol": "MU", "signal": "candidate", "as_of": "2026-09-22"}],
        "regime_state": {"qqq": {"qqq_above_sma50": True}}, "risk_state": {"notes": ["risk"]},
        "external_evidence": [{"symbol": "MU", "title": "real", "url": "https://example.com/a", "source": "example", "retrieved_at": "now"}],
        "hypothesis": "h", "outcome": "o", "lessons": ["l"],
    })
    assert {"brief_id", "as_of", "symbol", "regime", "ranking", "evidence_summary", "risk_summary", "hypothesis", "outcome", "lessons"} <= set(summary)
    assert summary["evidence_summary"][0]["url"].startswith("https://")


def test_brightdata_url_dedupe_and_fresh_timestamps(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "x")
    monkeypatch.setenv("BRIGHTDATA_MCP_URL", "https://brightdata.test/search")
    payload = {"results": [
        {"title": "A", "url": "https://Example.com/a/?utm_source=x", "snippet": "s"},
        {"title": "A dup", "url": "https://example.com/a", "snippet": "s2"},
    ]}
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(payload=payload))
    out = brightdata_tools.search_web("MU")
    assert out["available"]
    assert len(out["results"]) == 1
    assert out["results"][0]["retrieved_at"]
    assert out["retrieved_at"]


def test_brightdata_nested_error_handling(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "x")
    monkeypatch.setenv("BRIGHTDATA_MCP_URL", "https://brightdata.test/search")
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(payload={"error": {"message": "bad zone"}}))
    out = brightdata_tools.search_web("MU")
    assert out["available"] is False
    assert "bad zone" in out["reason"]


def test_no_fabricated_sources_from_malformed_brightdata(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "x")
    monkeypatch.setenv("BRIGHTDATA_MCP_URL", "https://brightdata.test/search")
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(payload={"results": [{"title": "No URL", "snippet": "x"}]}))
    out = brightdata_tools.search_web("MU")
    assert out["available"] is False
    assert out["results"] == []


def test_allow_orders_false_in_example():
    assert "ALLOW_ORDERS=false" in Path(".env.example").read_text(encoding="utf-8")


def test_daily_research_required_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RESULTS_DIR", str(tmp_path))
    b = run_daily_research(persist=False, save=True)
    required = {"brief_id", "as_of", "generated_at", "quant_state", "regime_state", "risk_state", "candidates", "external_evidence", "memory_context", "conflicts", "limitations", "recommendation_state", "sources"}
    assert required <= set(b)
    assert b["recommendation_state"] in {"CANDIDATE", "WATCH", "BLOCKED"}
    assert Path(b["artifact_path"]).exists()


def test_no_trading_tool_exposure_extra():
    names = " ".join(create_research_agent().registered_tools).lower()
    assert all(word not in names for word in ["order", "trade", "buy", "sell"])
