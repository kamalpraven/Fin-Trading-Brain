from __future__ import annotations

from pathlib import Path
import json
import pandas as pd

from .backtest import BacktestConfig, run_single_symbol
from .features import add_basic_features
from .metrics import summarize
from .strategies import semi_momentum_signal, qqq_pullback_signal, catalyst_proxy_signal
from .walkforward import rolling_window_returns, summarize_windows
from .portfolio_backtest import PortfolioBacktestConfig, run_portfolio_backtest


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


def build_signals_for_config(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return leakage-safe feature rows and per-symbol entry signals."""
    feat = add_basic_features(df)
    rows = []
    for symbol in cfg["symbols"]:
        x = feat[feat["symbol"] == symbol].copy().reset_index(drop=True)
        if x.empty:
            continue
        signal = _signal_for_config(x, cfg)
        y = x[["symbol", "timestamp"]].copy()
        y["entry_signal"] = signal.fillna(False).astype(bool).values
        y["signal_strength"] = 0.0
        # Preserve useful point-in-time metadata for later ranking/analysis.
        for col in ["ret_1d", "close_lag1", "close_lag2", "close_lag5", "rsi_14", "vol_ratio_20"]:
            if col in x.columns:
                y[col] = x[col].values
        rows.append(y)
    signals = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["symbol", "timestamp", "entry_signal", "signal_strength"])
    return feat, signals


def run_portfolio_config(df: pd.DataFrame, cfg: dict, controls: pd.DataFrame | None = None):
    feat, signals = build_signals_for_config(df, cfg)
    bt_cfg = PortfolioBacktestConfig(
        strategy=cfg.get("name", "strategy"),
        initial_cash=float(cfg.get("initial_cash", 100_000)),
        fraction_per_trade=float(cfg["sizing"].get("fraction_per_trade", 0.20)),
        max_positions=int(cfg["sizing"].get("max_positions", cfg.get("max_positions", max(1, int(1 / float(cfg["sizing"].get("fraction_per_trade", 0.20))))))),
        max_hold_days=int(cfg["exit"].get("max_hold_days", 3)),
        stop_loss_pct=float(cfg["exit"].get("stop_loss_pct", 0.04)),
        slippage_bps=float(cfg["execution"].get("slippage_bps", 5)),
        reverse_day_exit=bool(cfg["exit"].get("reverse_day", cfg["exit"].get("rebound_day", False))),
        stop_execution=str(cfg["exit"].get("stop_execution", "close_next_open")),
    )
    bars = feat[feat["symbol"].isin(cfg["symbols"])].copy()
    equity, trades, metrics, rolling, rolling_summary = run_portfolio_backtest(bars, signals, bt_cfg, controls=controls)
    return equity, trades, metrics, rolling, rolling_summary


def save_portfolio_artifacts(equity: pd.DataFrame, trades: pd.DataFrame, metrics: dict, rolling: pd.DataFrame, rolling_summary: dict, out_dir: str | Path, name: str) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {"metrics": metrics, "rolling_10d": rolling_summary}
    paths = {
        "summary": out / f"{name}_portfolio_summary.json",
        "trades": out / f"{name}_portfolio_trades.csv",
        "equity": out / f"{name}_portfolio_equity.csv",
        "rolling": out / f"{name}_rolling_10d.csv",
    }
    paths["summary"].write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    trades.to_csv(paths["trades"], index=False)
    equity.to_csv(paths["equity"], index=False)
    rolling.to_csv(paths["rolling"], index=False)
    return paths
