from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from agent.tools.brightdata_tools import healthcheck, search_web


def main() -> int:
    load_dotenv(ROOT / ".env")
    health = healthcheck(timeout=20)
    res = search_web("AMAT MU NVDA semiconductor earnings AI HBM latest news", max_results=5, timeout=30, news=True)
    real_urls = [r for r in res.get("results", []) if str(r.get("url", "")).startswith(("http://", "https://"))]
    status = "PASS" if res.get("available") and real_urls else "FAIL" if res.get("available") else "DEGRADED"
    print(json.dumps({
        "status": status,
        "result_count": len(real_urls),
        "retrieved_at": res.get("retrieved_at"),
        "sample_sources": [{"title": r.get("title"), "url": r.get("url"), "source": r.get("source"), "retrieved_at": r.get("retrieved_at")} for r in real_urls[:3]],
        "health": {"available": health.get("available"), "status": health.get("status"), "reason": health.get("reason")},
        "reason": res.get("reason"),
    }, indent=2))
    return 0 if status in {"PASS", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
