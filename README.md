# Alpaca Alpha Lab

Research-first harness for the Conviction × Alpaca hackathon follow-on work.

Goals:
- fetch/caches Alpaca daily bars
- reproduce three strategy families
- run walk-forward and rolling 10-trading-day tests
- add parameter robustness and later ML/meta-models
- keep research/shadow execution separate from official Conviction competition execution

**Safety:** Do not submit external orders to the dedicated hackathon Alpaca account. Use a separate paper account for shadow execution.

Quick start:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# copy .env.example to .env and add paper keys
python scripts/fetch_data.py --symbols NVDA QQQ SPY META --start 2024-01-01 --end 2026-09-18
pytest -q
```

Initial strategy families:
1. semiconductor momentum
2. QQQ pullback/reversal
3. catalyst proxy (price-based until point-in-time news is added)

## Start here now

See [`MILESTONE_1.md`](MILESTONE_1.md), [`MILESTONE_2.md`](MILESTONE_2.md), [`MILESTONE_3.md`](MILESTONE_3.md), and [`MILESTONE_4.md`](MILESTONE_4.md).

You can verify the code without credentials:

```bash
python scripts/make_sample_data.py
python scripts/run_backtest.py --config configs/semi_momentum.yaml --csv data/sample_daily_bars.csv
pytest -q
```

Shared-capital portfolio backtest:

```bash
python scripts/run_portfolio_backtest.py --config configs/semi_momentum.yaml
```

Milestone 3 robustness sweep:

```bash
python scripts/run_sweep.py --config configs/semi_momentum.yaml
```

Milestone 4 deterministic regime controls:

```bash
python scripts/run_regime_analysis.py --config configs/semi_momentum.yaml
```

## Agentic Semiconductor Research MVP

Alpha Lab is the deterministic quantitative engine. The current validated regime-risk rule is the QQQ SMA50 hard gate: when QQQ is below its 50-day SMA, new long entries are blocked and existing positions follow deterministic exits. Strands is used as the agent orchestration layer when installed/configured, Bright Data provides fresh external evidence, and Cognee provides persistent research memory. QuantConnect/backtest execution validation remains independent.

This system is research-only and does not automatically trade. No brokerage order tools are exposed.

Run the interactive/one-shot agent:

```bash
python scripts/run_agent.py
python scripts/run_agent.py --query "Analyze MU" --save
```

Run the daily research workflow:

```bash
python scripts/daily_research.py
```

Optional environment variables:

```bash
AWS_REGION=
AWS_PROFILE=
STRANDS_MODEL_ID=
BRIGHTDATA_API_KEY=
BRIGHTDATA_MCP_URL=
COGNEE_API_KEY=
COGNEE_ENDPOINT=
```

If Bright Data or Cognee credentials are unavailable, the workflow degrades gracefully: deterministic Alpha Lab/regime tools still run, and the JSON artifact records the unavailable integration status rather than fabricating evidence or memory.

Then create `.env` from `.env.example` using credentials from a **separate** Alpaca paper account and fetch real historical bars.
