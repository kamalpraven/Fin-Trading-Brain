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

See [`MILESTONE_1.md`](MILESTONE_1.md).

You can verify the code without credentials:

```bash
python scripts/make_sample_data.py
python scripts/run_backtest.py --config configs/semi_momentum.yaml --csv data/sample_daily_bars.csv
pytest -q
```

Then create `.env` from `.env.example` using credentials from a **separate** Alpaca paper account and fetch real historical bars.
