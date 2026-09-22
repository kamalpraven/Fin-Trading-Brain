from __future__ import annotations

from typing import Any

from agent.memory.cognee_client import CogneeClient


def recall_similar_setups(query: str, limit: int = 5) -> dict[str, Any]:
    return CogneeClient().recall_research(query, limit)


def recall_symbol_history(symbol: str, limit: int = 5) -> dict[str, Any]:
    return CogneeClient().recall_research(f"symbol {symbol.upper()} semiconductor setup", limit)


def store_daily_research(report: dict[str, Any]) -> dict[str, Any]:
    return CogneeClient().remember_research(report)


def store_strategy_lesson(lesson: dict[str, Any] | str) -> dict[str, Any]:
    return CogneeClient().remember_strategy_lesson(lesson)


def memory_healthcheck() -> dict[str, Any]:
    return CogneeClient().healthcheck()
