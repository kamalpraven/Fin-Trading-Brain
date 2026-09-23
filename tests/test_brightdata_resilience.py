import json
from pathlib import Path

import pytest

from agent.main import run_research_agent
from agent.tools import brightdata_tools


class Resp:
    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if text is None and payload is not None else (text if text is not None else "")
        self.headers = headers or {"content-type": "application/json"}
    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def configure(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "secret-key")
    monkeypatch.setenv("BRIGHTDATA_MCP_URL", "https://brightdata.test/search")
    monkeypatch.delenv("BRIGHTDATA_SERP_ZONE", raising=False)


def test_valid_json_response(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(payload={"results": [{"title": "A", "url": "https://example.com/a", "snippet": "s"}]}))
    out = brightdata_tools.search_web("MU")
    assert out["status"] == "READY"
    assert out["results"][0]["freshness_status"] == "fresh"


def test_brightdata_wrapper_body(monkeypatch):
    configure(monkeypatch)
    body = json.dumps({"organic": [{"title": "A", "link": "https://example.com/a"}]})
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(payload={"body": body}))
    out = brightdata_tools.search_web("MU")
    assert out["available"] and out["results"][0]["url"] == "https://example.com/a"


def test_nested_provider_error(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(payload={"error": {"message": "bad zone"}}))
    out = brightdata_tools.search_web("MU")
    assert out["available"] is False
    assert "bad zone" in out["reason"]
    assert out["diagnostic"]["provider_error"] == "bad zone"


def test_http_502_retry_once(monkeypatch):
    configure(monkeypatch)
    calls = []
    def post(*a, **k):
        calls.append(1)
        return Resp(status_code=502, text="bad gateway") if len(calls) == 1 else Resp(payload={"results": [{"title": "A", "url": "https://example.com/a"}]})
    monkeypatch.setattr(brightdata_tools.requests, "post", post)
    out = brightdata_tools.search_web("MU", max_retries=1)
    assert out["available"]
    assert len(calls) == 2


def test_timeout_retry_once(monkeypatch):
    configure(monkeypatch)
    calls = []
    def post(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise brightdata_tools.requests.Timeout("timeout")
        return Resp(payload={"results": [{"title": "A", "url": "https://example.com/a"}]})
    monkeypatch.setattr(brightdata_tools.requests, "post", post)
    out = brightdata_tools.search_web("MU", max_retries=1)
    assert out["available"] and len(calls) == 2


def test_empty_body_and_html_and_malformed(monkeypatch):
    configure(monkeypatch)
    for resp in [Resp(text=""), Resp(text="<html>captcha</html>", headers={"content-type": "text/html"}), Resp(text='{"body": "{bad"}')]:
        monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, _resp=resp, **k: _resp)
        out = brightdata_tools.search_web("MU", max_retries=0)
        assert out["available"] is False
        assert out["status"] == "DEGRADED"


def test_no_retry_on_auth(monkeypatch):
    configure(monkeypatch)
    calls = []
    def post(*a, **k):
        calls.append(1)
        return Resp(status_code=401, payload={"detail": "invalid"})
    monkeypatch.setattr(brightdata_tools.requests, "post", post)
    out = brightdata_tools.search_web("MU", max_retries=1)
    assert out["status"] == "FAIL"
    assert len(calls) == 1


def test_partial_results_and_url_dedupe(monkeypatch):
    configure(monkeypatch)
    payload = {"results": [
        {"title": "no url"},
        {"title": "A", "url": "https://example.com/a?utm_source=x"},
        {"title": "dup", "url": "https://example.com/a"},
    ]}
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(payload=payload))
    out = brightdata_tools.search_web("MU")
    assert len(out["results"]) == 1
    assert out["results"][0]["canonical_url"] == "https://example.com/a"


def test_stale_fallback_marking_retains_retrieved_at():
    items = [{"title": "A", "url": "https://example.com/a", "retrieved_at": "old", "freshness_status": "fresh"}]
    out = brightdata_tools.mark_stale_fallback(items, "now", "failed")
    assert out[0]["retrieved_at"] == "old"
    assert out[0]["freshness_status"] == "stale_fallback"
    assert out[0]["brightdata_attempted_at"] == "now"


def test_failed_live_query_never_fake_fresh(monkeypatch, tmp_path):
    configure(monkeypatch)
    monkeypatch.setattr(brightdata_tools, "LAST_GOOD_PATH", tmp_path / "last_good.json")
    brightdata_tools.save_last_good_evidence([{"title": "A", "url": "https://example.com/a", "retrieved_at": "old", "freshness_status": "fresh"}], "q")
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(status_code=502, text="bad gateway"))
    out = run_research_agent("Analyze MU")
    assert out["external_evidence"][0]["freshness_status"] == "stale_fallback"
    assert out["brightdata_status"] == "DEGRADED"


def test_secrets_not_in_brightdata_result(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp(text="<html>captcha</html>"))
    out = brightdata_tools.search_web("MU", max_retries=0)
    assert "secret-key" not in json.dumps(out)


def test_allow_orders_false():
    assert "ALLOW_ORDERS=false" in Path(".env.example").read_text(encoding="utf-8")
