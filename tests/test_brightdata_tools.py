from agent.tools import brightdata_tools


class Resp:
    status_code = 200
    text = "ok"
    headers = {"content-type": "application/json"}
    def raise_for_status(self): pass
    def json(self):
        return {"results": [{"title": "T", "url": "https://example.com/a", "snippet": "S"}]}


def test_brightdata_unavailable(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_MCP_URL", raising=False)
    out = brightdata_tools.search_web("NVDA")
    assert out["available"] is False
    assert out["results"] == []


def test_brightdata_normalized_search_schema(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "x")
    monkeypatch.setenv("BRIGHTDATA_MCP_URL", "https://brightdata.test/search")
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Resp())
    out = brightdata_tools.search_web("NVDA")
    assert out["available"]
    item = out["results"][0]
    assert {"title", "url", "snippet", "source", "published_at", "retrieved_at"} <= set(item)


def test_brightdata_timeout_error(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "x")
    monkeypatch.setenv("BRIGHTDATA_MCP_URL", "https://brightdata.test/search")
    def boom(*a, **k): raise TimeoutError("timeout")
    monkeypatch.setattr(brightdata_tools.requests, "post", boom)
    out = brightdata_tools.search_web("NVDA")
    assert out["available"] is False
    assert "failed" in out["reason"]


def test_brightdata_malformed_result_handling(monkeypatch):
    class Bad(Resp):
        def json(self): return {"weird": {"x": 1}}
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "x")
    monkeypatch.setenv("BRIGHTDATA_MCP_URL", "https://brightdata.test/search")
    monkeypatch.setattr(brightdata_tools.requests, "post", lambda *a, **k: Bad())
    out = brightdata_tools.search_web("NVDA")
    assert out["available"] is False and out["results"] == []
