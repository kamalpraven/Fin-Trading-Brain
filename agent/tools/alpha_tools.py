from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from alpha_lab.config import load_config
from alpha_lab.data import load_cached
from alpha_lab.features import add_basic_features
from alpha_lab.runner import build_signals_for_config

CONFIG_PATH = Path("configs/semi_momentum.yaml")
M4_DIR = Path("results/m4")
M3_DIR = Path("results/m3")


def _unavailable(name: str, path: Path) -> dict[str, Any]:
    return {"available": False, "artifact": name, "reason": f"missing artifact: {path}"}


def get_strategy_config() -> dict[str, Any]:
    cfg = load_config(CONFIG_PATH)
    return {"available": True, "config_path": str(CONFIG_PATH), "config": cfg}


def get_semiconductor_universe() -> dict[str, Any]:
    cfg = load_config(CONFIG_PATH)
    return {"available": True, "symbols": list(cfg.get("symbols", []))}


def _load_data() -> pd.DataFrame:
    return load_cached("daily_bars")


def get_latest_rankings() -> dict[str, Any]:
    cfg = load_config(CONFIG_PATH)
    try:
        df = _load_data()
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    feat, signals = build_signals_for_config(df[df["symbol"].isin(cfg["symbols"])].copy(), cfg)
    latest_date = pd.to_datetime(feat["timestamp"]).max()
    rows = []
    for sym in cfg["symbols"]:
        sx = signals[signals.symbol == sym].sort_values("timestamp")
        fx = feat[feat.symbol == sym].sort_values("timestamp")
        if sx.empty or fx.empty:
            rows.append({"symbol": sym, "rank": None, "signal": "unavailable", "score": None})
            continue
        srow = sx.iloc[-1]
        frow = fx.iloc[-1]
        is_candidate = bool(srow.entry_signal)
        score = float(frow.get("ret_1d", 0) if pd.notna(frow.get("ret_1d", 0)) else 0)
        rows.append({"symbol": sym, "signal": "candidate" if is_candidate else "watch", "raw_signal": is_candidate, "score": score, "as_of": str(srow.timestamp)})
    rows = sorted(rows, key=lambda r: (0 if r["raw_signal"] else 1, -(r["score"] or -999), r["symbol"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return {"available": True, "as_of": str(latest_date), "symbols": rows}


def get_signal_for_symbol(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    universe = get_semiconductor_universe()["symbols"]
    if symbol not in universe:
        return {"available": False, "symbol": symbol, "reason": "unsupported symbol"}
    rankings = get_latest_rankings()
    if not rankings.get("available"):
        return rankings
    for row in rankings["symbols"]:
        if row["symbol"] == symbol:
            return {"available": True, **row}
    return {"available": False, "symbol": symbol, "reason": "signal unavailable"}


def _read_csv_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _unavailable(path.name, path)
    return {"available": True, "path": str(path), "records": pd.read_csv(path).to_dict("records")}


def get_backtest_summary() -> dict[str, Any]:
    p = Path("results/semi_momentum_portfolio_summary.json")
    if not p.exists():
        return _unavailable(p.name, p)
    return {"available": True, "path": str(p), "summary": json.loads(p.read_text(encoding="utf-8"))}


def get_cost_sensitivity_summary() -> dict[str, Any]:
    return _read_csv_artifact(M4_DIR / "regime_cost_sensitivity.csv")


def get_walk_forward_summary() -> dict[str, Any]:
    return _read_csv_artifact(M4_DIR / "regime_walk_forward.csv")


def get_symbol_attribution() -> dict[str, Any]:
    p = M4_DIR / "regime_symbol_attribution.csv"
    if p.exists():
        return _read_csv_artifact(p)
    return _read_csv_artifact(M3_DIR / "symbol_attribution.csv")


def get_benchmark_comparison() -> dict[str, Any]:
    return _read_csv_artifact(M4_DIR / "regime_benchmark_comparison.csv")


def get_2022_drawdown_diagnosis() -> dict[str, Any]:
    return _read_csv_artifact(M4_DIR / "regime_2022_diagnosis.csv")
