from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

_PLACEHOLDER_TOKENS = {"", "your_serp_zone", "your_aws_profile", "your_bedrock_model_id"}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    lowered = v.lower()
    if lowered.startswith("placeholder_") or lowered.startswith("https://your-") or lowered in _PLACEHOLDER_TOKENS:
        return None
    return v


@dataclass(frozen=True)
class AgentConfig:
    aws_region: str | None
    aws_profile: str | None
    strands_model_id: str | None
    brightdata_api_key: str | None
    brightdata_serp_zone: str | None
    brightdata_api_url: str | None
    brightdata_mcp_url: str | None
    cognee_api_key: str | None
    cognee_endpoint: str | None
    results_dir: str = "results/agent"

    @property
    def brightdata_configured(self) -> bool:
        return bool(self.brightdata_api_key and (self.brightdata_mcp_url or self.brightdata_serp_zone))

    @property
    def cognee_configured(self) -> bool:
        return bool(self.cognee_api_key and self.cognee_endpoint)

    @property
    def aws_optional_configured(self) -> bool:
        return bool(self.aws_region and self.strands_model_id)


def load_agent_config() -> AgentConfig:
    if "PYTEST_CURRENT_TEST" not in os.environ:
        load_dotenv(Path(".env"))
    return AgentConfig(
        aws_region=_clean(os.getenv("AWS_REGION")),
        aws_profile=_clean(os.getenv("AWS_PROFILE")),
        strands_model_id=_clean(os.getenv("STRANDS_MODEL_ID")),
        brightdata_api_key=_clean(os.getenv("BRIGHTDATA_API_KEY")),
        brightdata_serp_zone=_clean(os.getenv("BRIGHTDATA_SERP_ZONE")),
        brightdata_api_url=_clean(os.getenv("BRIGHTDATA_API_URL")) or "https://api.brightdata.com/request",
        brightdata_mcp_url=_clean(os.getenv("BRIGHTDATA_MCP_URL")),
        cognee_api_key=_clean(os.getenv("COGNEE_API_KEY")),
        cognee_endpoint=_clean(os.getenv("COGNEE_ENDPOINT")),
        results_dir=os.getenv("AGENT_RESULTS_DIR", "results/agent"),
    )


def integration_status() -> dict:
    cfg = load_agent_config()
    try:
        import strands  # type: ignore  # noqa: F401
        strands_status = {"available": True, "mode": "optional", "required": False}
    except Exception as exc:
        strands_status = {"available": False, "mode": "deterministic_fallback", "required": False, "reason": str(exc)}
    return {
        "alpha_lab": {"available": True, "status": "READY", "required": True},
        "aws_bedrock": {"available": False, "required": False, "status": "OUT OF SCOPE / DEFERRED", "reason": "not used in Milestone 7"},
        "strands": {**strands_status, "available": False, "status": "OPTIONAL / DEFERRED", "reason": "not used in Milestone 7"},
        "brightdata": {"available": cfg.brightdata_configured, "required": False, "reason": None if cfg.brightdata_configured else "BRIGHTDATA credentials not configured"},
        "cognee": {"available": cfg.cognee_configured, "required": False, "reason": None if cfg.cognee_configured else "COGNEE credentials not configured"},
    }
