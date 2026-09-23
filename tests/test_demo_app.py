from pathlib import Path

from demo.app import COGNEE_MAP, latest_artifact, load_brief, render_home


def test_latest_artifact_resolution():
    path = latest_artifact()
    assert path is not None
    assert path.name.startswith("daily_research_")
    assert path.suffix == ".json"


def test_load_brief_graceful_missing(tmp_path):
    out = load_brief(tmp_path / "missing.json")
    assert out["available"] is False
    assert "No daily research artifact" in out["reason"]


def test_render_home_contains_core_panels():
    html = render_home()
    for text in ["Fin Trading Brain", "Market Regime", "Candidate Ranking", "Live Bright Data Evidence", "Cognee Knowledge Map", "ALLOW_ORDERS"]:
        assert text in html


def test_graph_path_resolution():
    assert COGNEE_MAP.name == "fin_trading_brain_map.html"
    assert "results" in str(COGNEE_MAP)
