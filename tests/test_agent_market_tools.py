from agent.tools import market_tools


def test_market_regime_contract():
    r = market_tools.get_market_regime()
    assert r["available"]
    assert "risk_control" in r
    assert r["risk_control"]["rule"] == "qqq_sma50_gate"
    assert r["risk_control"]["exposure_multiplier"] in (0.0, 1.0)


def test_qqq_regime_positive_or_negative_state():
    q = market_tools.get_qqq_regime()
    assert q["available"]
    assert isinstance(q["qqq_above_sma50"], bool)
    assert q["qqq_trend"] in {"positive", "negative"}


def test_exposure_multiplier_matches_gate():
    q = market_tools.get_qqq_regime()
    e = market_tools.get_exposure_multiplier()
    assert e["new_entries_allowed"] == q["qqq_above_sma50"]
    assert e["exposure_multiplier"] == (1.0 if q["qqq_above_sma50"] else 0.0)
