# Fin Trading Brain — 60–90 Second Demo Script

Fin Trading Brain is a research-only semiconductor trading intelligence demo. It combines deterministic Alpha Lab rankings, a QQQ SMA50 risk gate, live Bright Data evidence, and persistent Cognee memory.

Start at the hero: this is not an autonomous trading bot. `ALLOW_ORDERS=false` is visible, and no trades are executed.

Move to the market regime panel. The system checks whether QQQ is above its 50-day moving average. That deterministic rule controls whether new long candidates are allowed or blocked.

Next, show the ranked semiconductor candidates. These ranks come from the Alpha Lab strategy artifacts, not from an LLM. The recommendation state summarizes whether the current setup is a candidate, watch, or blocked state.

Then show live evidence. Bright Data supplies source-preserving external evidence cards with URLs, sources, retrieval timestamps, and freshness labels. If live retrieval degrades, stale fallback evidence is clearly labeled rather than treated as fresh.

Finally, open the Cognee knowledge map. This visualizes persistent structured memory: research briefs, symbols, QQQ/SMA50 regime state, evidence, source URLs, hypotheses, and lessons. The point is continuity — tomorrow’s research can recall and build on today’s evidence.

Close with the safety panel: deterministic strategy, evidence-backed research, persistent memory, and no autonomous trading.
