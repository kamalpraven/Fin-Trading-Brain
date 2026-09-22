from __future__ import annotations

import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.config import integration_status
from agent.main import create_research_agent, format_brief, run_research_agent


def main():
    p = argparse.ArgumentParser(description="Alpha Lab semiconductor research agent")
    p.add_argument("--query", default=None)
    p.add_argument("--save", action="store_true")
    p.add_argument("--persist", action="store_true")
    args = p.parse_args()

    print("Integration status:")
    for k, v in integration_status().items():
        print(f"  {k}: {'READY' if v.get('available') else 'UNAVAILABLE'}" + (f" ({v.get('reason')})" if v.get('reason') else ""))

    agent = create_research_agent()
    if args.query:
        brief = run_research_agent(args.query, agent=agent, persist=args.persist, save=args.save)
        print(format_brief(brief))
        if brief.get("artifact_path"):
            print(f"Saved: {brief['artifact_path']}")
        return

    print("Enter research prompts. Ctrl+C to exit.")
    while True:
        try:
            query = input("alpha-agent> ").strip()
            if not query:
                continue
            brief = run_research_agent(query, agent=agent, persist=args.persist, save=args.save)
            print(format_brief(brief))
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break


if __name__ == "__main__":
    main()
