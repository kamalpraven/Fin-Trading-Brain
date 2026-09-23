# QuantConnect / LEAN Validation Handoff

Purpose: independently validate Alpha Lab execution semantics in LEAN without embedding QuantConnect in the research application.

## V0.x lessons

- Execution plumbing was validated separately from this repo.
- A duplicate-order/state bug was discovered when same-bar state and order placement were not separated.
- Corrected design: compute signals after close, persist target state, execute at the next session, and make order submission idempotent.

## V1 specification

- Universe: same semiconductor universe from `configs/semi_momentum.yaml`.
- Signal/ranking: actual Alpha Lab deterministic signal and ranking logic, not a proxy model.
- Holdings: use configured `max_hold`.
- Exit: reverse-day/strategy exit semantics from Alpha Lab.
- Stop behavior: match Alpha Lab stop configuration.
- Slippage: 5 bps.
- Regime: QQQ SMA50 hard gate for new entries.
- Execution: next-session orders only; no same-bar fill assumptions.
- Safety: paper/backtest only until explicitly approved; no autonomous live trading.

## Acceptance criteria

1. LEAN trades match local signal dates after accounting for next-session execution.
2. No duplicate orders for an unchanged target state.
3. QQQ SMA50 gate blocks new entries exactly when local gate is false.
4. Local vs LEAN portfolio metrics are compared with documented tolerances.
5. Any differences are explained by fills, holidays, data vendor differences, or fees/slippage.

## Comparison artifact schema

Store future comparison artifacts under `results/validation/` using the schema in `results/validation/schema.json`.

Do not fake QuantConnect results. This directory is prepared for later validation outputs only.
