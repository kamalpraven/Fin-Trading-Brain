from pathlib import Path
import json

from agent.memory.cognee_client import build_outcome_memory, build_structured_research_memories, memory_to_cognee_text


def sample_report():
    return {
        "brief_id": "brief-test-1",
        "as_of": "2026-09-18T00:00:00Z",
        "query": "daily research",
        "recommendation_state": "CANDIDATE",
        "hypothesis": "Deterministic hypothesis",
        "regime_state": {"qqq": {"as_of": "2026-09-18T00:00:00Z", "qqq_above_sma50": True}, "risk_control": {"new_entries_allowed": True}},
        "risk_state": {"notes": ["Semiconductor sector concentration"]},
        "candidates": [
            {"rank": 1, "symbol": "AMAT", "signal": "candidate", "as_of": "2026-09-18T00:00:00Z"},
            {"rank": 2, "symbol": "MU", "signal": "watch", "as_of": "2026-09-18T00:00:00Z"},
        ],
        "external_evidence": [
            {"symbol": "AMAT", "title": "AMAT earnings guidance", "url": "https://example.com/a?utm_source=x", "source": "example.com", "snippet": "AI demand", "retrieved_at": "2026-09-23T00:00:00Z"},
            {"symbol": "AMAT", "title": "Duplicate", "url": "https://example.com/a", "source": "example.com", "snippet": "duplicate", "retrieved_at": "2026-09-23T00:00:01Z"},
            {"symbol": "MU", "title": "Unknown catalyst", "url": "https://example.org/mu", "snippet": "plain text", "retrieved_at": "2026-09-23T00:00:02Z"},
        ],
    }


def test_structured_research_memory_schema():
    mem = build_structured_research_memories(sample_report())
    types = {m["memory_type"] for m in mem}
    assert {"ResearchBrief", "Regime", "Evidence", "SymbolMemory"} <= types
    assert all(m["environment"] == "production" for m in mem)
    assert all(m.get("brief_id") == "brief-test-1" for m in mem if m["memory_type"] != "Regime" or m.get("brief_id"))


def test_evidence_url_preservation_and_deduplication():
    ev = [m for m in build_structured_research_memories(sample_report()) if m["memory_type"] == "Evidence"]
    assert len(ev) == 2
    urls = [e["url"] for e in ev]
    assert "https://example.com/a" in urls
    assert "https://example.org/mu" in urls


def test_no_fabricated_metadata_for_missing_values():
    ev = [m for m in build_structured_research_memories(sample_report()) if m["memory_type"] == "Evidence" and m["symbol"] == "MU"][0]
    assert ev["published_at"] is None
    assert ev["source"] is None
    assert ev["evidence_type"] is None


def test_symbol_memory_linkage():
    symbols = [m for m in build_structured_research_memories(sample_report()) if m["memory_type"] == "SymbolMemory"]
    amat = [m for m in symbols if m["symbol"] == "AMAT"][0]
    assert amat["rank"] == 1
    assert amat["signal_state"] == "candidate"
    assert amat["evidence_ids"]
    assert amat["source_urls"] == ["https://example.com/a"]


def test_regime_memory_structure():
    reg = [m for m in build_structured_research_memories(sample_report()) if m["memory_type"] == "Regime"][0]
    assert reg["benchmark"] == "QQQ"
    assert reg["indicator"] == "SMA50"
    assert reg["state"] == "above_sma50"
    assert reg["allow_entries"] is True
    assert reg["source"] == "deterministic_alpha_lab"


def test_test_tagging_supported():
    mem = build_structured_research_memories(sample_report(), environment="test")
    assert all(m["environment"] == "test" for m in mem)


def test_existing_prose_memory_compatibility(monkeypatch):
    from agent.memory.cognee_client import compact_research_summary
    compact = compact_research_summary(sample_report())
    assert compact["brief_id"] == "brief-test-1"
    assert "evidence_summary" in compact


def test_outcome_lesson_foundation():
    rec = build_outcome_memory("brief-test-1", "AMAT", "watched_only", "lesson text", "2026-10-01T00:00:00Z")
    assert rec["memory_type"] == "OutcomeLesson"
    assert rec["relations"]["evaluates"] == "Hypothesis"
    assert rec["relations"]["produces"] == "Lesson"


def test_no_credentials_in_stored_payload():
    rec = build_structured_research_memories(sample_report())[0]
    text = memory_to_cognee_text(rec)
    assert "COGNEE_API_KEY" not in text
    assert "secret" not in text.lower()


def test_allow_orders_false_and_no_trading_actions():
    assert "ALLOW_ORDERS=false" in Path(".env.example").read_text(encoding="utf-8")
    text = "\n".join(memory_to_cognee_text(m) for m in build_structured_research_memories(sample_report()))
    assert "execute_order" not in text
    assert "place_order" not in text
