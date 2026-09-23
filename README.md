# Fin Trading Brain

Fin Trading Brain is a research-only semiconductor trading intelligence demo. The implemented architecture is intentionally simple:

```text
Alpha Lab deterministic rankings
+ QQQ SMA50 regime/risk gate
+ Bright Data live sourced evidence
+ Cognee persistent research memory when available
+ deterministic structured synthesis
= results/agent/daily_research_*.json
```

`ALLOW_ORDERS=false` must remain set. The project does not expose broker order tools, does not autonomously trade, and does not add new ML models or strategy optimization.

## Implemented architecture

1. **Alpha Lab** loads cached/historical artifacts and emits deterministic rankings with `as_of` timestamps.
2. **Regime/risk** uses the validated QQQ > SMA50 gate to allow/block new long candidates.
3. **Bright Data** performs live SERP/news requests, normalizes results, preserves real URLs, timestamps retrieval, canonicalizes/deduplicates URLs, and reports degraded status instead of fabricating sources.
4. **Cognee** stores compact structured research memories and recalls prior context when the configured external endpoint supports it; otherwise it degrades gracefully.
5. **Deterministic synthesis** builds a structured daily research brief without requiring an LLM.
6. **QuantConnect** remains the next independent V1 parity-validation step.

AWS/Bedrock/Strands are **optional / experimental integrations** only. They are not required for preflight, daily research, tests, or demo completion.

## Daily research

```bash
python scripts/daily_research.py
```

Outputs:
- terminal brief
- JSON artifact under `results/agent/`
- no trades executed

Required artifact fields include `brief_id`, `as_of`, `generated_at`, `quant_state`, `regime_state`, `risk_state`, `candidates`, `external_evidence`, `memory_context`, `conflicts`, `limitations`, `recommendation_state`, and `sources`.

## Live validation commands

```bash
python scripts/preflight.py
python scripts/test_brightdata_live.py
python scripts/ingest_memory.py --file results/agent/<artifact>.json
python scripts/recall_memory.py "MU semiconductor daily research"
```

These commands print safe metadata only and never print credentials.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
python scripts/preflight.py
pytest -q
```

Configure `.env` only for integrations you want to validate. Do not commit `.env`.

## Environment

Core safety:

```text
ALLOW_ORDERS=false
```

Live evidence:

```text
BRIGHTDATA_API_KEY=...
BRIGHTDATA_SERP_ZONE=...
BRIGHTDATA_API_URL=https://api.brightdata.com/request
```

Persistent memory:

```text
COGNEE_API_KEY=...
COGNEE_ENDPOINT=...
```

Optional / not required:

```text
AWS_REGION=...
AWS_PROFILE=...
STRANDS_MODEL_ID=...
```

## QuantConnect validation

QuantConnect/LEAN is independent execution validation, not autonomous trading. See `docs/QUANTCONNECT_VALIDATION.md` and `results/validation/schema.json`. No QuantConnect results are claimed unless produced by a real run.

## Safety

- `ALLOW_ORDERS=false` is checked by tests and preflight.
- No buy/sell/order/trade tool is registered with the research agent.
- Bright Data and Cognee credentials are loaded from environment only.
- Source URLs are preserved end-to-end.
- Missing integrations return `DEGRADED`/unavailable metadata rather than mocked success.
