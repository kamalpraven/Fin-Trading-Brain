from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
symbols = ["NVDA", "AMD", "AVGO", "AMAT", "MU", "QQQ", "META", "TSLA", "GOOGL", "AMZN"]
dates = pd.bdate_range("2025-01-02", periods=320, tz="UTC")
rows = []
for j, symbol in enumerate(symbols):
    base = 100 + 10*j
    noise = rng.normal(0.0004 + j*0.00001, 0.018 + (j % 3)*0.002, len(dates))
    close = base * np.exp(np.cumsum(noise))
    overnight = rng.normal(0, 0.004, len(dates))
    open_ = close * (1 + overnight)
    high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.02, len(dates)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.02, len(dates)))
    volume = rng.integers(10_000_000, 90_000_000, len(dates))
    for i, dt in enumerate(dates):
        rows.append((symbol, dt, open_[i], high[i], low[i], close[i], int(volume[i])))

out = pd.DataFrame(rows, columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])
path = Path("data/sample_daily_bars.csv")
out.to_csv(path, index=False)
print(f"wrote {len(out):,} rows -> {path}")
