import math

import pandas as pd

from alpha_lab.portfolio_backtest import PortfolioBacktestConfig, run_portfolio_backtest, rolling_10d_windows


def bars(symbols=("AAA",), n=15, opens=None, closes=None):
    dates = pd.bdate_range("2026-01-01", periods=n, tz="UTC")
    rows = []
    for sym in symbols:
        op = opens or [100.0] * n
        cl = closes or op
        for i, ts in enumerate(dates):
            rows.append({"symbol": sym, "timestamp": ts, "open": op[i], "high": max(op[i], cl[i]) + 1, "low": min(op[i], cl[i]) - 1, "close": cl[i], "volume": 1000})
    return pd.DataFrame(rows)


def sig(df, true_by_symbol_index):
    out = df[["symbol", "timestamp"]].copy()
    out["entry_signal"] = False
    out["signal_strength"] = 0.0
    for sym, idxs in true_by_symbol_index.items():
        mask = out["symbol"].eq(sym)
        sym_index = out[mask].index.tolist()
        for i in idxs:
            out.loc[sym_index[i], "entry_signal"] = True
    return out


def run(df, signals, **kwargs):
    cfg = PortfolioBacktestConfig(strategy="t", initial_cash=100_000, fraction_per_trade=kwargs.pop("fraction_per_trade", .2), max_positions=kwargs.pop("max_positions", 4), max_hold_days=kwargs.pop("max_hold_days", 3), stop_loss_pct=kwargs.pop("stop_loss_pct", .04), slippage_bps=kwargs.pop("slippage_bps", 0), reverse_day_exit=kwargs.pop("reverse_day_exit", False))
    return run_portfolio_backtest(df, signals, cfg)


def test_shared_cash_accounting_and_current_equity_sizing_and_equity_calc():
    df = bars(("AAA", "BBB"), n=6, opens=[100, 100, 110, 110, 110, 110], closes=[100, 110, 110, 110, 110, 110])
    equity, trades, *_ = run(df, sig(df, {"AAA": [0], "BBB": [1]}), max_hold_days=5)
    assert equity.iloc[1].cash == 80_000
    # BBB sizes from current equity (102k), not original capital.
    assert math.isclose(equity.iloc[2].cash, 80_000 - 20_400, rel_tol=1e-9)
    assert (abs(equity.cash + equity.invested_value - equity.total_equity) < 1e-8).all()


def test_entry_at_next_open_and_no_lookahead():
    df = bars(n=5, opens=[100, 123, 999, 999, 999], closes=[200, 1, 1, 1, 1])
    _, trades, *_ = run(df, sig(df, {"AAA": [0]}), max_hold_days=1)
    assert trades.iloc[0].entry_time == df.iloc[1].timestamp
    assert trades.iloc[0].entry_price == 123


def test_max_positions_simultaneous_deterministic_priority_and_no_duplicate_tickers():
    df = bars(("CCC", "AAA", "BBB"), n=5)
    equity, trades, *_ = run(df, sig(df, {"AAA": [0], "BBB": [0], "CCC": [0]}), max_positions=2, max_hold_days=2)
    entries = trades.sort_values("symbol").symbol.tolist()
    assert entries == ["AAA", "BBB"]
    assert equity.number_open_positions.max() <= 2
    assert len(trades[trades.symbol == "AAA"]) == 1


def test_stop_loss_behavior():
    df = bars(n=5, opens=[100, 100, 90, 90, 90], closes=[100, 94, 90, 90, 90])
    _, trades, *_ = run(df, sig(df, {"AAA": [0]}), max_hold_days=5, stop_loss_pct=.04)
    assert trades.iloc[0].exit_reason == "stop_loss"
    assert trades.iloc[0].exit_time == df.iloc[2].timestamp


def test_maximum_holding_period_exit():
    df = bars(n=6)
    _, trades, *_ = run(df, sig(df, {"AAA": [0]}), max_hold_days=3)
    assert trades.iloc[0].exit_reason == "max_hold"
    assert trades.iloc[0].hold_bars == 3


def test_reverse_day_exit():
    df = bars(n=6, closes=[100, 105, 104, 104, 104, 104])
    _, trades, *_ = run(df, sig(df, {"AAA": [0]}), max_hold_days=5, reverse_day_exit=True)
    assert trades.iloc[0].exit_reason == "reverse_day"
    assert trades.iloc[0].exit_time == df.iloc[3].timestamp


def test_slippage_applied_to_entry_and_exit():
    df = bars(n=4, opens=[100, 100, 100, 100])
    _, trades, *_ = run(df, sig(df, {"AAA": [0]}), max_hold_days=1, slippage_bps=50)
    assert math.isclose(trades.iloc[0].entry_price, 100.5)
    assert math.isclose(trades.iloc[0].exit_price, 99.5)


def test_rolling_10_day_returns_and_zero_trade_windows():
    eq = pd.DataFrame({
        "timestamp": pd.bdate_range("2026-01-01", periods=12, tz="UTC"),
        "total_equity": [100 + i for i in range(12)],
        "gross_exposure": [0.0] * 12,
    })
    tr = pd.DataFrame(columns=["entry_time", "exit_time"])
    r = rolling_10d_windows(eq, tr, window=10)
    assert len(r) == 3
    assert math.isclose(r.iloc[0].portfolio_return, 109 / 100 - 1)
    assert r.any_trade.eq(False).all()
