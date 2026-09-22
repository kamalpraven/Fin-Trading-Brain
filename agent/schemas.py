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
    limitations: list[str] = field(default_factory=list)
    integration_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_brief(obj: dict[str, Any]) -> bool:
    required = ["timestamp", "query", "market_regime", "quantitative_state", "quantitative_candidates", "candidate_actions", "limitations"]
    if not all(k in obj for k in required):
        return False
    forbidden = {"executed", "bought", "sold"}
    for action in obj.get("candidate_actions", []):
        if str(action.get("status", "")).lower() in forbidden:
            return False
    return True
