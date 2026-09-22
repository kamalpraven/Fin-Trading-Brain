from __future__ import annotations

import argparse, json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_lab.config import load_config
from alpha_lab.data import load_cached
from alpha_lab.regime import RegimeSpec, build_regime_controls, default_m4_specs, summarize_control_usage
from alpha_lab.runner import run_portfolio_config
from alpha_lab.sweep import (
    filter_dates, result_row, non_overlapping_10d, bootstrap_ci, symbol_attribution,
    benchmarks, add_regimes, regime_attribution,
)


def turnover(trades: pd.DataFrame, equity: pd.DataFrame) -> float:
    return float(trades["allocation"].sum() / equity["total_equity"].mean()) if len(trades) and len(equity) else 0.0


def eval_spec(df: pd.DataFrame, cfg: dict, spec: RegimeSpec, slippage_bps: float | None = None):
    c = cfg.copy(); c["execution"] = dict(cfg["execution"])
    if slippage_bps is not None:
        c["execution"]["slippage_bps"] = float(slippage_bps)
    controls = build_regime_controls(df, spec)
    equity, trades, metrics, rolling, rolling_summary = run_portfolio_config(df, c, controls=controls)
    row = {
        "candidate": spec.name,
        "kind": spec.kind,
        "symbol": spec.symbol,
        "sma_days": spec.sma_days,
        "below_multiplier": spec.below_multiplier,
        "high_vol_multiplier": spec.high_vol_multiplier,
        "slippage_bps": c["execution"].get("slippage_bps", 5),
        **result_row(metrics, rolling_summary),
        "annualized_return": metrics.get("annualized_return"),
        "turnover_estimate": turnover(trades, equity),
        "max_concurrent_positions": int(equity["number_open_positions"].max()) if len(equity) else 0,
        "slippage_cost_estimate": float(trades["allocation"].sum() * (c["execution"].get("slippage_bps", 5) / 10000.0) * 2) if len(trades) else 0.0,
        **summarize_control_usage(controls),
    }
    return row, equity, trades, rolling, controls


def summarize_nonoverlap(candidate: str, equity: pd.DataFrame, trades: pd.DataFrame) -> dict:
    non = non_overlapping_10d(equity, trades)
    if non.empty:
        return {"candidate": candidate}
    return {
        "candidate": candidate,
        "count": int(len(non)),
        "mean_10d_return": float(non.portfolio_return.mean()),
        "median_10d_return": float(non.portfolio_return.median()),
        "p10": float(non.portfolio_return.quantile(.1)),
        "p90": float(non.portfolio_return.quantile(.9)),
        "probability_positive": float((non.portfolio_return > 0).mean()),
        **bootstrap_ci(non.portfolio_return),
    }


def diagnose_2022(candidate: str, equity: pd.DataFrame, trades: pd.DataFrame, controls: pd.DataFrame) -> dict:
    start = pd.Timestamp("2022-02-09", tz="UTC")
    end = pd.Timestamp("2022-10-14", tz="UTC")
    e = equity.copy(); e["timestamp"] = pd.to_datetime(e["timestamp"])
    tz = e["timestamp"].dt.tz
    if tz is not None:
        start = start.tz_convert(tz); end = end.tz_convert(tz)
    w = e[(e.timestamp >= start) & (e.timestamp <= end)]
    tr = trades.copy()
    if len(tr):
        tr["entry_time"] = pd.to_datetime(tr["entry_time"]); tr["exit_time"] = pd.to_datetime(tr["exit_time"])
        entries = tr[(tr.entry_time >= start) & (tr.entry_time <= end)]
        exits = tr[(tr.exit_time >= start) & (tr.exit_time <= end)]
        pnl = exits.pnl_dollars.sum()
    else:
        entries = exits = tr; pnl = 0.0
    c = controls.copy(); c["timestamp"] = pd.to_datetime(c["timestamp"])
    cw = c[(c.timestamp >= start) & (c.timestamp <= end)]
    dd = float((w.total_equity / w.total_equity.cummax() - 1).min()) if len(w) else np.nan
    return {"candidate": candidate, "period_drawdown": dd, "period_net_pnl_closed": float(pnl), "average_exposure": float(w.gross_exposure.mean()) if len(w) else np.nan, "entries": int(len(entries)), "exits": int(len(exits)), "pct_cash_control": float((cw.exposure_multiplier <= 0).mean()) if len(cw) else np.nan, "pct_reduced_control": float(((cw.exposure_multiplier > 0) & (cw.exposure_multiplier < 1)).mean()) if len(cw) else np.nan, "avg_control_multiplier": float(cw.exposure_multiplier.mean()) if len(cw) else np.nan}


