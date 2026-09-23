from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

ActionStatus = Literal["candidate", "watch", "blocked_by_regime", "needs_more_evidence"]


@dataclass
class ExternalEvidence:
    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None


@dataclass
class CandidateAction:
    symbol: str
    status: ActionStatus
    rationale: str


@dataclass
class ResearchBrief:
    timestamp: str
    query: str
    market_regime: dict[str, Any]
    quantitative_state: dict[str, Any]
    quantitative_candidates: list[dict[str, Any]]
    external_evidence: list[dict[str, Any]] = field(default_factory=list)
    memory_context: list[dict[str, Any]] = field(default_factory=list)
    risk: dict[str, Any] = field(default_factory=dict)
    candidate_actions: list[dict[str, Any]] = field(default_factory=list)
    synthesis: str = ""
    catalysts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    conflicts: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    data_freshness: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    integration_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_brief(obj: dict[str, Any]) -> bool:
    legacy_required = ["timestamp", "query", "market_regime", "quantitative_state", "quantitative_candidates", "candidate_actions", "limitations"]
    daily_required = ["brief_id", "as_of", "generated_at", "quant_state", "regime_state", "risk_state", "candidates", "external_evidence", "memory_context", "conflicts", "limitations", "recommendation_state", "sources"]
    if not (all(k in obj for k in legacy_required) or all(k in obj for k in daily_required)):
        return False
    if obj.get("recommendation_state") and obj.get("recommendation_state") not in {"CANDIDATE", "WATCH", "BLOCKED"}:
        return False
    forbidden = {"executed", "bought", "sold", "buy", "sell"}
    for action in obj.get("candidate_actions", []):
        if str(action.get("status", "")).lower() in forbidden:
            return False
    return True
