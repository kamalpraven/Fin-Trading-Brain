# Milestone 3 — Robustness, Walk-Forward Validation, and Parameter Plateau Analysis

## Research questions

Does the deterministic semiconductor momentum family contain a robust short-horizon signal that survives time splits, nearby parameters, costs, symbol removal, and simple market regimes?

No order execution was enabled. This remains historical research only.

## Experimental design

Primary 64-point grid:

- momentum lookback: `[2, 3, 5, 10]`
- max hold: `[1, 2, 3, 5]`
- stop loss: `[0.02, 0.03, 0.04, 0.05]`
- slippage: `5 bps`
- sizing fixed at `20%` current equity
- max positions fixed at `4`

Artifacts are in `results/m3/`.

## Execution assumptions

Two stop modes now exist:

- `close_next_open`: original comparable mode. Stop is observed on completed close and filled at next open.
- `daily_gap_aware`: if next open is through stop, fill next open; else if next low touches stop, fill stop price. Slippage is applied against the trader.

The baseline config remains on `close_next_open` unless explicitly changed.

## Overlapping-window caveat

Overlapping 10-trading-day windows are reported descriptively but are not independent. Milestone 3 also saves non-overlapping 10-day windows and a simple bootstrap confidence interval on their mean.

Baseline overlapping 10d: mean `0.3482%`, median `0.0070%`, p10 `-4.4919%`, p90 `5.5429%`, probability positive `50.04%`.

Non-overlapping 10d: count `118`, mean `0.5037%`, median `-0.0813%`, p10 `-3.3430%`, p90 `6.4704%`, probability positive `50.00%`, bootstrap mean CI `[-0.1446%, 1.1282%]`.

## Parameter plateau findings

64 configurations were evaluated. `93.75%` had profit factor above 1.0, but median 10-day return across the grid was slightly negative (`-0.0764%`).

Best scoring region by the robustness score was lookback `10`, max hold `2`, stop `2%`; neighboring configurations were mostly similar by profit factor (`88.9%` of local neighbors above 1.0), but local mean median-10d return was still slightly negative.

Average by lookback:

- lookback 2: PF `1.0898`, median 10d `0.0503%`, return `38.55%`, Sharpe `0.4296`
- lookback 3: PF `1.0793`, median 10d `-0.1088%`, return `31.16%`, Sharpe `0.3824`
- lookback 5: PF `1.0264`, median 10d `-0.3012%`, return `9.39%`, Sharpe `0.1882`
- lookback 10: PF `1.1216`, median 10d `-0.0642%`, return `48.50%`, Sharpe `0.5440`

Stops from 2%-5% behaved almost identically because many exits are driven by max-hold/reverse-day rather than stop loss.

## Walk-forward design and results

Chronological folds only:

1. Train 2022-2023, validate 2024
2. Train 2022-2024, validate 2025
3. Train 2022-2025, validate 2026 through 2026-09-18

For runtime practicality, walk-forward parameter selection used a compact adjacent robustness grid while the full 64-point plateau grid remains saved separately.

Validation results:

- Fold 1 selected: return `-0.14%`, Sharpe `0.0769`, drawdown `-13.73%`, PF `0.9981`; baseline did better at `16.42%`, Sharpe `0.8447`, PF `1.1857`.
- Fold 2 selected: return `34.55%`, Sharpe `1.6944`, drawdown `-11.75%`, PF `1.5100`; baseline return `19.62%`, Sharpe `0.9478`, PF `1.2521`.
- Fold 3 selected: return `-0.42%`, Sharpe `0.0948`, drawdown `-22.40%`, PF `0.9793`; baseline did better at `8.25%`, Sharpe `0.5684`, PF `1.0993`.

Selection is not stable enough to trust as an optimizer. The original baseline is competitive out-of-sample.

## Cost sensitivity

Using the selected full-sample region lookback `10`, hold `2`, stop `2%` without retuning:

- 0 bps: return `95.67%`, Sharpe `0.8666`, PF `1.2063`
- 5 bps: return `52.67%`, Sharpe `0.5807`, PF `1.1257`
- 10 bps: return `19.13%`, Sharpe `0.2942`, PF `1.0489`
- 20 bps: return `-27.43%`, Sharpe `-0.2793`, PF `0.9070`

The effect is highly cost-sensitive.

## Symbol attribution

Baseline net P&L by symbol:

- MU: `+$17,405`, PF `1.1960`
- NVDA: `+$13,261`, PF `1.2364`
- AMD: `+$9,489`, PF `1.1090`
- AVGO: `+$6,337`, PF `1.0841`
- AMAT: `-$5,631`, PF `0.9284`

Leave-one-out total returns stayed positive but ranged widely:

- remove NVDA: `26.29%`
- remove AMD: `38.82%`
- remove AVGO: `34.64%`
- remove AMAT: `57.27%`
- remove MU: `29.54%`

The result is not solely one ticker, but MU/NVDA contribute materially and AMAT detracted.

## Regime definitions and findings

Regimes use only available historical bars:

- QQQ above/below 50-day SMA
- QQQ 20-day realized volatility classified by expanding, shifted quantiles
- SPY above/below 50-day SMA

Trade behavior is regime-dependent:

- QQQ above SMA50: `869` trades, net `+$76,180`, PF `1.3151`
- QQQ below SMA50: `381` trades, net `-$35,318`, PF `0.7551`
- SPY positive trend: PF `1.2097`
- SPY negative trend: PF `0.8553`
- High-vol QQQ windows had negative 10d median (`-1.5317%`)

## Drawdown diagnosis

Largest drawdown episode:

- Start: `2022-02-09`
- Trough: `2022-10-14`
- Recovery: `2024-03-22`
- Max drawdown: `-28.92%`
- Duration: `531` bars
- Max concurrent positions: `4`
- Responsible symbols included AMD, NVDA, AMAT, AVGO
- Regime: QQQ below SMA50, medium vol

The failure mode is clustered long semiconductor exposure during adverse market trend regimes, not one isolated trade.

## Trade dependence

Trades are frequent and clustered:

- yearly trades: 2022 `236`, 2023 `273`, 2024 `255`, 2025 `289`, 2026 YTD `197`
- entries per trading day distribution: 1 entry on `283` days, 2 on `182`, 3 on `101`, 4 on `75`
- simultaneous positions: portfolio spent `310` days at 4 open positions
- turnover estimate: notional allocations about `252x` average equity over the full test

The trades are often correlated semiconductor bets rather than independent observations.

## Benchmarks

Buy-and-hold context:

- SPY: return `59.45%`, drawdown `-25.36%`, Sharpe `0.6586`
- QQQ: return `79.61%`, drawdown `-35.25%`, Sharpe `0.6534`
- Equal-weight semis: return `267.84%`, drawdown `-74.58%`, Sharpe `0.8069`

The strategy has lower drawdown than equal-weight semis but does not dominate passive benchmarks on raw return or Sharpe.

## Limitations

- Static universe; survivorship assumptions remain.
- Daily OHLC stop modeling is approximate.
- The walk-forward selector used a compact grid for runtime; full grid plateau is saved separately.
- Overlapping windows are descriptive only.
- Trade-level observations are not independent due to sector clustering.

## Final classification

**PROMISING BUT REGIME-DEPENDENT**

Rationale: the family has positive profit factor across much of the grid and is not solely one symbol, but performance is cost-sensitive, 10-day medians are weak, walk-forward selection is inconsistent, and losses concentrate in negative broad-market regimes.
