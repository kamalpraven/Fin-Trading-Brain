from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from agent.tools.memory_tools import memory_healthcheck, recall_similar_setups


def _summarize(memories: list[dict]) -> list[dict]:
    out = []
    for item in memories:
        rm = item.get("research_memory") if isinstance(item, dict) else None
        if isinstance(rm, dict):
            evidence = rm.get("evidence_summary", []) or []
            out.append({
                "brief_id": rm.get("brief_id"),
                "as_of": rm.get("as_of"),
                "symbol": rm.get("symbol"),
                "ranking_count": len(rm.get("ranking", []) or []),
                "evidence_count": len(evidence),
                "sample_urls": [e.get("url") for e in evidence[:3] if e.get("url")],
                "outcome": rm.get("outcome"),
            })
        elif isinstance(item, dict):
            out.append({"dataset_name": item.get("dataset_name"), "text_chars": len(str(item.get("text") or item.get("search_result") or ""))})
    return out


def _safe_recall(query: str, limit: int) -> dict:
    health = memory_healthcheck()
    safe_health = {"available": health.get("available"), "status": health.get("status"), "reason": health.get("reason")}
    if not health.get("available"):
        return {"status": "DEGRADED", "health": safe_health, "query": query, "memory_count": 0, "memories": []}
    res = recall_similar_setups(query, limit)
    memories = res.get("memories", [])
    return {
        "status": "PASS" if res.get("available") else "DEGRADED",
        "health": safe_health,
        "query": query,
        "memory_count": len(memories),
        "memories": _summarize(memories),
        "reason": res.get("reason"),
    }


def main() -> int:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(description="Recall Cognee research memory in a separate process; prints safe metadata only.")
    p.add_argument("query", nargs="?", default="semiconductor daily research setup")
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    out = _safe_recall(args.query, args.limit)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["status"] in {"PASS", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
