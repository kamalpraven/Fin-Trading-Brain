from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "demo"
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"


def wait_ready(timeout: float = 12.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urlopen(URL, timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("demo server did not start")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([sys.executable, "-m", "demo.app", "--port", str(PORT)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        wait_ready()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1200}, device_scale_factor=1)
            page.goto(URL, wait_until="networkidle")
            for text in ["Fin Trading Brain", "Market Regime", "Candidate Ranking", "Live Bright Data Evidence", "Cognee Knowledge Map", "No trades executed"]:
                page.get_by_text(text, exact=False).first.wait_for(timeout=8000)
            page.screenshot(path=str(OUT / "home.png"), full_page=True)
            page.locator("#evidence").scroll_into_view_if_needed()
            page.locator("#evidence").screenshot(path=str(OUT / "evidence.png"))
            page.locator("#cognee-map").scroll_into_view_if_needed()
            page.locator("#cognee-map").screenshot(path=str(OUT / "cognee_map_panel.png"))
            graph = browser.new_page(viewport={"width": 1440, "height": 1000})
            graph.goto(URL + "/graph", wait_until="domcontentloaded")
            graph.screenshot(path=str(OUT / "cognee_map.png"), full_page=True)
            browser.close()
        print(f"Screenshots saved under {OUT}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
