import pandas as pd
from alpha_lab.runner import run_config


def _sample(symbol="NVDA", n=40):
    dates = pd.bdate_range("2026-01-01", periods=n, tz="UTC")
    close = [100 + i * 0.5 + (1 if i % 3 == 0 else 0) for i in range(n)]
    return pd.DataFrame({
        "symbol": [symbol] * n,
        "timestamp": dates,
        "open": close,
        "high": [x + 1 for x in close],
        "low": [x - 1 for x in close],
        "close": close,
        "volume": [10_000_000 + i * 1_000 for i in range(n)],
    })


def test_run_config_returns_symbol_row():
    cfg = {
        "name": "test",
        "symbols": ["NVDA"],
        "entry": {"type": "momentum", "lookback_days": 2},
        "exit": {"reverse_day": True, "max_hold_days": 3, "stop_loss_pct": 0.04},
        "sizing": {"fraction_per_trade": 0.20},
        "execution": {"slippage_bps": 5},
    }
    table, metrics = run_config(_sample(), cfg)
    assert len(table) == 1
    assert table.loc[0, "symbol"] == "NVDA"
    assert "total_return" in metrics["NVDA"]
