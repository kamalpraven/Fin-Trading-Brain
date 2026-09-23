from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from agent.config import load_agent_config
from agent.tools import alpha_tools, brightdata_tools, market_tools, memory_tools

REQUIRED_PACKAGES = ["pandas", "numpy", "yaml", "dotenv", "requests"]


def line(label: str, state: str, reason: str | None = None) -> str:
    out = f"{label:<24} {state}"
    if reason:
        out += f" ({reason})"
    return out


def git_ignores_env() -> bool:
    try:
        out = subprocess.run(["git", "check-ignore", ".env"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.returncode == 0
    except Exception:
        gi = ROOT / ".gitignore"
        return gi.exists() and ".env" in gi.read_text(encoding="utf-8")


def main() -> int:
    load_dotenv(ROOT / ".env")
    cfg = load_agent_config()
    required_failure = False
    lines: list[str] = ["FIN TRADING BRAIN PREFLIGHT", ""]

    deps_missing = [p for p in REQUIRED_PACKAGES if importlib.util.find_spec(p) is None]
    deps_ready = not deps_missing
    lines.append(line("Python dependencies", "READY" if deps_ready else "FAIL", ", ".join(deps_missing) if deps_missing else None)); required_failure |= not deps_ready

    ignore_ok = git_ignores_env()
    lines.append(line(".env gitignored", "READY" if ignore_ok else "FAIL", None if ignore_ok else ".env is not ignored")); required_failure |= not ignore_ok

    allow_orders = os.getenv("ALLOW_ORDERS", "false").strip().lower() == "false"
    lines.append(line("ALLOW_ORDERS", "false" if allow_orders else "FAIL", None if allow_orders else "must remain false")); required_failure |= not allow_orders

    alpha = alpha_tools.get_latest_rankings(); qqq = market_tools.get_qqq_regime()
    alpha_ready = bool(alpha.get("available")); qqq_ready = bool(qqq.get("available"))
    lines.append(line("Alpha artifacts", "READY" if alpha_ready else "FAIL", alpha.get("reason"))); required_failure |= not alpha_ready
    lines.append(line("QQQ SMA50 regime", "READY" if qqq_ready else "FAIL", qqq.get("reason"))); required_failure |= not qqq_ready

    bd_creds = cfg.brightdata_configured
    bd = brightdata_tools.healthcheck(timeout=10) if bd_creds else {"available": False, "reason": "BRIGHTDATA credentials not configured"}
    lines.append(line("Bright Data env", "READY" if bd_creds else "DEGRADED", None if bd_creds else "not configured"))
    lines.append(line("Bright Data live query", "READY" if bd.get("available") else "DEGRADED", bd.get("reason")))

    cog_creds = cfg.cognee_configured
    cog = memory_tools.memory_healthcheck() if cog_creds else {"available": False, "reason": "COGNEE credentials not configured"}
    lines.append(line("Cognee env", "READY" if cog_creds else "DEGRADED", None if cog_creds else "not configured"))
    lines.append(line("Cognee health", "READY" if cog.get("available") else "DEGRADED", cog.get("reason")))

    for d in [Path(cfg.results_dir), Path("results/validation")]:
        try:
            full = ROOT / d if not d.is_absolute() else d
            full.mkdir(parents=True, exist_ok=True)
            test = full / ".write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink()
            writable = True; reason = None
        except Exception as exc:
            writable = False; reason = str(exc)
        lines.append(line(f"Writable {d}", "READY" if writable else "FAIL", reason)); required_failure |= not writable

    strands_import = importlib.util.find_spec("strands") is not None
    lines.append(line("Strands", "OUT OF SCOPE / DEFERRED", "installed but unused" if strands_import else "not installed; deterministic fallback available"))
    lines.append(line("AWS/Bedrock", "OUT OF SCOPE / DEFERRED", "not used in Milestone 7"))

    lines.append("")
    lines.append("Required result: " + ("PASS" if not required_failure else "FAIL"))
    lines.append("Live integrations: Bright Data=" + ("READY" if bd.get("available") else "DEGRADED") + ", Cognee=" + ("READY" if cog.get("available") else "DEGRADED"))
    print("\n".join(lines))
    return 1 if required_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
