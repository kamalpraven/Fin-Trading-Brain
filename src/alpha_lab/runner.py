from __future__ import annotations

from pathlib import Path
import json
import pandas as pd

from .backtest import BacktestConfig, run_single_symbol
from .features import add_basic_features
from .metrics import summarize
from .strategies import semi_momentum_signal, qqq_pullback_signal, catalyst_proxy_signal
from .walkforward import rolling_window_returns, summarize_windows


def _signal_for_config(df: pd.DataFrame, cfg: dict) -> pd.Series:
    typ = cfg["entry"]["type"]
    if typ == "momentum":
        n = int(cfg["entry"].get("lookback_days", 2))
        lag = f"close_lag{n}"
        if lag not in df.columns:
            df[lag] = df["close"].shift(n)
        return semi_momentum_signal(df, n)
    if typ == "pullback":
        return qqq_pullback_signal(df)
    if typ == "large_move":
        return catalyst_proxy_signal(df, float(cfg["entry"].get("min_daily_return", 0.02)))
    raise ValueError(f"Unknown entry type: {typ}")


def run_config(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Run one config independently on each configured symbol.

    This is the Milestone-1 research runner. Portfolio-level capital competition
    across simultaneous symbols is intentionally deferred to Milestone 2.
    """
    feat = add_basic_features(df)
    rows = []
    all_metrics = {}

    for symbol in cfg["symbols"]:
        x = feat[feat["symbol"] == symbol].copy().reset_index(drop=True)
        if x.empty:
            rows.append({"symbol": symbol, "status": "missing_data"})
            continue

        signal = _signal_for_config(x, cfg)
        bt_cfg = BacktestConfig(
            initial_cash=float(cfg.get("initial_cash", 100_000)),
            fraction_per_trade=float(cfg["sizing"]["fraction_per_trade"]),
            max_hold_days=int(cfg["exit"]["max_hold_days"]),
            stop_loss_pct=float(cfg["exit"]["stop_loss_pct"]),
            slippage_bps=float(cfg["execution"].get("slippage_bps", 5)),
            reverse_day_exit=bool(cfg["exit"].get("reverse_day", cfg["exit"].get("rebound_day", False))),
        )
        equity, trades, metrics = run_single_symbol(x, signal, bt_cfg)
        window_metrics = summarize_windows(rolling_window_returns(equity, 10))
        merged = {**metrics, **window_metrics}
        all_metrics[symbol] = merged
        rows.append({"symbol": symbol, "status": "ok", **merged})

    return pd.DataFrame(rows), all_metrics


def save_result_table(table: pd.DataFrame, out_dir: str | Path, name: str) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"{name}.csv"
    json_path = out / f"{name}.json"
    table.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(table.to_dict(orient="records"), indent=2, default=str), encoding="utf-8")
    return csv_path, json_path
