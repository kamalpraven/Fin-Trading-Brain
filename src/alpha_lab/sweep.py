from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .runner import run_portfolio_config
from .features import add_basic_features
from .strategies import semi_momentum_signal
from .portfolio_backtest import PortfolioBacktestConfig, run_portfolio_backtest, rolling_10d_windows, summarize_rolling_10d


def config_with_params(base: dict, lookback: int | None = None, max_hold: int | None = None, stop_loss: float | None = None, slippage_bps: float | None = None, symbols: list[str] | None = None) -> dict:
    cfg = deepcopy(base)
    if lookback is not None:
        cfg["entry"]["lookback_days"] = int(lookback)
    if max_hold is not None:
        cfg["exit"]["max_hold_days"] = int(max_hold)
    if stop_loss is not None:
        cfg["exit"]["stop_loss_pct"] = float(stop_loss)
    if slippage_bps is not None:
        cfg["execution"]["slippage_bps"] = float(slippage_bps)
    if symbols is not None:
        cfg["symbols"] = list(symbols)
    return cfg


def filter_dates(df: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"])
    tz = x["timestamp"].dt.tz
    if start:
        ts = pd.Timestamp(start)
        if tz is not None:
            ts = ts.tz_localize(tz) if ts.tzinfo is None else ts.tz_convert(tz)
        x = x[x["timestamp"] >= ts]
    if end:
        ts = pd.Timestamp(end)
        if tz is not None:
            ts = ts.tz_localize(tz) if ts.tzinfo is None else ts.tz_convert(tz)
        x = x[x["timestamp"] <= ts]
    return x.copy()


def result_row(metrics: dict, rolling: dict) -> dict[str, Any]:
    return {
        "total_return": metrics.get("total_return"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("maximum_drawdown"),
        "trades": metrics.get("number_of_trades"),
        "win_rate": metrics.get("win_rate"),
        "profit_factor": metrics.get("profit_factor"),
        "average_exposure": metrics.get("average_exposure"),
        "mean_10d_return": rolling.get("mean_10d_return"),
        "median_10d_return": rolling.get("median_10d_return"),
        "p10": rolling.get("p10"),
        "p90": rolling.get("p90"),
        "probability_positive_10d": rolling.get("probability_10d_return_positive"),
        "probability_zero_trade_10d": rolling.get("probability_zero_trade_window"),
        "worst_10d": rolling.get("worst_10d_return"),
        "best_10d": rolling.get("best_10d_return"),
    }


def run_parameter_sweep(df: pd.DataFrame, base_cfg: dict, lookbacks=(2, 3, 5, 10), holds=(1, 2, 3, 5), stops=(0.02, 0.03, 0.04, 0.05), slippage_bps: float = 5.0) -> pd.DataFrame:
    rows = []
    feat = add_basic_features(df[df["symbol"].isin(base_cfg["symbols"])].copy())
    feat = feat.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    for lb in lookbacks:
        if f"close_lag{lb}" not in feat.columns:
            feat[f"close_lag{lb}"] = feat.groupby("symbol")["close"].shift(lb)
        sig_parts = []
        for sym in base_cfg["symbols"]:
            x = feat[feat.symbol == sym].copy().reset_index(drop=True)
            y = x[["symbol", "timestamp"]].copy()
            y["entry_signal"] = semi_momentum_signal(x, lb).fillna(False).astype(bool).values
            y["signal_strength"] = 0.0
            sig_parts.append(y)
        signals = pd.concat(sig_parts, ignore_index=True)
        for hold in holds:
            for stop in stops:
                pcfg = PortfolioBacktestConfig(
                    strategy=base_cfg.get("name", "strategy"),
                    initial_cash=float(base_cfg.get("initial_cash", 100_000)),
                    fraction_per_trade=float(base_cfg["sizing"].get("fraction_per_trade", 0.20)),
                    max_positions=int(base_cfg["sizing"].get("max_positions", 4)),
                    max_hold_days=int(hold),
                    stop_loss_pct=float(stop),
                    slippage_bps=float(slippage_bps),
                    reverse_day_exit=bool(base_cfg["exit"].get("reverse_day", False)),
                    stop_execution=str(base_cfg["exit"].get("stop_execution", "close_next_open")),
                )
                _, _, metrics, _, rolling_summary = run_portfolio_backtest(feat, signals, pcfg)
                rows.append({"lookback": lb, "max_hold": hold, "stop_loss": stop, "slippage_bps": slippage_bps, **result_row(metrics, rolling_summary)})
    return pd.DataFrame(rows).sort_values(["lookback", "max_hold", "stop_loss"]).reset_index(drop=True)


def score_rows(table: pd.DataFrame) -> pd.Series:
    pf = table["profit_factor"].replace([np.inf, -np.inf], np.nan).fillna(0)
    return table["median_10d_return"].fillna(-1) + 0.002 * table["sharpe"].fillna(-10) + 0.001 * (pf - 1) + 0.2 * table["p10"].fillna(-1)


def plateau_summary(table: pd.DataFrame, top_n: int = 5) -> dict[str, Any]:
    t = table.copy()
    t["score"] = score_rows(t)
    top = t.sort_values("score", ascending=False).head(top_n)
    # Local neighbor similarity around best params using one-step grid adjacency.
    best = top.iloc[0]
    neighbors = t[((t.lookback - best.lookback).abs().isin([0, 1, 2, 3, 5, 8])) & ((t.max_hold - best.max_hold).abs() <= 2) & ((t.stop_loss - best.stop_loss).abs() <= 0.011)]
    robust = float((neighbors["profit_factor"] > 1).mean()) if len(neighbors) else np.nan
    return {
        "best_params": {"lookback": int(best.lookback), "max_hold": int(best.max_hold), "stop_loss": float(best.stop_loss)},
        "top_params": top[["lookback", "max_hold", "stop_loss", "score", "median_10d_return", "p10", "profit_factor", "sharpe", "total_return"]].to_dict("records"),
        "neighbor_count": int(len(neighbors)),
        "neighbor_pf_gt_1_rate": robust,
        "neighbor_median_10d_mean": float(neighbors["median_10d_return"].mean()) if len(neighbors) else np.nan,
        "neighbor_p10_mean": float(neighbors["p10"].mean()) if len(neighbors) else np.nan,
    }


def select_parameter_region(train_sweep: pd.DataFrame) -> dict[str, Any]:
    t = train_sweep.copy()
    t["score"] = score_rows(t)
    candidates = t[(t["profit_factor"] > 1.0) & (t["trades"] >= 20)].copy()
    if candidates.empty:
        candidates = t
    row = candidates.sort_values(["score", "profit_factor", "median_10d_return"], ascending=False).iloc[0]
    return {"lookback": int(row.lookback), "max_hold": int(row.max_hold), "stop_loss": float(row.stop_loss), "score": float(row.score)}


def walk_forward(df: pd.DataFrame, base_cfg: dict, folds: list[dict[str, str]], lookbacks=(2, 3, 5, 10), holds=(1, 2, 3, 5), stops=(0.02, 0.03, 0.04, 0.05)) -> pd.DataFrame:
    rows = []
    baseline = {"lookback": int(base_cfg["entry"].get("lookback_days", 2)), "max_hold": int(base_cfg["exit"].get("max_hold_days", 3)), "stop_loss": float(base_cfg["exit"].get("stop_loss_pct", 0.04))}
    for n, f in enumerate(folds, 1):
        train = filter_dates(df, f["train_start"], f["train_end"])
        valid = filter_dates(df, f["valid_start"], f["valid_end"])
        sw = run_parameter_sweep(train, base_cfg, lookbacks=lookbacks, holds=holds, stops=stops)
        sel = select_parameter_region(sw)
        for label, params in [("selected", sel), ("baseline", baseline)]:
            cfg = config_with_params(base_cfg, params["lookback"], params["max_hold"], params["stop_loss"], 5.0)
            _, _, m, _, r = run_portfolio_config(valid, cfg)
            rows.append({"fold": n, "model": label, "train_start": f["train_start"], "train_end": f["train_end"], "valid_start": f["valid_start"], "valid_end": f["valid_end"], **{k: params[k] for k in ["lookback", "max_hold", "stop_loss"]}, **result_row(m, r)})
    return pd.DataFrame(rows)


def non_overlapping_10d(equity: pd.DataFrame, trades: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    rows = []
    for start in range(0, len(equity) - window + 1, window):
        rows.append(rolling_10d_windows(equity.iloc[start:start+window].reset_index(drop=True), trades.iloc[0:0] if trades is not None else pd.DataFrame(), window).iloc[0])
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def bootstrap_ci(values, n_boot: int = 1000, seed: int = 7, alpha: float = 0.05) -> dict[str, float]:
    x = pd.Series(values).dropna().to_numpy()
    if len(x) == 0:
        return {"ci_low": np.nan, "ci_high": np.nan}
    rng = np.random.default_rng(seed)
    means = [rng.choice(x, size=len(x), replace=True).mean() for _ in range(n_boot)]
    return {"ci_low": float(np.quantile(means, alpha/2)), "ci_high": float(np.quantile(means, 1-alpha/2))}


def cost_sensitivity(df: pd.DataFrame, base_cfg: dict, params: dict[str, Any], costs=(0, 5, 10, 20)) -> pd.DataFrame:
    rows = []
    for c in costs:
        cfg = config_with_params(base_cfg, params["lookback"], params["max_hold"], params["stop_loss"], c)
        _, _, m, _, r = run_portfolio_config(df, cfg)
        rows.append({"slippage_bps": c, **{k: params[k] for k in ["lookback", "max_hold", "stop_loss"]}, **result_row(m, r)})
    return pd.DataFrame(rows)


def symbol_attribution(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sym, g in trades.groupby("symbol"):
        wins = g[g.pnl_dollars > 0]
        losers = g[g.pnl_dollars < 0]
        gp = wins.pnl_dollars.sum()
        gl = -losers.pnl_dollars.sum()
        rows.append({"symbol": sym, "trades": len(g), "gross_pnl": gp, "net_pnl": g.pnl_dollars.sum(), "average_trade": g.pnl_dollars.mean(), "win_rate": (g.pnl_dollars > 0).mean(), "profit_factor": gp / gl if gl else np.inf, "average_holding_period": g.hold_bars.mean()})
    return pd.DataFrame(rows).sort_values("net_pnl", ascending=False)


def leave_one_out(df: pd.DataFrame, base_cfg: dict) -> pd.DataFrame:
    rows = []
    for sym in base_cfg["symbols"]:
        syms = [s for s in base_cfg["symbols"] if s != sym]
        cfg = config_with_params(base_cfg, symbols=syms)
        _, _, m, _, r = run_portfolio_config(df[df.symbol.isin(syms)], cfg)
        rows.append({"removed_symbol": sym, **result_row(m, r)})
    return pd.DataFrame(rows)


def add_regimes(bars: pd.DataFrame) -> pd.DataFrame:
    qqq = bars[bars.symbol == "QQQ"].sort_values("timestamp").copy()
    qqq["qqq_sma50"] = qqq.close.rolling(50).mean()
    qqq["qqq_trend"] = np.where(qqq.close > qqq.qqq_sma50, "above_sma50", "below_sma50")
    ret = qqq.close.pct_change()
    vol = ret.rolling(20).std() * np.sqrt(252)
    q1 = vol.shift(1).expanding().quantile(.33)
    q2 = vol.shift(1).expanding().quantile(.67)
    qqq["qqq_vol_regime"] = np.select([vol <= q1, vol <= q2], ["low_vol", "med_vol"], default="high_vol")
    spy = bars[bars.symbol == "SPY"].sort_values("timestamp").copy()
    spy["spy_sma50"] = spy.close.rolling(50).mean()
    spy["spy_trend"] = np.where(spy.close > spy.spy_sma50, "spy_positive", "spy_negative")
    reg = qqq[["timestamp", "qqq_trend", "qqq_vol_regime"]].merge(spy[["timestamp", "spy_trend"]], on="timestamp", how="outer").sort_values("timestamp")
    return reg


def regime_attribution(equity: pd.DataFrame, trades: pd.DataFrame, rolling: pd.DataFrame, regimes: pd.DataFrame) -> pd.DataFrame:
    tr = trades.copy()
    tr["timestamp"] = pd.to_datetime(tr["entry_time"])
    tr = tr.merge(regimes, on="timestamp", how="left")
    rows = []
    for cols in [["qqq_trend"], ["qqq_vol_regime"], ["spy_trend"]]:
        col = cols[0]
        for val, g in tr.groupby(col, dropna=False):
            wins = g[g.pnl_dollars > 0]; losers = g[g.pnl_dollars < 0]
            gp = wins.pnl_dollars.sum(); gl = -losers.pnl_dollars.sum()
            rows.append({"regime_type": col, "regime": val, "trade_count": len(g), "trade_pnl": g.pnl_dollars.sum(), "profit_factor": gp/gl if gl else np.inf, "win_rate": (g.pnl_dollars > 0).mean()})
    rw = rolling.copy()
    rw["timestamp"] = pd.to_datetime(rw["start_date"])
    rw = rw.merge(regimes, on="timestamp", how="left")
    for col in ["qqq_trend", "qqq_vol_regime", "spy_trend"]:
        for val, g in rw.groupby(col, dropna=False):
            rows.append({"regime_type": col + "_10d", "regime": val, "trade_count": np.nan, "trade_pnl": np.nan, "profit_factor": np.nan, "win_rate": np.nan, "median_10d": g.portfolio_return.median(), "p10_10d": g.portfolio_return.quantile(.1)})
    return pd.DataFrame(rows)


def drawdown_episodes(equity: pd.DataFrame, trades: pd.DataFrame, regimes: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    e = equity.copy().reset_index(drop=True)
    e["peak"] = e.total_equity.cummax()
    e["dd"] = e.total_equity / e.peak - 1
    episodes = []
    in_dd = False
    start = trough = None
    for i, row in e.iterrows():
        if not in_dd and row.dd < 0:
            in_dd = True; start = i-1 if i > 0 else i; trough = i
        if in_dd:
            if row.dd < e.loc[trough, "dd"]: trough = i
            if row.dd >= 0 or i == len(e)-1:
                end = i if row.dd >= 0 else np.nan
                episodes.append((start, trough, end))
                in_dd = False
    rows = []
    for start, trough, end in sorted(episodes, key=lambda x: e.loc[x[1], "dd"])[:top_n]:
        st = e.loc[start, "timestamp"]; tr_date = e.loc[trough, "timestamp"]; rec = None if pd.isna(end) else e.loc[int(end), "timestamp"]
        losers = trades[(pd.to_datetime(trades.exit_time) >= pd.to_datetime(st)) & (pd.to_datetime(trades.exit_time) <= pd.to_datetime(tr_date))].sort_values("pnl_dollars").head(5)
        reg = regimes[regimes.timestamp == tr_date]
        rows.append({"start": st, "trough": tr_date, "recovery": rec, "max_drawdown": e.loc[trough, "dd"], "duration_bars": trough-start if pd.isna(end) else int(end)-start, "max_concurrent_positions": int(e.loc[start:trough, "number_open_positions"].max()), "symbols_responsible": ",".join(losers.symbol.dropna().unique()), "largest_losing_trades": ";".join(f"{r.symbol}:{r.pnl_dollars:.0f}" for _, r in losers.iterrows()), "qqq_trend": reg.qqq_trend.iloc[0] if len(reg) else None, "qqq_vol_regime": reg.qqq_vol_regime.iloc[0] if len(reg) else None})
    return pd.DataFrame(rows)


def trade_clustering(equity: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    tr = trades.copy(); tr["entry_time"] = pd.to_datetime(tr.entry_time); tr["month"] = tr.entry_time.dt.to_period("M").astype(str); tr["year"] = tr.entry_time.dt.year
    monthly = tr.groupby("month").size().rename("entries").reset_index(); monthly["type"] = "monthly"
    yearly = tr.groupby("year").size().rename("entries").reset_index().rename(columns={"year":"month"}); yearly["type"] = "yearly"
    daily = tr.groupby(tr.entry_time.dt.normalize()).size()
    dist = daily.value_counts().sort_index().rename_axis("entries_per_day").reset_index(name="days")
    dist["type"] = "entries_per_day_distribution"; dist = dist.rename(columns={"entries_per_day":"month", "days":"entries"})
    pos = equity.number_open_positions.value_counts().sort_index().rename_axis("open_positions").reset_index(name="days")
    pos["type"] = "simultaneous_position_distribution"; pos = pos.rename(columns={"open_positions":"month", "days":"entries"})
    turnover = pd.DataFrame([{"month":"turnover_estimate", "entries": float(tr.allocation.sum() / equity.total_equity.mean()), "type":"notional_allocated_over_avg_equity"}])
    return pd.concat([monthly, yearly, dist, pos, turnover], ignore_index=True)


def benchmarks(bars: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    rows = []
    for name, syms in [("SPY_buy_hold", ["SPY"]), ("QQQ_buy_hold", ["QQQ"]), ("equal_weight_semis_buy_hold", symbols)]:
        wide = bars[bars.symbol.isin(syms)].pivot(index="timestamp", columns="symbol", values="close").dropna()
        if wide.empty: continue
        norm = wide / wide.iloc[0]
        equity = norm.mean(axis=1) * 100_000
        eq = pd.DataFrame({"timestamp": equity.index, "total_equity": equity.values, "gross_exposure": 1.0})
        eq["daily_return"] = eq.total_equity.pct_change().fillna(0); eq["drawdown"] = eq.total_equity / eq.total_equity.cummax() - 1
        roll = summarize_rolling_10d(rolling_10d_windows(eq, pd.DataFrame()))
        std = eq.daily_return.std(ddof=1)
        rows.append({"benchmark": name, "total_return": eq.total_equity.iloc[-1] / eq.total_equity.iloc[0] - 1, "max_drawdown": eq.drawdown.min(), "sharpe": np.sqrt(252)*eq.daily_return.mean()/std if std else np.nan, **roll})
    return pd.DataFrame(rows)
