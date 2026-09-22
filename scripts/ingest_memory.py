from __future__ import annotations

import argparse, json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools.memory_tools import store_daily_research, store_strategy_lesson


def main():
    p = argparse.ArgumentParser(description="Ingest a research artifact or lesson into Cognee")
    p.add_argument("--file", help="JSON research artifact")
    p.add_argument("--lesson", help="Strategy lesson text")
    args = p.parse_args()
    if args.file:
        obj = json.loads(Path(args.file).read_text(encoding="utf-8"))
        print(store_daily_research(obj))
    elif args.lesson:
        print(store_strategy_lesson(args.lesson))
    else:
        raise SystemExit("Provide --file or --lesson")


if __name__ == "__main__":
    main()
