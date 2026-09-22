from agent.memory.cognee_client import CogneeClient
from agent.tools import memory_tools


class Resp:
    status_code = 200
    text = "ok"
    def raise_for_status(self): pass
    def json(self): return {"results": [{"x": 1}]}


def test_cognee_unavailable(monkeypatch):
    monkeypatch.delenv("COGNEE_API_KEY", raising=False)
    monkeypatch.delenv("COGNEE_ENDPOINT", raising=False)
    c = CogneeClient()
    assert c.healthcheck()["available"] is False
    assert c.recall_research("x")["memories"] == []


def test_cognee_memory_write_contract(monkeypatch):
    monkeypatch.setenv("COGNEE_API_KEY", "k")
    monkeypatch.setenv("COGNEE_ENDPOINT", "https://cognee.test")
    monkeypatch.setattr("agent.memory.cognee_client.requests.post", lambda *a, **k: Resp())
    out = CogneeClient().remember_research({"a": 1})
    assert out["available"] and out["stored"]


def test_cognee_memory_recall_contract(monkeypatch):
    monkeypatch.setenv("COGNEE_API_KEY", "k")
    monkeypatch.setenv("COGNEE_ENDPOINT", "https://cognee.test")
    monkeypatch.setattr("agent.memory.cognee_client.requests.post", lambda *a, **k: Resp())
    out = memory_tools.recall_similar_setups("MU")
    assert out["available"] and isinstance(out["memories"], list)


def test_no_fabricated_memory(monkeypatch):
    monkeypatch.delenv("COGNEE_API_KEY", raising=False)
    monkeypatch.delenv("COGNEE_ENDPOINT", raising=False)
    out = memory_tools.recall_symbol_history("MU")
    assert out["available"] is False
    assert out["memories"] == []
