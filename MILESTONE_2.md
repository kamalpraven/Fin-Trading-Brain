# Milestone 2 — Shared-Capital Portfolio Backtester

## Purpose

Replace Milestone-1 independent per-symbol backtests with one shared-capital portfolio simulation for historical research only. Official Conviction execution remains separate; `ALLOW_ORDERS` was not changed.

## Architecture

- `src/alpha_lab/portfolio_backtest.py` implements the portfolio engine, trade ledger, daily equity ledger, portfolio metrics, and rolling 10-trading-day horizon analysis.
- `src/alpha_lab/runner.py` now has portfolio helpers that reuse the existing feature and signal generation path.
- `scripts/run_portfolio_backtest.py` runs a config end-to-end and saves portfolio artifacts.
- `tests/test_portfolio_backtest.py` covers shared cash, next-open fills, no duplicate positions, max positions, exits, slippage, accounting, and rolling windows.

## Execution assumptions

- Signals are computed from completed bar `t` and can only enter at the next available open for that symbol.
- Exit decisions use completed prior-bar information and fill at the current open.
- Stop loss is modeled as a close-below-stop condition observed after the completed bar, not as an intraday stop order.
- Multiple same-day candidates are ranked deterministically by descending `signal_strength` if supplied, then symbol alphabetically.
- Long-only, fully paid positions; allocation is capped by available cash.
- Slippage is applied against the trader: buys at `open * (1 + slippage)`, sells at `open * (1 - slippage)`.

## Portfolio accounting model

- Starting cash defaults to `$100,000`.
- Each entry targets `fraction_per_trade * current portfolio equity` after same-day exits and mark-to-current open valuation.
- `max_positions` caps concurrent positions. `configs/semi_momentum.yaml` now explicitly sets `max_positions: 4`, so intended max exposure is about 80% before price drift.
- Daily ledger fields: `timestamp`, `cash`, `invested_value`, `total_equity`, `gross_exposure`, `number_open_positions`, `daily_return`, `drawdown`.
- Validation on the baseline artifacts found max `abs(cash + invested_value - total_equity)` of `2.91e-11` and max open positions of `4`.

## 10-day evaluation methodology

For each rolling block of 10 trading rows in the portfolio equity curve, the engine records start/end dates, portfolio return, entries, exits, within-window drawdown, average/max gross exposure, and whether any trade occurred. Aggregate statistics include mean/median, p10/p25/p75/p90, probability positive, probability zero-trade window, worst/best, and entry-count statistics.

## Files added/changed

Added:
- `src/alpha_lab/portfolio_backtest.py`
- `scripts/run_portfolio_backtest.py`
- `tests/test_portfolio_backtest.py`
- `MILESTONE_2.md`

Changed:
- `src/alpha_lab/runner.py`
- `configs/semi_momentum.yaml`
- `README.md`

Generated, ignored by git:
- `results/semi_momentum_portfolio_summary.json`
- `results/semi_momentum_portfolio_trades.csv`
- `results/semi_momentum_portfolio_equity.csv`
- `results/semi_momentum_rolling_10d.csv`

## Commands

```bash
pytest -q
python scripts/run_portfolio_backtest.py --config configs/semi_momentum.yaml
```

## Semiconductor shared-portfolio baseline

Using the existing semiconductor momentum signal, one shared `$100,000` account, 20% current-equity sizing, max 4 positions, 5 bps slippage, max hold 3 bars, reverse-day exit, and 4% close-based stop:

- total return: `44.0303%`
- Sharpe: `0.4747`
- max drawdown: `-28.9224%`
- trades: `1250`
- win rate: `45.84%`
- profit factor: `1.1059`
- average exposure: `37.23%`

This is a different capital model from Milestone-1 independent-symbol returns and should not be compared directly.

Rolling 10-trading-day distribution:

- mean: `0.3482%`
- median: `0.0070%`
- p10: `-4.4919%`
- p90: `5.5429%`
- probability positive: `50.04%`
- probability zero-trade window: `0.00%`
- worst: `-9.8146%`
- best: `15.3527%`

## Known limitations and assumptions

- Universe membership is static; survivorship assumptions are inherited from the configured symbol list.
- Daily bars do not model intraday stop execution; stops are close-observed and next-open filled to avoid lookahead.
- Corporate actions, borrow, commissions, taxes, and liquidity constraints beyond slippage are not modeled.
- Missing symbol dates fall back to last close for marking, although the current Alpaca daily universe appears aligned.
- Open positions remaining at the dataset end are marked in equity but not forced closed into the completed-trade log.
- The deterministic ranking interface is present but no predictive ranking model is used yet.
