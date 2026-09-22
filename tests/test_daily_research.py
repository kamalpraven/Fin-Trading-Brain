import json
from pathlib import Path

from agent.main import run_daily_research
from agent.schemas import validate_brief


def test_daily_research_produces_json_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RESULTS_DIR", str(tmp_path))
    monkeypatch.delenv("COGNEE_API_KEY", raising=False)
    brief = run_daily_research(persist=True, save=True)
    path = Path(brief["artifact_path"])
    assert path.exists()
    obj = json.loads(path.read_text())
    assert validate_brief(obj)
    assert obj["memory_store_result"]["stored"] is False


def test_daily_research_cognee_attempted_only_when_available(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RESULTS_DIR", str(tmp_path))
    monkeypatch.delenv("COGNEE_API_KEY", raising=False)
    out = run_daily_research(persist=True, save=False)
    assert out["memory_store_result"]["available"] is False
