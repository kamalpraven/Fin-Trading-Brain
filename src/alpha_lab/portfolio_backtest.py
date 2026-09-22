from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd


@dataclass
class PortfolioBacktestConfig:
    strategy: str = "strategy"
    initial_cash: float = 100_000.0
    fraction_per_trade: float = 0.20
    max_positions: int | None = None
    max_hold_days: int = 3
    stop_loss_pct: float = 0.04
    slippage_bps: float = 5.0
    reverse_day_exit: bool = False
    stop_execution: str = "close_next_open"  # close_next_open or daily_gap_aware


@dataclass
class Position:
    symbol: str
    signal_time: Any
    entry_time: Any
    entry_index: int
    entry_price: float
    shares: float
    allocation: float
    metadata: dict[str, Any]


def _as_ts(x: Any) -> pd.Timestamp:
    return pd.Timestamp(x)


def _default_rank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable deterministic ranking; higher signal_strength wins if present."""
    return sorted(candidates, key=lambda c: (-float(c.get("signal_strength", 0.0)), str(c["symbol"])))


def run_portfolio_backtest(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    cfg: PortfolioBacktestConfig,
    ranker: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    controls: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame, dict[str, Any]]:
    """Run a long-only shared-capital portfolio backtest.

    `signals` must contain symbol, timestamp, entry_signal and may contain
    signal_strength plus arbitrary metadata. A True signal at completed bar t can
    only enter at that symbol's next available open.
    """
    required = {"symbol", "timestamp", "open", "high", "low", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"bars missing columns: {sorted(missing)}")

    b = bars.copy()
    b["timestamp"] = pd.to_datetime(b["timestamp"])
    b = b.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    sig = signals.copy()
    sig["timestamp"] = pd.to_datetime(sig["timestamp"])
    if "entry_signal" not in sig.columns:
        raise ValueError("signals must include entry_signal")
    if "signal_strength" not in sig.columns:
        sig["signal_strength"] = 0.0

    symbol_order = list(dict.fromkeys(b["symbol"].tolist()))
    by_symbol = {s: x.reset_index(drop=True) for s, x in b.groupby("symbol", sort=False)}
    sig_by_symbol = {s: x.reset_index(drop=True) for s, x in sig.groupby("symbol", sort=False)}
    sig_lookup: dict[tuple[str, pd.Timestamp], pd.Series] = {}
    for s, x in sig_by_symbol.items():
        for _, row in x.iterrows():
            sig_lookup[(s, _as_ts(row["timestamp"]))] = row

    control_lookup: dict[pd.Timestamp, dict[str, Any]] = {}
    if controls is not None and not controls.empty:
        c = controls.copy()
        c["timestamp"] = pd.to_datetime(c["timestamp"])
        for _, row in c.iterrows():
            control_lookup[pd.Timestamp(row["timestamp"])] = row.to_dict()

    all_dates = sorted(pd.to_datetime(b["timestamp"]).unique())
    slip = cfg.slippage_bps / 10_000.0
    cash = float(cfg.initial_cash)
    positions: dict[str, Position] = {}
    trades: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    rank = ranker or _default_rank
    max_positions = cfg.max_positions if cfg.max_positions is not None else int(np.floor(1.0 / cfg.fraction_per_trade))

    index_by_symbol = {
        s: {pd.Timestamp(ts): i for i, ts in enumerate(x["timestamp"])} for s, x in by_symbol.items()
    }

    def mark_value(ts: pd.Timestamp, field: str = "close") -> float:
        value = cash
        for sym, pos in positions.items():
            idx = index_by_symbol[sym].get(ts)
            if idx is None:
                # Daily US equity data should be aligned; fall back to last close.
                hist = by_symbol[sym][by_symbol[sym]["timestamp"] <= ts]
                if hist.empty:
                    px = pos.entry_price
                else:
                    px = float(hist.iloc[-1]["close"])
            else:
                px = float(by_symbol[sym].iloc[idx][field])
            value += pos.shares * px
        return float(value)

    for ts in all_dates:
        ts = pd.Timestamp(ts)

        # Exits first: decisions use information from completed prior bars and
        # fills use current open.
        for sym in list(positions.keys()):
            idx = index_by_symbol[sym].get(ts)
            if idx is None or idx <= positions[sym].entry_index:
                continue
            x = by_symbol[sym]
            pos = positions[sym]
            prev = x.iloc[idx - 1]
            cur = x.iloc[idx]
            hold_bars = idx - pos.entry_index
            stop_price = pos.entry_price * (1.0 - cfg.stop_loss_pct)
            if cfg.stop_execution == "close_next_open":
                stop = float(prev["close"]) <= stop_price
                stop_fill = float(cur["open"]) * (1.0 - slip)
            elif cfg.stop_execution == "daily_gap_aware":
                if float(cur["open"]) <= stop_price:
                    stop = True
                    stop_fill = float(cur["open"]) * (1.0 - slip)
                elif float(cur["low"]) <= stop_price:
                    stop = True
                    stop_fill = stop_price * (1.0 - slip)
                else:
                    stop = False
                    stop_fill = np.nan
            else:
                raise ValueError(f"unknown stop_execution: {cfg.stop_execution}")
            reverse = bool(cfg.reverse_day_exit and idx >= 2 and float(x.iloc[idx - 1]["close"]) < float(x.iloc[idx - 2]["close"]))
            max_hold = hold_bars >= cfg.max_hold_days
            if not (stop or reverse or max_hold):
                continue
            reason = "stop_loss" if stop else "reverse_day" if reverse else "max_hold"
            exit_price = float(stop_fill) if stop else float(cur["open"]) * (1.0 - slip)
            proceeds = pos.shares * exit_price
            cash += proceeds
            pnl = proceeds - pos.allocation
            trades.append({
                "strategy": cfg.strategy,
                "symbol": sym,
                "signal_time": pos.signal_time,
                "entry_time": pos.entry_time,
                "exit_time": ts,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "shares": pos.shares,
                "allocation": pos.allocation,
                "pnl_dollars": pnl,
                "pnl_pct": pnl / pos.allocation if pos.allocation else np.nan,
                "hold_bars": hold_bars,
                "exit_reason": reason,
                **{f"signal_{k}": v for k, v in pos.metadata.items() if k not in {"symbol", "timestamp", "entry_signal"}},
            })
            del positions[sym]

        # Entry candidates: previous completed bar's signal, next available open.
        candidates: list[dict[str, Any]] = []
        for sym in symbol_order:
            if sym in positions:
                continue
            idx = index_by_symbol[sym].get(ts)
            if idx is None or idx <= 0:
                continue
            x = by_symbol[sym]
            signal_time = pd.Timestamp(x.iloc[idx - 1]["timestamp"])
            srow = sig_lookup.get((sym, signal_time))
            if srow is not None and bool(srow["entry_signal"]):
                ctrl = control_lookup.get(signal_time, {})
                if not bool(ctrl.get("allow_entries", True)):
                    continue
                mult = float(ctrl.get("exposure_multiplier", 1.0))
                if mult <= 0:
                    continue
                md = srow.to_dict()
                candidates.append({"symbol": sym, "idx": idx, "signal_time": signal_time, "signal_strength": md.get("signal_strength", 0.0), "metadata": md, "exposure_multiplier": mult})

        slots = max(0, int(max_positions) - len(positions))
        for cand in rank(candidates)[:slots]:
            if len(positions) >= int(max_positions):
                break
            sym = cand["symbol"]
            idx = cand["idx"]
            px = float(by_symbol[sym].iloc[idx]["open"]) * (1.0 + slip)
            equity_now = mark_value(ts, field="open")
            target = equity_now * cfg.fraction_per_trade * float(cand.get("exposure_multiplier", 1.0))
            allocation = min(target, cash)
            if allocation <= 0 or px <= 0:
                continue
            shares = allocation / px
            cash -= allocation
            positions[sym] = Position(
                symbol=sym,
                signal_time=cand["signal_time"],
                entry_time=ts,
                entry_index=idx,
                entry_price=px,
                shares=shares,
                allocation=allocation,
                metadata={**cand["metadata"], "exposure_multiplier": cand.get("exposure_multiplier", 1.0)},
            )

        invested = 0.0
        for sym, pos in positions.items():
            idx = index_by_symbol[sym].get(ts)
            px = float(by_symbol[sym].iloc[idx]["close"]) if idx is not None else pos.entry_price
            invested += pos.shares * px
        total = cash + invested
        gross = invested / total if total else np.nan
        ctrl_today = control_lookup.get(ts, {})
        ledger.append({
            "timestamp": ts,
            "cash": cash,
            "invested_value": invested,
            "total_equity": total,
            "gross_exposure": gross,
            "number_open_positions": len(positions),
            "allow_entries": bool(ctrl_today.get("allow_entries", True)),
            "exposure_multiplier": float(ctrl_today.get("exposure_multiplier", 1.0)),
        })

    equity = pd.DataFrame(ledger)
    equity["daily_return"] = equity["total_equity"].pct_change().fillna(0.0)
    equity["drawdown"] = equity["total_equity"] / equity["total_equity"].cummax() - 1.0
    trades_df = pd.DataFrame(trades)
    metrics = portfolio_metrics(equity, trades_df, cfg.initial_cash)
    rolling = rolling_10d_windows(equity, trades_df)
    rolling_summary = summarize_rolling_10d(rolling)
    return equity, trades_df, metrics, rolling, rolling_summary


def portfolio_metrics(equity: pd.DataFrame, trades: pd.DataFrame, initial_cash: float) -> dict[str, Any]:
    total_return = float(equity["total_equity"].iloc[-1] / initial_cash - 1.0) if len(equity) else np.nan
    daily = equity["daily_return"].dropna()
    std = daily.std(ddof=1)
    sharpe = float(np.sqrt(252) * daily.mean() / std) if len(daily) > 1 and std > 0 else np.nan
    years = max(len(equity) / 252.0, 1e-12)
    ann = float((1.0 + total_return) ** (1.0 / years) - 1.0) if total_return > -1 else -1.0
    mdd = float(equity["drawdown"].min()) if len(equity) else np.nan
    n = int(len(trades))
    if n:
        wins = trades[trades["pnl_dollars"] > 0]
        losers = trades[trades["pnl_dollars"] < 0]
        gross_profit = float(wins["pnl_dollars"].sum())
        gross_loss = float(-losers["pnl_dollars"].sum())
        win_rate = float(len(wins) / n)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        avg_winner = float(wins["pnl_dollars"].mean()) if len(wins) else 0.0
        avg_loser = float(losers["pnl_dollars"].mean()) if len(losers) else 0.0
        avg_hold = float(trades["hold_bars"].mean())
        largest_winner = float(trades["pnl_dollars"].max())
        largest_loser = float(trades["pnl_dollars"].min())
        expectancy = float(trades["pnl_dollars"].mean())
    else:
        win_rate = profit_factor = avg_hold = largest_winner = largest_loser = expectancy = np.nan
        avg_winner = avg_loser = 0.0
    return {
        "total_return": total_return,
        "annualized_return": ann,
        "sharpe": sharpe,
        "maximum_drawdown": mdd,
        "number_of_trades": n,
        "win_rate": win_rate,
        "profit_factor": float(profit_factor),
        "average_winner": avg_winner,
        "average_loser": avg_loser,
        "average_holding_period": avg_hold,
        "average_exposure": float(equity["gross_exposure"].mean()) if len(equity) else np.nan,
        "capital_utilization": float(equity["gross_exposure"].mean()) if len(equity) else np.nan,
        "largest_winner": largest_winner,
        "largest_loser": largest_loser,
        "expectancy_per_trade": expectancy,
    }


def rolling_10d_windows(equity: pd.DataFrame, trades: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if len(equity) < window:
        return pd.DataFrame(rows)
    e = equity.reset_index(drop=True)
    tr = trades.copy()
    if len(tr):
        tr["entry_time"] = pd.to_datetime(tr["entry_time"])
        tr["exit_time"] = pd.to_datetime(tr["exit_time"])
    for i in range(0, len(e) - window + 1):
        w = e.iloc[i : i + window]
        start = pd.Timestamp(w.iloc[0]["timestamp"])
        end = pd.Timestamp(w.iloc[-1]["timestamp"])
        if len(tr):
            entries = tr[(tr["entry_time"] >= start) & (tr["entry_time"] <= end)]
            exits = tr[(tr["exit_time"] >= start) & (tr["exit_time"] <= end)]
        else:
            entries = exits = tr
        dd = w["total_equity"] / w["total_equity"].cummax() - 1.0
        rows.append({
            "start_date": start,
            "end_date": end,
            "portfolio_return": float(w.iloc[-1]["total_equity"] / w.iloc[0]["total_equity"] - 1.0),
            "number_entries": int(len(entries)),
            "number_exits": int(len(exits)),
            "maximum_drawdown_within_window": float(dd.min()),
            "average_gross_exposure": float(w["gross_exposure"].mean()),
            "maximum_gross_exposure": float(w["gross_exposure"].max()),
            "any_trade": bool(len(entries) or len(exits)),
        })
    return pd.DataFrame(rows)


def summarize_rolling_10d(rolling: pd.DataFrame) -> dict[str, Any]:
    if rolling.empty:
        return {}
    r = rolling["portfolio_return"]
    return {
        "mean_10d_return": float(r.mean()),
        "median_10d_return": float(r.median()),
        "p10": float(r.quantile(0.10)),
        "p25": float(r.quantile(0.25)),
        "p75": float(r.quantile(0.75)),
        "p90": float(r.quantile(0.90)),
        "probability_10d_return_positive": float((r > 0).mean()),
        "probability_zero_trade_window": float((~rolling["any_trade"]).mean()),
        "worst_10d_return": float(r.min()),
        "best_10d_return": float(r.max()),
        "median_entries_per_10d": float(rolling["number_entries"].median()),
        "mean_entries_per_10d": float(rolling["number_entries"].mean()),
    }
