from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse, unquote
import json
import time

import requests

from agent.config import load_agent_config

TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    return {"available": False, "reason": reason, "results": [], **extra}


def canonical_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(str(url))
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", urlencode(qs), ""))


def classify_source(url: str, source: str | None = None) -> str:
    host = (urlparse(url).netloc or source or "").lower()
    if any(x in host for x in ["sec.gov", "investor.", "ir."]) or host.endswith((".com", ".net")) and any(c in host for c in ["nvidia", "micron", "amd", "broadcom", "intel"]):
        return "primary/company source"
    if any(x in host for x in ["reuters", "bloomberg", "wsj", "cnbc", "marketwatch", "barrons", "ft.com", "finance.yahoo"]):
        return "established financial/news source"
    return "other source"


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    url = item.get("url") or item.get("link") or item.get("href") or item.get("display_link") or ""
    if isinstance(url, str) and url.startswith("/goto?"):
        q = dict(parse_qsl(urlparse(url).query))
        url = unquote(q.get("url", url))
    title = item.get("title") or item.get("name") or item.get("headline") or url
    snippet = item.get("snippet") or item.get("description") or item.get("text") or item.get("summary")
    source = item.get("source") or item.get("domain") or (urlparse(url).netloc if url else None)
    published = item.get("published_at") or item.get("date") or item.get("published") or item.get("time")
    canon = canonical_url(str(url))
    return {
        "title": str(title),
        "url": str(url),
        "canonical_url": canon,
        "snippet": None if snippet is None else str(snippet),
        "source": source,
        "source_quality": classify_source(str(url), source),
        "published_at": published,
        "retrieved_at": utc_now(),
    }


def deduplicate_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set(); out: list[dict[str, Any]] = []
    for r in results:
        key = r.get("canonical_url") or canonical_url(r.get("url", "")) or (r.get("title", "").lower(), r.get("source"))
        if str(key) in seen:
            continue
        seen.add(str(key)); out.append(r)
    return out


def _extract_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("body"), str):
        try:
            payload = json.loads(payload["body"])
        except Exception:
            pass
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("results") or payload.get("organic") or payload.get("news") or payload.get("items") or payload.get("data") or []
        if isinstance(raw, dict):
            raw = raw.get("results") or raw.get("organic") or raw.get("items") or []
    else:
        return []
    out = [_normalize(x) for x in raw if isinstance(x, dict)]
    return [r for r in out if str(r.get("url", "")).startswith(("http://", "https://"))]


def _nested_error(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for k in ("error", "errors", "message", "detail"):
            v = payload.get(k)
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                inner = _nested_error(v)
                if inner: return inner
            if isinstance(v, list) and v:
                inner = _nested_error(v[0])
                if inner: return inner
    return None


def _looks_blocked(text: str) -> bool:
    low = text.lower()
    return "captcha" in low or "cloudflare" in low or "502 bad gateway" in low or "proxy error" in low


def _direct_payload(query: str, max_results: int, news: bool) -> dict[str, Any]:
    cfg = load_agent_config()
    search = f"{query}"
    if news:
        search += " latest news"
    return {"zone": cfg.brightdata_serp_zone, "url": f"https://www.google.com/search?q={requests.utils.quote(search)}&num={max_results}", "format": "json"}


def search_web(query: str, max_results: int = 5, timeout: float = 20.0, news: bool = False) -> dict[str, Any]:
    cfg = load_agent_config()
    if not cfg.brightdata_configured:
        return _unavailable("BRIGHTDATA credentials not configured")
    use_direct = bool(cfg.brightdata_serp_zone)
    url = (cfg.brightdata_api_url if use_direct else cfg.brightdata_mcp_url) or "https://api.brightdata.com/request"
    headers = {"Authorization": f"Bearer {cfg.brightdata_api_key}", "Content-Type": "application/json"}
    payload = _direct_payload(query, max_results, news) if use_direct else {"query": query, "max_results": max_results, "news": news}
    last_reason = "unknown Bright Data failure"
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            text = resp.text[:4000]
            if resp.status_code in TRANSIENT_STATUS or _looks_blocked(text):
                last_reason = "Bright Data transient/blocking response (CAPTCHA/502/proxy)" if _looks_blocked(text) else f"Bright Data HTTP {resp.status_code}"
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1)); continue
            if resp.status_code >= 400:
                try: err = _nested_error(resp.json())
                except Exception: err = text[:300]
                return _unavailable(f"Bright Data HTTP {resp.status_code}: {err or 'request failed'}")
            try:
                data = resp.json()
            except Exception:
                return _unavailable("Bright Data malformed JSON response")
            if isinstance(data, dict) and isinstance(data.get("body"), str):
                if _looks_blocked(data["body"]):
                    return _unavailable("Bright Data transient/blocking response (CAPTCHA/502/proxy)")
                try:
                    body_data = json.loads(data["body"])
                    if isinstance(body_data, dict):
                        data = body_data
                except Exception:
                    return _unavailable("Bright Data malformed JSON response body")
            err = _nested_error(data)
            if err and not _extract_results(data):
                return _unavailable(f"Bright Data error: {err}")
            results = deduplicate_results(_extract_results(data))[:max_results]
            return {"available": True, "query": query, "news": news, "results": results, "retrieved_at": utc_now()}
        except requests.Timeout:
            last_reason = "Bright Data request failed: timed out"
        except (requests.RequestException, TimeoutError) as exc:
            last_reason = f"Bright Data request failed: {exc}"
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    return _unavailable(last_reason)


def healthcheck(timeout: float = 10.0) -> dict[str, Any]:
    res = search_web("semiconductor news", max_results=1, timeout=timeout, news=True)
    return {"available": bool(res.get("available")), "status": "READY" if res.get("available") else "UNAVAILABLE", "reason": res.get("reason"), "result_count": len(res.get("results", []))}


def research_symbol(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    query = f"{symbol} semiconductor earnings guidance AI HBM datacenter demand"
    res = search_web(query, max_results=5, news=True)
    res["symbol"] = symbol
    return res


def get_recent_semiconductor_news() -> dict[str, Any]:
    return search_web("latest semiconductor industry AI datacenter HBM earnings guidance", max_results=8, news=True)


def get_macro_context() -> dict[str, Any]:
    return search_web("latest macro market context Nasdaq QQQ rates semiconductors", max_results=5, news=True)


def fetch_page(url: str, timeout: float = 20.0) -> dict[str, Any]:
    cfg = load_agent_config()
    if not cfg.brightdata_configured:
        return {"available": False, "reason": "BRIGHTDATA credentials not configured", "url": url}
    try:
        endpoint = cfg.brightdata_api_url or cfg.brightdata_mcp_url
        payload = {"zone": cfg.brightdata_serp_zone, "url": url, "format": "raw"} if cfg.brightdata_api_url else {"url": url}
        resp = requests.post(endpoint, headers={"Authorization": f"Bearer {cfg.brightdata_api_key}", "Content-Type": "application/json"}, json=payload, timeout=timeout)
        resp.raise_for_status()
        return {"available": True, "url": url, "content": resp.text[:20000], "retrieved_at": utc_now()}
    except Exception as exc:
        return {"available": False, "reason": f"Bright Data request failed: {exc}", "url": url}
