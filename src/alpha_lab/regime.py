from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegimeSpec:
    name: str
    kind: str = "none"  # none, trend_gate, trend_reduce, vol_reduce, vol_cash, combined
    symbol: str = "QQQ"
    sma_days: int = 50
    below_multiplier: float = 1.0
    high_vol_multiplier: float = 1.0
    vol_days: int = 10
    vol_quantile: float = 0.67


def _base_dates(bars: pd.DataFrame) -> pd.DataFrame:
    dates = pd.DataFrame({"timestamp": sorted(pd.to_datetime(bars["timestamp"]).unique())})
    dates["allow_entries"] = True
    dates["exposure_multiplier"] = 1.0
    return dates


def trend_state(bars: pd.DataFrame, symbol: str = "QQQ", sma_days: int = 50) -> pd.DataFrame:
    x = bars[bars["symbol"] == symbol].sort_values("timestamp").reset_index(drop=True).copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"])
    x["sma"] = x["close"].rolling(sma_days).mean()
    x[f"{symbol.lower()}_above_sma{sma_days}"] = x["close"] > x["sma"]
    return x[["timestamp", "close", "sma", f"{symbol.lower()}_above_sma{sma_days}"]].rename(columns={"close": f"{symbol.lower()}_close", "sma": f"{symbol.lower()}_sma{sma_days}"})


def volatility_state(bars: pd.DataFrame, symbol: str = "QQQ", vol_days: int = 10, quantile: float = 0.67) -> pd.DataFrame:
    x = bars[bars["symbol"] == symbol].sort_values("timestamp").reset_index(drop=True).copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"])
    ret = x["close"].pct_change()
    vol = ret.rolling(vol_days).std() * np.sqrt(252)
    threshold = vol.shift(1).expanding().quantile(quantile)
    x[f"{symbol.lower()}_rv{vol_days}"] = vol
    x[f"{symbol.lower()}_vol_threshold"] = threshold
    x["high_vol"] = vol > threshold
    return x[["timestamp", f"{symbol.lower()}_rv{vol_days}", f"{symbol.lower()}_vol_threshold", "high_vol"]]


def build_regime_controls(bars: pd.DataFrame, spec: RegimeSpec) -> pd.DataFrame:
    controls = _base_dates(bars)
    if spec.kind == "none":
        controls["regime_name"] = spec.name
        return controls

    if spec.kind in {"trend_gate", "trend_reduce", "combined"}:
        tr = trend_state(bars, spec.symbol, spec.sma_days)
        flag = f"{spec.symbol.lower()}_above_sma{spec.sma_days}"
        controls = controls.merge(tr, on="timestamp", how="left")
        below = ~controls[flag].fillna(False)
        if spec.kind == "trend_gate":
            controls.loc[below, "allow_entries"] = False
            controls.loc[below, "exposure_multiplier"] = 0.0
        elif spec.kind == "trend_reduce":
            controls.loc[below, "exposure_multiplier"] = spec.below_multiplier
        elif spec.kind == "combined":
            controls.loc[below, "exposure_multiplier"] = spec.below_multiplier
            if spec.below_multiplier <= 0:
                controls.loc[below, "allow_entries"] = False

    if spec.kind in {"vol_reduce", "vol_cash", "combined"}:
        vol = volatility_state(bars, "QQQ", spec.vol_days, spec.vol_quantile)
        controls = controls.merge(vol, on="timestamp", how="left")
        high = controls["high_vol"].fillna(False)
        mult = 0.0 if spec.kind == "vol_cash" else spec.high_vol_multiplier
        controls.loc[high, "exposure_multiplier"] = np.minimum(controls.loc[high, "exposure_multiplier"], mult)
        if mult <= 0:
            controls.loc[high, "allow_entries"] = False

    controls["regime_name"] = spec.name
    controls["regime_label"] = np.where(controls["exposure_multiplier"] >= 1.0, "normal", np.where(controls["exposure_multiplier"] > 0, "reduced", "cash"))
    return controls


def default_m4_specs() -> list[RegimeSpec]:
    return [
        RegimeSpec("baseline", "none"),
        RegimeSpec("qqq_sma50_gate", "trend_gate", symbol="QQQ", sma_days=50),
        RegimeSpec("qqq_sma50_reduce50", "trend_reduce", symbol="QQQ", sma_days=50, below_multiplier=0.5),
        RegimeSpec("spy_sma50_gate", "trend_gate", symbol="SPY", sma_days=50),
        RegimeSpec("spy_sma50_reduce50", "trend_reduce", symbol="SPY", sma_days=50, below_multiplier=0.5),
        RegimeSpec("qqq_vol10_reduce50", "vol_reduce", high_vol_multiplier=0.5, vol_days=10),
        RegimeSpec("qqq_trend_gate_vol_reduce50", "combined", symbol="QQQ", sma_days=50, below_multiplier=0.0, high_vol_multiplier=0.5, vol_days=10),
        RegimeSpec("qqq_trend_reduce50_vol_reduce50", "combined", symbol="QQQ", sma_days=50, below_multiplier=0.5, high_vol_multiplier=0.5, vol_days=10),
    ]


def summarize_control_usage(controls: pd.DataFrame) -> dict[str, float]:
    return {
        "pct_cash_control": float((controls["exposure_multiplier"] <= 0).mean()),
        "pct_reduced_control": float(((controls["exposure_multiplier"] > 0) & (controls["exposure_multiplier"] < 1)).mean()),
        "avg_control_multiplier": float(controls["exposure_multiplier"].mean()),
    }
