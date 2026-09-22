from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from alpha_lab.config import load_config
from alpha_lab.data import load_cached
from alpha_lab.runner import run_portfolio_config, save_portfolio_artifacts


def main() -> None:
    p = argparse.ArgumentParser(description="Run a shared-capital portfolio backtest")
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

    equity, trades, metrics, rolling, rolling_summary = run_portfolio_config(df, cfg)
    name = Path(args.config).stem
    paths = save_portfolio_artifacts(equity, trades, metrics, rolling, rolling_summary, args.out, name)

    print(f"Strategy: {cfg.get('name', name)}")
    print(f"Total return: {metrics['total_return']:.4%}")
    print(f"Sharpe: {metrics['sharpe']:.4f}")
    print(f"Max drawdown: {metrics['maximum_drawdown']:.4%}")
    print(f"Trades: {metrics['number_of_trades']}")
    print(f"Win rate: {metrics['win_rate']:.2%}")
    print(f"Profit factor: {metrics['profit_factor']:.4f}")
    print(f"Average exposure: {metrics['average_exposure']:.2%}")
    if rolling_summary:
        print("Rolling 10d:")
        print(f"  mean={rolling_summary['mean_10d_return']:.4%} median={rolling_summary['median_10d_return']:.4%} p10={rolling_summary['p10']:.4%} p90={rolling_summary['p90']:.4%}")
        print(f"  prob_positive={rolling_summary['probability_10d_return_positive']:.2%} prob_zero_trade={rolling_summary['probability_zero_trade_window']:.2%}")
        print(f"  worst={rolling_summary['worst_10d_return']:.4%} best={rolling_summary['best_10d_return']:.4%}")
    print("Saved:")
    for path in paths.values():
        print(f"  {path}")


if __name__ == "__main__":
    main()
