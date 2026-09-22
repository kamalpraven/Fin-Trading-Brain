from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from alpha_lab.config import load_config
from alpha_lab.data import load_cached
from alpha_lab.runner import run_config, save_result_table


def main():
    p = argparse.ArgumentParser(description="Run an Alpha Lab baseline backtest")
    p.add_argument("--config", required=True)
    p.add_argument("--data", default="daily_bars", help="cached parquet basename")
    p.add_argument("--csv", default=None, help="optional CSV path instead of cached parquet")
    p.add_argument("--out", default="results")
    args = p.parse_args()

    cfg = load_config(args.config)
    if args.csv:
        df = pd.read_csv(args.csv, parse_dates=["timestamp"])
    else:
        df = load_cached(args.data)

    table, _ = run_config(df, cfg)
    name = Path(args.config).stem
    csv_path, json_path = save_result_table(table, args.out, name)
    print(table.to_string(index=False))
    print(f"\nSaved: {csv_path}")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
