# MILESTONE 7 — Deterministic Research Brain + Live Evidence/Memory

## Architecture

Final M7 architecture is LLM-free on the critical path:

1. Deterministic Alpha Lab ranking engine
2. QQQ SMA50 regime/risk engine
3. Bright Data current external evidence with source URLs
4. Cognee persistent external research memory
5. Deterministic synthesis into structured research briefs
6. QuantConnect/LEAN as independent strategy/execution validator

AWS, Bedrock, Anthropic/Claude, OpenAI-through-Bedrock, and Strands are out of scope for Milestone 7. Existing code is preserved only as harmless optional/deferred functionality and is not required by preflight, tests, or the daily pipeline.

## Files changed / created

Changed:
- `.env.example`
- `.gitignore`
- `README.md`
- `agent/config.py`
- `agent/main.py`
- `agent/memory/cognee_client.py`
- `agent/schemas.py`
- `agent/tools/brightdata_tools.py`
- `scripts/daily_research.py`
- `scripts/ingest_memory.py`

Created:
- `scripts/preflight.py`
- `scripts/recall_memory.py`
- `scripts/test_brightdata_live.py`
- `tests/test_milestone7_contracts.py`
- `docs/QUANTCONNECT_VALIDATION.md`
- `results/validation/schema.json`
- `MILESTONE_7.md`

Existing untracked `MILESTONE_6.md` was preserved and not overwritten.

## Tests

Full suite result:

```text
85 passed
```

Coverage added for:
- AWS/Bedrock not required
- deterministic fallback without LLM
- Cognee graceful degradation and persistence contract
- Bright Data normalization, URL dedupe, nested errors, timestamps, no fabricated URLs
- `ALLOW_ORDERS=false`
- daily research required schema
- no trading tool exposure

## Cognee live status

Status: **PASS**

Optional knowledge-map addition: `scripts/visualize_cognee.py` reuses the hosted Cognee tenant/dataset and writes `results/cognee/fin_trading_brain_map.html` plus `results/cognee/fin_trading_brain_graph.json`. Cognee ingestion now writes structured production-tagged research memories for ResearchBrief, SymbolMemory, Regime, Evidence, Source URLs, hypotheses, and future Outcome/Lesson records. Visualization uses native hosted Cognee output when appropriate and falls back to local rendering of real Cognee graph data only when native HTML is unavailable or explicit test-junk filtering is needed.

Validated external persistence flow:

1. `python scripts/daily_research.py` stored a compact structured research memory remotely in Cognee dataset `fin_trading_brain`.
2. A separate process ran `python scripts/recall_memory.py "brief-20260923 AMAT" --limit 2`.
3. The separate process recalled the saved memory and printed safe metadata only.

Latest recall metadata included:
- `brief_id`: `brief-20260923-065842-c3f17ad2`
- `symbol`: `AMAT`
- `ranking_count`: `5`
- `evidence_count`: `8`
- sample real source URLs retained

Implementation details:
- credentials loaded only from environment
- `X-API-Key` auth used for Cognee SaaS API
- `/api/v1/add_text` + `/api/v1/cognify` used for persistence
- `/api/v1/search` with `CHUNKS` and `onlyContext=true` used for deterministic recall
- no credentials printed
- degraded result returned if health, store, or recall fails

## Bright Data live status

Status: **PASS**

Validated command:

```bash
python scripts/test_brightdata_live.py
```

Latest result returned 5 real sourced results with preserved URLs, including examples from TradingView, Yahoo Finance, and YouTube. Each normalized result contains:
- `title`
- `url`
- `snippet`
- `source`
- `published_at` when available
- `retrieved_at`

Adapter handles:
- explicit timeout
- limited retry
- HTTP errors
- nested Bright Data errors
- 502/CAPTCHA/proxy blocking text
- malformed JSON / malformed nested body
- canonical URL normalization
- deduplication
- no fabricated results

## Daily research status

Status: **PASS**

Validated command:

```bash
python scripts/daily_research.py
```

Latest artifact:

```text
results/agent/daily_research_20260923_135746.json
```

Pipeline completed without AWS/Bedrock/Strands and saved a structured JSON brief with required fields:
- `brief_id`
- `as_of`
- `generated_at`
- `quant_state`
- `regime_state`
- `risk_state`
- `candidates`
- `external_evidence`
- `memory_context`
- `conflicts`
- `limitations`
- `recommendation_state`
- `sources`

No trades were executed.

## Preflight status

Status: **PASS**

Validated command:

```bash
python scripts/preflight.py
```

Latest required checks:
- Python dependencies: READY
- `.env` gitignored: READY
- `ALLOW_ORDERS`: false
- Alpha artifacts: READY
- QQQ SMA50 regime: READY
- Bright Data env/live query: READY
- Cognee env/health: READY
- results directories writable: READY
- Strands: OUT OF SCOPE / DEFERRED
- AWS/Bedrock: OUT OF SCOPE / DEFERRED

## Evaluation harness status

Searched repository and parent folders for `evals/eval_runner.py` / `eval_runner.py` before creating anything. No project evaluation harness was found in this checkout or searched parent folders.

Therefore the previously reported Milestone 6 evaluation cannot currently be reproduced from this checkout. No prior evaluation results are invented here. Existing `MILESTONE_6.md` was preserved for discrepancy review.

## Security checks

- `.env` remains gitignored.
- `.env.example` contains placeholders only.
- credentials are loaded from environment only.
- no Bright Data or Cognee credentials are printed.
- `ALLOW_ORDERS=false` remains the required safety state.
- no buy/sell/order/trade tools are exposed to the research agent.
- source URLs are preserved end-to-end.

## Limitations

- Bright Data is a live external dependency and can return DEGRADED on timeout, CAPTCHA/proxy, malformed body, or provider errors.
- Cognee persistence depends on Cognee SaaS API availability and successful cognify/search operations.
- Quant data remains cached/historical unless refreshed.
- QuantConnect/LEAN V1 parity validation has not yet been run.
- No LLM provider is used or added for M7 synthesis.

## Remaining blockers

1. Produce real QuantConnect/LEAN V1 comparison artifacts.
2. Refresh Alpha Lab market data if a newer `as_of` is required.
3. Optionally refine evidence quality filters after more live Bright Data samples.

## M7 FINAL STATUS

- Alpha/risk engine: **READY**
- QQQ regime: **READY**
- Bright Data: **READY with graceful transient degradation handling**
- Cognee persistence: **READY**
- Cognee structured memory: **READY**
- Cognee knowledge graph: **READY**
- Daily research pipeline: **READY**
- Preflight required result: **PASS**
- `ALLOW_ORDERS=false`
- AWS/Bedrock/Strands: **OUT OF SCOPE**
- QuantConnect parity: **separate validation track**
- Tests: **85 passed**
- Latest graph: **263 nodes / 912 edges**
- Latest live Bright Data test: **PASS, 5 results**
- Latest daily research artifact: `results/agent/daily_research_20260923_135746.json`

Bright Data freshness behavior:
- Fresh live results are tagged as `fresh` and keep their own `retrieved_at` timestamps.
- If Bright Data transiently fails and prior real evidence exists, daily research may use it only as `stale_fallback` with the original `retrieved_at`, current attempted time, and failure reason.
- If no valid prior evidence exists, no fake evidence is produced.

Known final limitation:
- Bright Data provider can transiently return empty or malformed nested responses. This is handled via limited retry, safe diagnostics, explicit `DEGRADED` semantics, and fallback logic without silently treating stale evidence as fresh.

## Next step

Run QuantConnect V1 parity validation and populate `results/validation/` with real local-vs-LEAN comparison artifacts.
