from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AgentConfig:
    aws_region: str | None
    aws_profile: str | None
    strands_model_id: str | None
    brightdata_api_key: str | None
    brightdata_mcp_url: str | None
    cognee_api_key: str | None
    cognee_endpoint: str | None
    results_dir: str = "results/agent"

    @property
    def brightdata_configured(self) -> bool:
        return bool(self.brightdata_api_key and self.brightdata_mcp_url)

    @property
    def cognee_configured(self) -> bool:
        return bool(self.cognee_api_key and self.cognee_endpoint)


def load_agent_config() -> AgentConfig:
    return AgentConfig(
        aws_region=os.getenv("AWS_REGION") or None,
        aws_profile=os.getenv("AWS_PROFILE") or None,
        strands_model_id=os.getenv("STRANDS_MODEL_ID") or None,
        brightdata_api_key=os.getenv("BRIGHTDATA_API_KEY") or None,
        brightdata_mcp_url=os.getenv("BRIGHTDATA_MCP_URL") or None,
        cognee_api_key=os.getenv("COGNEE_API_KEY") or None,
        cognee_endpoint=os.getenv("COGNEE_ENDPOINT") or None,
        results_dir=os.getenv("AGENT_RESULTS_DIR", "results/agent"),
    )


def integration_status() -> dict:
    cfg = load_agent_config()
    try:
        import strands  # type: ignore  # noqa: F401
        strands_status = {"available": True, "mode": "strands"}
    except Exception as exc:
        strands_status = {"available": False, "mode": "local_fallback", "reason": str(exc)}
    return {
        "alpha_lab": {"available": True, "status": "READY"},
        "strands": strands_status,
        "brightdata": {"available": cfg.brightdata_configured, "reason": None if cfg.brightdata_configured else "BRIGHTDATA credentials not configured"},
        "cognee": {"available": cfg.cognee_configured, "reason": None if cfg.cognee_configured else "COGNEE credentials not configured"},
    }
