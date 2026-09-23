from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse, unquote
import json
import os
import time

import requests

from agent.config import load_agent_config

TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
AUTH_STATUS = {401, 403}
LAST_GOOD_PATH = Path("results/agent/brightdata_last_good.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _diagnostic(status_code: int | None = None, content_type: str | None = None, byte_length: int | None = None, provider_error: str | None = None, retry_count: int = 0) -> dict[str, Any]:
    return {"http_status": status_code, "content_type": content_type, "response_bytes": byte_length, "provider_error": provider_error, "retry_count": retry_count, "retrieved_at": utc_now()}


def _unavailable(reason: str, status: str = "DEGRADED", diagnostic: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"available": False, "status": status, "reason": reason, "results": [], "diagnostic": diagnostic or _diagnostic(), **extra}


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
        "freshness_status": "fresh",
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
    return "captcha" in low or "cloudflare" in low or "502 bad gateway" in low or "proxy error" in low or "unusual traffic" in low


def _parse_response_payload(resp: Any, retry_count: int) -> tuple[Any | None, str | None, bool, dict[str, Any]]:
    text = getattr(resp, "text", "") or ""
    status_code = getattr(resp, "status_code", None)
    content_type = ""
    try:
        content_type = resp.headers.get("content-type", "") if getattr(resp, "headers", None) else ""
    except Exception:
        content_type = ""
    diag = _diagnostic(status_code=status_code, content_type=content_type, byte_length=len(text.encode("utf-8", errors="ignore")), retry_count=retry_count)
    if not text.strip():
        return None, "Bright Data empty response body", True, diag
    if _looks_blocked(text):
        return None, "Bright Data transient/blocking response (CAPTCHA/502/proxy)", True, diag
    try:
        data = resp.json()
    except Exception:
        preview = text[:120].lower()
        if "<html" in preview or "<!doctype" in preview:
            return None, "Bright Data returned HTML/text instead of JSON", True, diag
        return None, "Bright Data malformed JSON response", True, diag
    err = _nested_error(data)
    diag["provider_error"] = err
    if isinstance(data, dict) and isinstance(data.get("body"), str):
        body = data["body"]
        diag["response_bytes"] = len(body.encode("utf-8", errors="ignore"))
        if not body.strip():
            return None, "Bright Data empty nested response body", True, diag
        if _looks_blocked(body):
            return None, "Bright Data transient/blocking response (CAPTCHA/502/proxy)", True, diag
        try:
            body_data = json.loads(body)
            if isinstance(body_data, (dict, list)):
                data = body_data
            else:
                return None, "Bright Data unexpected nested JSON schema", False, diag
        except Exception:
            if "<html" in body[:160].lower() or "<!doctype" in body[:160].lower():
                return None, "Bright Data nested body returned HTML/text instead of JSON", True, diag
            return None, "Bright Data malformed JSON response body", True, diag
    return data, None, False, diag


def _direct_payload(query: str, max_results: int, news: bool) -> dict[str, Any]:
    cfg = load_agent_config()
    search = f"{query}"
    if news:
        search += " latest news"
    return {"zone": cfg.brightdata_serp_zone, "url": f"https://www.google.com/search?q={requests.utils.quote(search)}&num={max_results}", "format": "json"}


def search_web(query: str, max_results: int = 5, timeout: float = 20.0, news: bool = False, max_retries: int = 1) -> dict[str, Any]:
    cfg = load_agent_config()
    if not cfg.brightdata_configured:
        return _unavailable("BRIGHTDATA credentials not configured", status="FAIL")
    use_direct = bool(cfg.brightdata_serp_zone)
    url = (cfg.brightdata_api_url if use_direct else cfg.brightdata_mcp_url) or "https://api.brightdata.com/request"
    headers = {"Authorization": f"Bearer {cfg.brightdata_api_key}", "Content-Type": "application/json"}
    payload = _direct_payload(query, max_results, news) if use_direct else {"query": query, "max_results": max_results, "news": news}
    last_reason = "unknown Bright Data failure"
    last_diag = _diagnostic()
    attempts = max(1, int(max_retries) + 1)
    for attempt in range(attempts):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            text = getattr(resp, "text", "") or ""
            diag = _diagnostic(status_code=resp.status_code, content_type=resp.headers.get("content-type", "") if getattr(resp, "headers", None) else "", byte_length=len(text.encode("utf-8", errors="ignore")), retry_count=attempt)
            last_diag = diag
            if resp.status_code in AUTH_STATUS:
                try: err = _nested_error(resp.json())
                except Exception: err = None
                diag["provider_error"] = err
                return _unavailable(f"Bright Data auth/config HTTP {resp.status_code}: {err or 'request not authorized'}", status="FAIL", diagnostic=diag)
            if resp.status_code in TRANSIENT_STATUS:
                last_reason = f"Bright Data HTTP {resp.status_code}"
                if attempt < attempts - 1:
                    time.sleep(0.5); continue
                return _unavailable(last_reason, diagnostic=diag)
            if resp.status_code >= 400:
                try: err = _nested_error(resp.json())
                except Exception: err = None
                diag["provider_error"] = err
                return _unavailable(f"Bright Data HTTP {resp.status_code}: {err or 'request failed'}", status="FAIL", diagnostic=diag)
            data, parse_error, retryable, diag = _parse_response_payload(resp, attempt)
            last_diag = diag
            if parse_error:
                last_reason = parse_error
                if retryable and attempt < attempts - 1:
                    time.sleep(0.5); continue
                return _unavailable(parse_error, diagnostic=diag)
            err = _nested_error(data)
            if err and not _extract_results(data):
                diag["provider_error"] = err
                return _unavailable(f"Bright Data error: {err}", status="FAIL" if "auth" in err.lower() else "DEGRADED", diagnostic=diag)
            results = deduplicate_results(_extract_results(data))[:max_results]
            if not results:
                return _unavailable("Bright Data returned no usable sourced results", diagnostic=diag)
            retrieved = utc_now()
            return {"available": True, "status": "READY", "query": query, "news": news, "results": results, "retrieved_at": retrieved, "diagnostic": diag}
        except requests.Timeout:
            last_reason = "Bright Data request failed: timed out"
            last_diag = _diagnostic(retry_count=attempt)
        except (requests.RequestException, TimeoutError) as exc:
            last_reason = f"Bright Data request failed: {exc}"
            last_diag = _diagnostic(retry_count=attempt)
        if attempt < attempts - 1:
            time.sleep(0.5)
    return _unavailable(last_reason, diagnostic=last_diag)


def save_last_good_evidence(items: list[dict[str, Any]], query: str | None = None) -> None:
    good = [x for x in items if isinstance(x, dict) and str(x.get("url", "")).startswith(("http://", "https://")) and x.get("freshness_status") == "fresh"]
    if not good:
        return
    LAST_GOOD_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_GOOD_PATH.write_text(json.dumps({"saved_at": utc_now(), "query": query, "results": good}, indent=2, default=str), encoding="utf-8")


def load_last_good_evidence() -> list[dict[str, Any]]:
    try:
        data = json.loads(LAST_GOOD_PATH.read_text(encoding="utf-8"))
        results = data.get("results", []) if isinstance(data, dict) else []
        return [x for x in results if isinstance(x, dict) and str(x.get("url", "")).startswith(("http://", "https://"))]
    except Exception:
        return []


def mark_stale_fallback(items: list[dict[str, Any]], attempted_at: str, failure_reason: str) -> list[dict[str, Any]]:
    out = []
    for item in items:
        x = dict(item)
        x["freshness_status"] = "stale_fallback"
        x["brightdata_attempted_at"] = attempted_at
        x["brightdata_failure_reason"] = failure_reason
        out.append(x)
    return out


def healthcheck(timeout: float = 10.0) -> dict[str, Any]:
    res = search_web("semiconductor news", max_results=1, timeout=timeout, news=True)
    status = "READY" if res.get("available") else res.get("status", "DEGRADED")
    return {"available": bool(res.get("available")), "status": status, "reason": res.get("reason"), "result_count": len(res.get("results", [])), "diagnostic": res.get("diagnostic")}


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
