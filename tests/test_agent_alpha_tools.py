from agent.tools import alpha_tools


def test_alpha_tools_universe_and_rankings():
    u = alpha_tools.get_semiconductor_universe()
    assert u["available"] and "NVDA" in u["symbols"]
    r = alpha_tools.get_latest_rankings()
    assert r["available"]
    assert all("symbol" in x and "rank" in x for x in r["symbols"])


def test_alpha_invalid_ticker_handling():
    out = alpha_tools.get_signal_for_symbol("XYZ")
    assert out["available"] is False
    assert "unsupported" in out["reason"]


def test_missing_artifact_handling(monkeypatch, tmp_path):
    monkeypatch.setattr(alpha_tools, "M4_DIR", tmp_path)
    out = alpha_tools.get_cost_sensitivity_summary()
    assert out["available"] is False
    assert "missing artifact" in out["reason"]
