# Milestone 4 — Deterministic Regime-Aware Risk Control

## Purpose

Test the hypothesis that much of the semiconductor momentum strategy's failure comes from clustered long exposure during hostile broad-market regimes, especially when QQQ is below its 50-day SMA. No alpha signal redesign, ML, order execution, or QuantConnect changes were made.

## Files created / changed

Created:
- `src/alpha_lab/regime.py`
- `scripts/run_regime_analysis.py`
- `tests/test_regime.py`
- `MILESTONE_4.md`
- `results/m4/*`

Changed:
- `src/alpha_lab/portfolio_backtest.py`
- `src/alpha_lab/runner.py`
- `.gitignore`
- `README.md`

## Tests

`pytest -q`: `25 passed`.

## Implementation

The portfolio engine now accepts optional daily controls with:

- `allow_entries`
- `exposure_multiplier`

Controls are keyed to the completed signal bar, so a regime observed after day `t` can affect entries at day `t+1` open. If controls are disabled or multiplier is `1.0`, baseline behavior is unchanged. Existing positions still exit under existing max-hold, reverse-day, and stop rules.

## Candidates tested

- Baseline: no control
- QQQ SMA50 hard gate
- QQQ SMA50 reduced exposure at 0.5x
- SPY SMA50 hard gate
- SPY SMA50 reduced exposure at 0.5x
- QQQ 10-day realized-volatility 0.5x throttle using expanding shifted 67th percentile
- QQQ SMA50 hard gate + high-vol 0.5x cap
- QQQ SMA50 0.5x reduction + high-vol 0.5x cap
- QQQ SMA40/SMA60 hard-gate neighborhood checks

## Main full-sample results at 5 bps

| Candidate | Return | Sharpe | Max DD | PF | Trades | Avg exposure |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 44.03% | 0.4747 | -28.92% | 1.1059 | 1250 | 37.23% |
| QQQ SMA50 gate | 42.83% | 0.5352 | -26.70% | 1.1495 | 895 | 27.06% |
| QQQ SMA50 reduce50 | 42.85% | 0.5161 | -25.86% | 1.1244 | 1250 | 31.60% |
| SPY SMA50 gate | 30.84% | 0.4141 | -31.50% | 1.1111 | 925 | 27.64% |
| SPY SMA50 reduce50 | 33.83% | 0.4334 | -28.60% | 1.1004 | 1250 | 31.74% |
| QQQ vol10 reduce50 | 34.27% | 0.4263 | -28.58% | 1.0925 | 1250 | 33.92% |
| QQQ gate + vol reduce | 38.34% | 0.5163 | -26.86% | 1.1460 | 895 | 25.58% |
| QQQ reduce + vol reduce | 39.61% | 0.5058 | -26.03% | 1.1230 | 1250 | 30.31% |

QQQ trend controls improved PF, Sharpe, turnover, and drawdown modestly while retaining most return. SPY controls were weaker.

## Cost sensitivity

Representative candidates:

| Candidate | 0 bps PF / return | 5 bps PF / return | 10 bps PF / return | 20 bps PF / return |
|---|---:|---:|---:|---:|
| Baseline | 1.1879 / 85.04% | 1.1059 / 44.03% | 1.0279 / 12.12% | 0.8840 / -32.03% |
| QQQ SMA50 gate | 1.2349 / 70.93% | 1.1495 / 42.83% | 1.0688 / 19.37% | 0.9210 / -16.61% |
| SPY SMA50 gate | 1.1984 / 57.51% | 1.1111 / 30.84% | 1.0288 / 8.69% | 0.8790 / -24.97% |
| QQQ vol10 reduce50 | 1.1746 / 68.63% | 1.0925 / 34.27% | 1.0149 / 6.92% | 0.8729 / -32.17% |
| QQQ gate + vol reduce | 1.2334 / 63.95% | 1.1460 / 38.34% | 1.0637 / 16.74% | 0.9142 / -16.85% |

QQQ gate survives 10 bps with PF above 1 and has less 20 bps damage than baseline, but 20 bps remains failing.

## Walk-forward comparison at 5 bps

