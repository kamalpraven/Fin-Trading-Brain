# Milestone 1 — Reproducible Baselines

## Objective

Get a clean local research loop working before adding Pi/autoresearch or ML.

## Definition of done

- [ ] Separate Alpaca paper credentials stored in `.env`
- [ ] `ALLOW_ORDERS=false`
- [ ] Daily bars cached locally for the initial universe
- [ ] Three baseline configs run end-to-end
- [ ] Result tables written to `results/`
- [ ] Rolling 10-trading-day metrics produced
- [ ] Tests pass
- [ ] First experiment note committed

## Initial universe

- Semiconductor momentum: NVDA, AMD, AVGO, AMAT, MU
- Pullback research: QQQ
- Catalyst proxy: META, TSLA, NVDA, AMD, GOOGL, AMZN
- Benchmarks/context to fetch: SPY, QQQ

## Commands

```bash
python scripts/check_setup.py
python scripts/fetch_data.py --symbols NVDA AMD AVGO AMAT MU QQQ SPY META TSLA GOOGL AMZN --start 2022-01-01 --end 2026-09-19
python scripts/run_backtest.py --config configs/semi_momentum.yaml
python scripts/run_backtest.py --config configs/qqq_pullback.yaml
python scripts/run_backtest.py --config configs/catalyst_proxy.yaml
pytest -q
```

## Offline smoke test

Before touching Alpaca credentials:

```bash
python scripts/make_sample_data.py
python scripts/run_backtest.py --config configs/semi_momentum.yaml --csv data/sample_daily_bars.csv
pytest -q
```

Synthetic results are only a software test; they have no trading meaning.

## Milestone 2

Replace independent single-symbol tests with a true multi-symbol portfolio engine with max-position limits, capital competition, benchmark comparison, and saved trade logs/equity curves.
