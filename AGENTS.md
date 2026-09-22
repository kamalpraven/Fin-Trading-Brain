# Pi / Codex operating rules

Pi: propose hypotheses, inspect results, challenge leakage/overfit, choose next experiment.
Codex: implement features/backtests/tests/sweeps, preserve experiment artifacts.

Rules:
1. Signals use only information available at the completed bar.
2. Fills occur after the signal is observable (default next open).
3. Never random-shuffle time-series splits.
4. Report zero-trade windows.
5. Change one major variable at a time outside designed sweeps.
6. Write experiment outputs to `results/`.
7. Keep official Conviction execution separate from this harness.
8. External orders must remain disabled by default.
