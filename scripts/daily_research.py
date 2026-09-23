from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agent.config import integration_status
from agent.main import format_brief, run_daily_research


def main():
    print("Integration status:")
    for k, v in integration_status().items():
        state = "READY" if v.get("available") else v.get("status", "DEGRADED")
        print(f"  {k}: {state}" + (f" ({v.get('reason')})" if v.get("reason") else ""))
    brief = run_daily_research(persist=True, save=True)
    print(format_brief(brief))
    print(f"Saved: {brief.get('artifact_path')}")
    if "memory_store_result" in brief:
        ms = brief["memory_store_result"]
        print(f"Cognee persistence: {'stored' if ms.get('stored') else 'not stored'}" + (f" ({ms.get('reason')})" if ms.get('reason') else ""))


if __name__ == "__main__":
    main()
