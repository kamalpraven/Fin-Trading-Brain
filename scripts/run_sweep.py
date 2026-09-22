from __future__ import annotations

import argparse, json
from pathlib import Path
import pandas as pd

from alpha_lab.config import load_config
from alpha_lab.data import load_cached
from alpha_lab.runner import run_portfolio_config
from alpha_lab.sweep import (
    run_parameter_sweep, plateau_summary, walk_forward, cost_sensitivity,
    symbol_attribution, leave_one_out, add_regimes, regime_attribution,
    drawdown_episodes, trade_clustering, benchmarks, non_overlapping_10d,
    bootstrap_ci, select_parameter_region,
)


def main():
    p = argparse.ArgumentParser(description="Milestone 3 robustness sweep")
    p.add_argument("--config", default="configs/semi_momentum.yaml")
    p.add_argument("--data", default="daily_bars")
    p.add_argument("--out", default="results/m3")
    args = p.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(args.config)
    df = load_cached(args.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    sweep_path = out / "semi_momentum_sweep.csv"
    if sweep_path.exists():
        sweep = pd.read_csv(sweep_path)
    else:
        sweep = run_parameter_sweep(df, cfg)
        sweep.to_csv(sweep_path, index=False)
    plateau = plateau_summary(sweep)
    (out / "plateau_summary.json").write_text(json.dumps(plateau, indent=2, default=str), encoding="utf-8")
    selected = select_parameter_region(sweep)

    folds = [
        {"train_start":"2022-01-03", "train_end":"2023-12-31", "valid_start":"2024-01-01", "valid_end":"2024-12-31"},
        {"train_start":"2022-01-03", "train_end":"2024-12-31", "valid_start":"2025-01-01", "valid_end":"2025-12-31"},
        {"train_start":"2022-01-03", "train_end":"2025-12-31", "valid_start":"2026-01-01", "valid_end":"2026-09-18"},
    ]
    # Walk-forward uses a compact robustness grid centered on scientifically
    # adjacent values to keep the full M3 script practical; the full 64-point
    # plateau grid is saved separately above.
    wf = walk_forward(df, cfg, folds, lookbacks=(2, 3, 5, 10), holds=(2, 3), stops=(0.03, 0.04))
    wf.to_csv(out / "walk_forward_summary.csv", index=False)

    cost = cost_sensitivity(df, cfg, selected)
    cost.to_csv(out / "cost_sensitivity.csv", index=False)

    equity, trades, metrics, rolling, rolling_summary = run_portfolio_config(df, cfg)
    symbol_attribution(trades).to_csv(out / "symbol_attribution.csv", index=False)
    leave_one_out(df, cfg).to_csv(out / "leave_one_out.csv", index=False)

    regimes = add_regimes(df)
    regimes.to_csv(out / "regime_labels.csv", index=False)
    regime_attribution(equity, trades, rolling, regimes).to_csv(out / "regime_attribution.csv", index=False)
    drawdown_episodes(equity, trades, regimes).to_csv(out / "drawdown_episodes.csv", index=False)
    trade_clustering(equity, trades).to_csv(out / "trade_clustering.csv", index=False)
    benchmarks(df, cfg["symbols"]).to_csv(out / "benchmark_comparison.csv", index=False)

    non = non_overlapping_10d(equity, trades)
    non_summary = {
        "overlapping": rolling_summary,
        "non_overlapping": {
            "count": int(len(non)),
            "mean_10d_return": float(non.portfolio_return.mean()),
            "median_10d_return": float(non.portfolio_return.median()),
            "p10": float(non.portfolio_return.quantile(.1)),
            "p90": float(non.portfolio_return.quantile(.9)),
            "probability_positive": float((non.portfolio_return > 0).mean()),
            **bootstrap_ci(non.portfolio_return),
        },
        "overlap_caveat": "Overlapping 10-day windows are descriptive and not independent samples.",
    }
    (out / "window_independence_summary.json").write_text(json.dumps(non_summary, indent=2, default=str), encoding="utf-8")

    print(f"Saved Milestone 3 artifacts to {out}")
    print("Selected region:", selected)
    print("Plateau:", plateau)
    print(wf.to_string(index=False))


if __name__ == "__main__":
    main()