def main():
    p = argparse.ArgumentParser(description="Milestone 4 deterministic regime controls")
    p.add_argument("--config", default="configs/semi_momentum.yaml")
    p.add_argument("--data", default="daily_bars")
    p.add_argument("--out", default="results/m4")
    args = p.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(args.config)
    df = load_cached(args.data); df["timestamp"] = pd.to_datetime(df["timestamp"])

    specs = default_m4_specs() + [
        RegimeSpec("qqq_sma40_gate", "trend_gate", symbol="QQQ", sma_days=40),
        RegimeSpec("qqq_sma60_gate", "trend_gate", symbol="QQQ", sma_days=60),
    ]
    summary=[]; nonrows=[]; diag=[]; saved={}
    for spec in specs:
        row, eq, tr, roll, controls = eval_spec(df, cfg, spec)
        summary.append(row); nonrows.append(summarize_nonoverlap(spec.name, eq, tr)); diag.append(diagnose_2022(spec.name, eq, tr, controls)); saved[spec.name]=(eq,tr,roll,controls)
        eq.to_csv(out / f"equity_{spec.name}.csv", index=False)
    pd.DataFrame(summary).to_csv(out / "regime_summary.csv", index=False)
    pd.DataFrame(nonrows).to_csv(out / "regime_10d_nonoverlapping.csv", index=False)
    pd.DataFrame(diag).to_csv(out / "regime_2022_diagnosis.csv", index=False)

    # Save overlapping summaries in flat form.
    overlap=[{k: row[k] for k in row if "10d" in k or k in ["candidate"]} for row in summary]
    pd.DataFrame(overlap).to_csv(out / "regime_10d_overlapping.csv", index=False)

    # Pick simple representatives, not a large optimized search.
    cost_specs = [s for s in specs if s.name in {"baseline", "qqq_sma50_gate", "spy_sma50_gate", "qqq_vol10_reduce50", "qqq_trend_gate_vol_reduce50"}]
    costs=[]
    for spec in cost_specs:
        for bps in [0,5,10,20]:
            row, *_ = eval_spec(df, cfg, spec, bps)
            costs.append(row)
    pd.DataFrame(costs).to_csv(out / "regime_cost_sensitivity.csv", index=False)

    folds = [
        ("2024", "2024-01-01", "2024-12-31"),
        ("2025", "2025-01-01", "2025-12-31"),
        ("2026_ytd", "2026-01-01", "2026-09-18"),
    ]
    wf_specs = cost_specs
    wf=[]
    for label, start, end in folds:
        sub = filter_dates(df, start, end)
        for spec in wf_specs:
            row, *_ = eval_spec(sub, cfg, spec)
            wf.append({"fold": label, **row})
    pd.DataFrame(wf).to_csv(out / "regime_walk_forward.csv", index=False)

    # Attribution and regime performance for baseline + main combined candidate.
    regimes = add_regimes(df)
    attr=[]; reg_attr=[]
    for name in ["baseline", "qqq_sma50_gate", "qqq_trend_gate_vol_reduce50"]:
        eq,tr,roll,_ = saved[name]
        a = symbol_attribution(tr); a.insert(0, "candidate", name); attr.append(a)
        r = regime_attribution(eq, tr, roll, regimes); r.insert(0, "candidate", name); reg_attr.append(r)
    pd.concat(attr, ignore_index=True).to_csv(out / "regime_symbol_attribution.csv", index=False)
    pd.concat(reg_attr, ignore_index=True).to_csv(out / "regime_by_market_state.csv", index=False)
    benchmarks(df, cfg["symbols"]).to_csv(out / "regime_benchmark_comparison.csv", index=False)

    print("Saved Milestone 4 artifacts to", out)
    print(pd.DataFrame(summary).sort_values(["max_drawdown", "profit_factor"], ascending=[False, False]).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
