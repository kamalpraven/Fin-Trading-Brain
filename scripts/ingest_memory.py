from __future__ import annotations

import argparse, json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from agent.memory.cognee_client import compact_research_summary
from agent.tools.memory_tools import memory_healthcheck, recall_similar_setups, remember_outcome, store_daily_research, store_strategy_lesson


def _print_safe(obj: dict) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main():
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(description="Ingest a research artifact or lesson into Cognee; prints safe metadata only")
    p.add_argument("--file", help="JSON research artifact")
    p.add_argument("--lesson", help="Strategy lesson text")
    p.add_argument("--recall", help="Recall/query Cognee memory")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--health", action="store_true")
    p.add_argument("--outcome", help="Outcome text for a prior brief/symbol")
    p.add_argument("--brief-id", help="Brief id for --outcome")
    p.add_argument("--symbol", help="Symbol for --outcome")
    p.add_argument("--observed-at", help="Observation timestamp for --outcome")
    p.add_argument("--dry-run", action="store_true", help="Show compact memory summary without storing")
    args = p.parse_args()
    if args.health:
        _print_safe(memory_healthcheck())
    elif args.file:
        obj = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if args.dry_run:
            _print_safe({"dry_run": True, "summary": compact_research_summary(obj)})
        else:
            res = store_daily_research(obj)
            _print_safe({"status": "PASS" if res.get("stored") else "DEGRADED", "stored": res.get("stored", False), "brief_id": obj.get("brief_id"), "symbol": compact_research_summary(obj).get("symbol"), "structured_memories": res.get("structured_memories"), "evidence_objects": res.get("evidence_objects"), "symbols": res.get("symbols"), "source_url_count": len(res.get("source_urls", []) or []), "reason": res.get("reason")})
    elif args.outcome:
        if not args.brief_id or not args.symbol:
            raise SystemExit("--outcome requires --brief-id and --symbol")
        res = remember_outcome(args.brief_id, args.symbol, args.outcome, lesson=args.lesson, observed_at=args.observed_at)
        _print_safe({"status": "PASS" if res.get("stored") else "DEGRADED", "stored": res.get("stored", False), "brief_id": args.brief_id, "symbol": args.symbol, "reason": res.get("reason")})
    elif args.lesson:
        res = store_strategy_lesson(args.lesson)
        _print_safe({"status": "PASS" if res.get("stored") else "DEGRADED", "stored": res.get("stored", False), "reason": res.get("reason")})
    elif args.recall:
        res = recall_similar_setups(args.recall, args.limit)
        _print_safe({"status": "PASS" if res.get("available") else "DEGRADED", "query": args.recall, "memory_count": len(res.get("memories", [])), "memories": res.get("memories", []), "reason": res.get("reason")})
    else:
        raise SystemExit("Provide --file, --lesson, --recall, or --health")


if __name__ == "__main__":
    main()
