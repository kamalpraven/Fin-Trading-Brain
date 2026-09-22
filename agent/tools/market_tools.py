from __future__ import annotations

from typing import Any

import pandas as pd

from alpha_lab.data import load_cached
from alpha_lab.regime import RegimeSpec, build_regime_controls, trend_state, volatility_state

M4_EVIDENCE = {"m4_5bps_pf": 1.1495, "m4_10bps_pf": 1.0688, "m4_2022_drawdown": -0.1708}


def _load() -> pd.DataFrame:
    return load_cached("daily_bars")


def get_qqq_regime() -> dict[str, Any]:
    try:
        df = _load()
        st = trend_state(df, "QQQ", 50).iloc[-1]
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    above = bool(st["qqq_above_sma50"])
    return {
        "available": True,
        "as_of": str(st["timestamp"]),
        "qqq_close": float(st["qqq_close"]),
        "qqq_sma50": float(st["qqq_sma50"]),
        "qqq_above_sma50": above,
        "qqq_trend": "positive" if above else "negative",
    }


def get_spy_regime() -> dict[str, Any]:
    try:
        df = _load(); st = trend_state(df, "SPY", 50).iloc[-1]
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    above = bool(st["spy_above_sma50"])
    return {"available": True, "as_of": str(st["timestamp"]), "spy_close": float(st["spy_close"]), "spy_sma50": float(st["spy_sma50"]), "spy_above_sma50": above, "spy_trend": "positive" if above else "negative"}


def get_volatility_regime() -> dict[str, Any]:
    try:
        df = _load(); st = volatility_state(df, "QQQ", 10, 0.67).iloc[-1]
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    return {"available": True, "as_of": str(st["timestamp"]), "qqq_rv10": None if pd.isna(st["qqq_rv10"]) else float(st["qqq_rv10"]), "threshold": None if pd.isna(st["qqq_vol_threshold"]) else float(st["qqq_vol_threshold"]), "high_vol": bool(st["high_vol"]), "volatility_regime": "high_vol" if bool(st["high_vol"]) else "normal_vol"}


def get_exposure_multiplier() -> dict[str, Any]:
    q = get_qqq_regime()
    if not q.get("available"):
        return q
    allowed = bool(q["qqq_above_sma50"])
    return {"available": True, "rule": "qqq_sma50_gate", "new_entries_allowed": allowed, "exposure_multiplier": 1.0 if allowed else 0.0, "existing_positions": "follow_existing_exit_rules", "evidence": M4_EVIDENCE}


def get_market_regime() -> dict[str, Any]:
    q = get_qqq_regime(); s = get_spy_regime(); v = get_volatility_regime(); e = get_exposure_multiplier()
    return {"available": all(x.get("available") for x in [q, s, v, e]), "qqq": q, "spy": s, "volatility": v, "risk_control": e}


def get_regime_research_summary() -> dict[str, Any]:
    return {"available": True, "preferred_rule": "qqq_sma50_gate", "classification": "PROMISING BUT STILL REGIME-SENSITIVE", "rationale": "Milestone 4 showed QQQ SMA50 gate reduced 2022 drawdown and improved PF/Sharpe while preserving most return.", "evidence": M4_EVIDENCE}


def controls_for_primary_gate() -> pd.DataFrame:
    return build_regime_controls(_load(), RegimeSpec("qqq_sma50_gate", "trend_gate", symbol="QQQ", sma_days=50))