| Fold | Candidate | Return | Sharpe | Max DD | PF |
|---|---|---:|---:|---:|---:|
| 2024 | Baseline | 16.42% | 0.8447 | -19.81% | 1.1857 |
| 2024 | QQQ gate | 8.83% | 0.6106 | -15.60% | 1.1608 |
| 2024 | SPY gate | 1.24% | 0.1577 | -21.59% | 1.0203 |
| 2024 | Vol reduce | 14.37% | 0.8769 | -14.56% | 1.2044 |
| 2024 | QQQ gate + vol | 6.45% | 0.4949 | -14.36% | 1.1313 |
| 2025 | Baseline | 19.62% | 0.9478 | -18.95% | 1.2521 |
| 2025 | QQQ gate | 41.02% | 2.2211 | -9.71% | 1.8107 |
| 2025 | SPY gate | 43.58% | 2.3331 | -9.71% | 1.8555 |
| 2025 | Vol reduce | 11.59% | 0.6598 | -18.20% | 1.1637 |
| 2025 | QQQ gate + vol | 33.97% | 1.9711 | -9.71% | 1.7039 |
| 2026 YTD | Baseline | 8.25% | 0.5684 | -18.83% | 1.0993 |
| 2026 YTD | QQQ gate | 6.56% | 0.5306 | -17.89% | 1.1427 |
| 2026 YTD | SPY gate | 13.60% | 0.9291 | -13.98% | 1.2741 |
| 2026 YTD | Vol reduce | 2.34% | 0.2665 | -15.12% | 1.0329 |
| 2026 YTD | QQQ gate + vol | 2.65% | 0.3116 | -14.37% | 1.0797 |

Regime control improved drawdown stability in most folds but often reduced return. It did not create uniformly superior performance.

## 2022 drawdown diagnosis

Baseline 2022-02-09 to 2022-10-14:

- period drawdown: -26.51%
- closed P&L: -$23,251
- average exposure: 30.42%
- entries/exits: 158 / 159

Key candidates:

| Candidate | Period DD | Closed P&L | Avg exposure | Entries | Cash/reduced control |
|---|---:|---:|---:|---:|---:|
| QQQ SMA50 gate | -17.08% | -$16,761 | 9.61% | 48 | cash 73.68% |
| QQQ SMA50 reduce50 | -20.76% | -$19,105 | 19.58% | 158 | reduced 73.68% |
| SPY SMA50 gate | -22.88% | -$22,564 | 11.47% | 60 | cash 70.76% |
| QQQ vol reduce50 | -24.40% | -$22,208 | 24.44% | 158 | reduced 34.50% |
| QQQ gate + vol reduce | -17.01% | -$16,688 | 9.50% | 48 | cash 73.68% |
| QQQ SMA60 gate | -16.46% | -$16,134 | 8.44% | 42 | cash 77.19% |

The QQQ trend gate activated as intended and materially reduced the diagnosed 2022 failure mode.

## 10-day results

Non-overlapping 10-day windows:

| Candidate | Mean | Median | P10 | P90 | Prob positive |
|---|---:|---:|---:|---:|---:|
| Baseline | 0.5037% | -0.0813% | -3.3430% | 6.4704% | 50.00% |
| QQQ SMA50 gate | 0.4325% | 0.0000% | -2.3678% | 4.3788% | 44.07% |
| QQQ SMA50 reduce50 | 0.4640% | -0.1279% | -2.5694% | 4.9513% | 49.15% |
| QQQ gate + vol reduce | 0.3643% | 0.0000% | -2.3393% | 3.7748% | 44.07% |

Regime controls reduce downside tails but also reduce positive-window frequency and upside.

## Regime attribution after controls

QQQ SMA50 gate reduced below-SMA trade count from 381 to 36, but residual below-SMA trades from positions opened before transitions still lost money. QQQ-below 10-day median improved from -0.2776% to 0.0%, and p10 improved from -4.5243% to -1.4829%.

## Benchmark comparison

Context benchmarks unchanged:

- SPY buy-and-hold: return 59.45%, drawdown -25.36%, Sharpe 0.6586
- QQQ buy-and-hold: return 79.61%, drawdown -35.25%, Sharpe 0.6534
- Equal-weight semis: return 267.84%, drawdown -74.58%, Sharpe 0.8069

The QQQ gate improves strategy risk metrics versus baseline but still does not dominate passive benchmarks on raw return or Sharpe.

## Research classification

**PROMISING BUT STILL REGIME-SENSITIVE**

The QQQ SMA50 hard gate directly mitigates the diagnosed structural failure, lowers drawdown and turnover, improves PF and Sharpe, and survives 10 bps with PF > 1. However, it sacrifices positive-window frequency, still fails at 20 bps, and walk-forward folds remain mixed.

## Three most important findings

1. QQQ trend gating is the cleanest deterministic control: it reduced the 2022 failure drawdown from -26.51% to about -17% and cut turnover materially.
2. Volatility throttling alone is weaker than trend gating; it helps some drawdowns but erodes return and does not solve the main hostile-trend problem.
3. The edge remains friction-sensitive and regime-sensitive; risk controls improve robustness but do not create a robust standalone strategy.

## Recommended Milestone 5

Test execution realism and trade-quality improvements without adding ML: liquidity/volume filters, limit/close-vs-open fill sensitivity, forced liquidation on regime transition, and a simple sector/beta exposure cap. Keep the QQQ SMA50 gate as the primary risk-control candidate and validate out-of-sample with the same walk-forward/cost gates.
