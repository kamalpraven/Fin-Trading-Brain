import json
from pathlib import Path

import scripts.visualize_cognee as viz
from agent.memory.cognee_client import CogneeClient


class Resp:
    def __init__(self, payload=None, text="", status_code=200):
        self._payload = payload
        self.text = text
        self.status_code = status_code
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")
    def json(self):
        return self._payload


def test_visualization_output_dir_creation(monkeypatch, tmp_path):
    class FakeClient:
        def visualize_graph_json(self, **kwargs):
            return {"available": True, "dataset": "fin_trading_brain", "dataset_id": "ds", "query": kwargs.get("query"), "nodes": [{"id": "n1", "name": "AMAT", "type": "Entity"}], "links": []}
        def visualize_graph_html(self, **kwargs):
            return {"available": True, "html": "<html>native</html>"}
    monkeypatch.setattr(viz, "CogneeClient", FakeClient)
    out = viz.build_visualization("AMAT", 10, 2, tmp_path / "nested")
    assert Path(out["html_path"]).exists()
    assert Path(out["json_path"]).exists()
    assert out["mode"] == "native_cognee_html"


def test_empty_cognee_response_graceful(monkeypatch, tmp_path):
    class FakeClient:
        def visualize_graph_json(self, **kwargs):
            return {"available": True, "dataset": "fin_trading_brain", "nodes": [], "links": []}
        def visualize_graph_html(self, **kwargs):
            return {"available": False, "reason": "no native"}
    monkeypatch.setattr(viz, "CogneeClient", FakeClient)
    out = viz.build_visualization("missing", 10, 2, tmp_path)
    assert out["status"] == "DEGRADED"
    assert Path(out["html_path"]).exists()


def test_malformed_graph_response_handled(monkeypatch):
    monkeypatch.setenv("COGNEE_API_KEY", "secret-token")
    monkeypatch.setenv("COGNEE_ENDPOINT", "https://cognee.test")
    def fake_get(url, **kwargs):
        if url.endswith("/api/v1/datasets/"):
            return Resp([{"id": "ds", "name": "fin_trading_brain"}])
        return Resp(["not", "a", "dict"])
    monkeypatch.setattr("agent.memory.cognee_client.requests.get", fake_get)
    out = CogneeClient().visualize_graph_json("AMAT")
    assert out["available"] is False
    assert "Malformed" in out["reason"]


def test_node_cap_respected(monkeypatch):
    monkeypatch.setenv("COGNEE_API_KEY", "secret-token")
    monkeypatch.setenv("COGNEE_ENDPOINT", "https://cognee.test")
    nodes = [{"id": f"n{i}", "name": f"node{i}"} for i in range(5)]
    links = [{"source": "n0", "target": "n1"}, {"source": "n3", "target": "n4"}]
    def fake_get(url, **kwargs):
        if url.endswith("/api/v1/datasets/"):
            return Resp([{"id": "ds", "name": "fin_trading_brain"}])
        return Resp({"nodes": nodes, "links": links})
    monkeypatch.setattr("agent.memory.cognee_client.requests.get", fake_get)
    out = CogneeClient().visualize_graph_json("AMAT", max_nodes=2)
    assert len(out["nodes"]) == 2
    assert len(out["links"]) == 1


def test_no_fabricated_nodes_in_local_html():
    graph = {"dataset": "fin_trading_brain", "nodes": [{"id": "real", "name": "Real Node"}], "links": []}
    html = viz.local_html_from_graph(graph)
    assert "Real Node" in html
    assert "AMAT" not in html
    assert "NVDA" not in html


def test_obvious_test_junk_filter():
    graph = {"nodes": [{"id": "real", "name": "Real Node"}, {"id": "test", "name": "M7_TEST_fake"}], "links": [{"source": "real", "target": "test"}]}
    filtered, removed = viz.filter_obvious_test_junk(graph)
    assert removed == 1
    assert len(filtered["nodes"]) == 1
    assert filtered["links"] == []


def test_hosted_cognee_config_reused(monkeypatch):
    monkeypatch.setenv("COGNEE_API_KEY", "secret-token")
    monkeypatch.setenv("COGNEE_ENDPOINT", "https://hosted.example")
    c = CogneeClient()
    assert c.endpoint == "https://hosted.example"
    assert c.dataset_name == "fin_trading_brain"


def test_visualization_result_does_not_expose_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNEE_API_KEY", "super-secret-key")
    class FakeClient:
        def visualize_graph_json(self, **kwargs):
            return {"available": True, "dataset": "fin_trading_brain", "nodes": [{"id": "n1", "name": "AMAT"}], "links": []}
        def visualize_graph_html(self, **kwargs):
            return {"available": False, "reason": "fallback"}
    monkeypatch.setattr(viz, "CogneeClient", FakeClient)
    out = viz.build_visualization("AMAT", 10, 2, tmp_path)
    text = json.dumps(out) + Path(out["json_path"]).read_text(encoding="utf-8") + Path(out["html_path"]).read_text(encoding="utf-8")
    assert "super-secret-key" not in text


def test_allow_orders_false_in_example_for_visualization():
    assert "ALLOW_ORDERS=false" in Path(".env.example").read_text(encoding="utf-8")
