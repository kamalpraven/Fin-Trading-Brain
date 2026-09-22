from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from agent.config import load_agent_config


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason, "results": []}


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    url = item.get("url") or item.get("link") or item.get("href") or ""
    title = item.get("title") or item.get("name") or url
    snippet = item.get("snippet") or item.get("description") or item.get("text")
    source = item.get("source") or (urlparse(url).netloc if url else None)
    return {"title": str(title), "url": str(url), "snippet": snippet, "source": source, "published_at": item.get("published_at") or item.get("date"), "retrieved_at": datetime.now(timezone.utc).isoformat()}


def _extract_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("results") or payload.get("organic") or payload.get("items") or payload.get("data") or []
        if isinstance(raw, dict):
            raw = raw.get("results") or raw.get("items") or []
    else:
        raw = []
    out = []
    for item in raw:
        if isinstance(item, dict):
            norm = _normalize(item)
            if norm["url"] or norm["title"]:
                out.append(norm)
    return out


def search_web(query: str, max_results: int = 5, timeout: float = 20.0) -> dict[str, Any]:
    cfg = load_agent_config()
    if not cfg.brightdata_configured:
        return _unavailable("BRIGHTDATA credentials not configured")
    try:
        resp = requests.post(
            cfg.brightdata_mcp_url,
            headers={"Authorization": f"Bearer {cfg.brightdata_api_key}", "Content-Type": "application/json"},
            json={"query": query, "max_results": max_results},
            timeout=timeout,
        )
        resp.raise_for_status()
        results = _extract_results(resp.json())[:max_results]
        return {"available": True, "query": query, "results": results}
    except Exception as exc:
        return _unavailable(f"Bright Data request failed: {exc}")


def research_symbol(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    query = f"{symbol} semiconductor earnings guidance AI HBM datacenter demand latest news"
    res = search_web(query, max_results=5)
    res["symbol"] = symbol
    return res


def get_recent_semiconductor_news() -> dict[str, Any]:
    return search_web("latest semiconductor industry AI datacenter HBM earnings guidance news", max_results=8)


def get_macro_context() -> dict[str, Any]:
    return search_web("latest macro market context Nasdaq QQQ rates semiconductors", max_results=5)


def fetch_page(url: str, timeout: float = 20.0) -> dict[str, Any]:
    cfg = load_agent_config()
    if not cfg.brightdata_configured:
        return {"available": False, "reason": "BRIGHTDATA credentials not configured", "url": url}
    try:
        resp = requests.post(cfg.brightdata_mcp_url, headers={"Authorization": f"Bearer {cfg.brightdata_api_key}", "Content-Type": "application/json"}, json={"url": url}, timeout=timeout)
        resp.raise_for_status()
        return {"available": True, "url": url, "content": resp.text[:20000], "retrieved_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"available": False, "reason": f"Bright Data request failed: {exc}", "url": url}
