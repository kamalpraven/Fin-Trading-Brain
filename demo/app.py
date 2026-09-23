from __future__ import annotations

import argparse
import json
import mimetypes
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "results" / "agent"
COGNEE_MAP = ROOT / "results" / "cognee" / "fin_trading_brain_map.html"


def latest_artifact() -> Path | None:
    files = sorted(AGENT_DIR.glob("daily_research_*.json"))
    return files[-1] if files else None


def load_brief(path: Path | None = None) -> dict:
    path = path or latest_artifact()
    if not path or not path.exists():
        return {"available": False, "reason": "No daily research artifact found"}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj["available"] = True
        obj["artifact_path"] = str(path.relative_to(ROOT))
        return obj
    except Exception as exc:
        return {"available": False, "reason": f"Could not read artifact: {exc}"}


def _status_chip(label: str, state: str, kind: str = "ok") -> str:
    return f'<span class="chip {kind}"><span class="dot"></span>{escape(label)}: {escape(state)}</span>'


def _fmt(value, fallback="—") -> str:
    return escape(str(value)) if value not in (None, "", []) else fallback


def render_home() -> str:
    brief = load_brief()
    if not brief.get("available"):
        body = f"""
        <section class="hero"><div><p class="eyebrow">Research-only demo</p><h1>Fin Trading Brain</h1><p class="subtitle">No artifact found. Run <code>python scripts/daily_research.py</code>.</p></div></section>
        <main class="grid"><article class="card"><h2>Missing data</h2><p>{_fmt(brief.get('reason'))}</p></article></main>
        """
        return _page(body)

    regime = brief.get("regime_state", {}) or brief.get("market_regime", {})
    qqq = regime.get("qqq", {}) if isinstance(regime, dict) else {}
    risk_control = regime.get("risk_control", {}) if isinstance(regime, dict) else {}
    candidates = brief.get("candidates") or brief.get("quantitative_candidates") or []
    evidence = [e for e in (brief.get("external_evidence") or []) if e.get("available", True) is not False and e.get("url")]
    memory = brief.get("memory_context") or []
    freshness = brief.get("evidence_freshness_summary") or brief.get("data_freshness", {}).get("evidence_freshness_summary") or {}
    bright = brief.get("brightdata_status") or brief.get("data_freshness", {}).get("brightdata_status") or "UNKNOWN"
    cognee_ready = "READY" if memory and memory[0].get("available", True) is not False else "READY" if brief.get("memory_store_result", {}).get("stored") else "DEGRADED"
    qqq_state = "Above SMA50" if qqq.get("qqq_above_sma50") else "Below SMA50"
    allow = "Allowed" if risk_control.get("new_entries_allowed") else "Blocked"

    hero = f"""
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Live evidence • Persistent memory • Research only</p>
        <h1>Fin Trading Brain</h1>
        <p class="subtitle">Deterministic quant research + live evidence + persistent memory for semiconductor trading research.</p>
        <div class="chips">
          {_status_chip('Bright Data', bright, 'ok' if bright == 'READY' else 'warn')}
          {_status_chip('Cognee', cognee_ready, 'ok')}
          {_status_chip('QQQ Regime', qqq_state, 'ok' if qqq.get('qqq_above_sma50') else 'warn')}
          {_status_chip('ALLOW_ORDERS', 'false', 'safe')}
        </div>
      </div>
      <div class="hero-card">
        <div class="big-number">{_fmt(brief.get('recommendation_state'))}</div>
        <p>Recommendation state</p>
        <small>Artifact: {_fmt(brief.get('artifact_path'))}</small>
      </div>
    </section>
    """

    regime_panel = f"""
    <article class="card regime-card" id="regime">
      <div class="card-head"><span>Market Regime</span><strong>{escape(allow)}</strong></div>
      <h2>QQQ &gt; SMA50: {_fmt(qqq.get('qqq_above_sma50'))}</h2>
      <div class="metric-row"><span>QQQ close</span><b>{_fmt(qqq.get('qqq_close'))}</b></div>
      <div class="metric-row"><span>SMA50</span><b>{_fmt(qqq.get('qqq_sma50'))}</b></div>
      <div class="metric-row"><span>Source timestamp</span><b>{_fmt(qqq.get('as_of') or brief.get('as_of'))}</b></div>
      <p class="muted">Existing positions follow deterministic exits; no forced liquidation from regime gate.</p>
    </article>
    """

    rows = "".join(
        f"<tr><td>{_fmt(c.get('rank'))}</td><td><b>{_fmt(c.get('symbol'))}</b></td><td>{_fmt(c.get('signal'))}</td><td>{_fmt(round(float(c.get('score', 0)), 4) if c.get('score') is not None else None)}</td></tr>"
        for c in candidates[:8]
    )
    ranking_panel = f"""
    <article class="card wide" id="ranking">
      <div class="card-head"><span>Candidate Ranking</span><strong>{_fmt(brief.get('recommendation_state'))}</strong></div>
      <table><thead><tr><th>Rank</th><th>Symbol</th><th>Signal</th><th>Score</th></tr></thead><tbody>{rows}</tbody></table>
      <p class="muted">{_fmt(brief.get('synthesis') or brief.get('hypothesis'))}</p>
    </article>
    """

    evidence_cards = "".join(
        f"""
        <a class="evidence-card" href="{escape(e.get('url'))}" target="_blank" rel="noreferrer">
          <div class="source">{_fmt(e.get('symbol'))} • {_fmt(e.get('source'))}</div>
          <h3>{_fmt(e.get('title'))}</h3>
          <p>{_fmt(e.get('snippet'))}</p>
          <footer><span>{_fmt(e.get('freshness_status', 'unknown'))}</span><span>{_fmt(e.get('retrieved_at'))}</span></footer>
        </a>
        """ for e in evidence[:9]
    ) or '<p class="muted">No live or fallback evidence available in the latest artifact.</p>'
    evidence_panel = f"""
    <article class="card wide" id="evidence">
      <div class="card-head"><span>Live Bright Data Evidence</span><strong>{escape(str(freshness))}</strong></div>
      <div class="evidence-grid">{evidence_cards}</div>
    </article>
    """

    memory_summary = "Cognee memory recalled" if memory else "No memory context in artifact"
    memory_panel = f"""
    <article class="card" id="memory">
      <div class="card-head"><span>Persistent Memory</span><strong>Cognee</strong></div>
      <h2>{len(memory)} memory items</h2>
      <p>{escape(memory_summary)}</p>
      <p class="muted">Structured memories connect research briefs, symbols, regime state, evidence URLs, hypotheses, and outcomes.</p>
      <a class="button" href="/graph" target="_blank">Open full knowledge map</a>
    </article>
    """

    graph_panel = f"""
    <article class="card wide graph-card" id="cognee-map">
      <div class="card-head"><span>Cognee Knowledge Map</span><strong>Hosted graph</strong></div>
      <iframe src="/graph" title="Cognee Knowledge Map"></iframe>
    </article>
    """

    safety_panel = """
    <article class="card safety" id="safety">
      <div class="card-head"><span>Safety & Trust</span><strong>No autonomous trading</strong></div>
      <ul>
        <li>No trades executed</li>
        <li>Deterministic strategy and QQQ risk gate</li>
        <li><b>ALLOW_ORDERS=false</b></li>
        <li>Evidence-backed research</li>
        <li>Persistent memory with Cognee</li>
      </ul>
    </article>
    """

    body = hero + f"<main class='grid'>{regime_panel}{memory_panel}{ranking_panel}{evidence_panel}{graph_panel}{safety_panel}</main>"
    return _page(body)


def _page(body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fin Trading Brain Demo</title>{_style()}</head><body>{body}</body></html>"""


def _style() -> str:
    return """
<style>
:root{--bg:#08111f;--panel:#101b2d;--panel2:#13233b;--text:#ecf4ff;--muted:#93a9c8;--cyan:#38d5ff;--green:#50f2a0;--yellow:#ffd166;--red:#ff6b6b;--line:#243856;--shadow:0 24px 70px rgba(0,0,0,.35)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#17345c,transparent 35%),linear-gradient(135deg,#070d18,#0b1425 45%,#0e1c33);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,Segoe UI,Arial,sans-serif}a{color:inherit}.hero{min-height:360px;padding:56px clamp(24px,5vw,72px);display:grid;grid-template-columns:1fr 340px;gap:32px;align-items:center}.eyebrow{color:var(--cyan);text-transform:uppercase;letter-spacing:.16em;font-size:12px;font-weight:800}.hero h1{font-size:clamp(44px,7vw,86px);line-height:.92;margin:8px 0;background:linear-gradient(90deg,#fff,#8fe7ff,#77ffb3);-webkit-background-clip:text;color:transparent}.subtitle{font-size:21px;max-width:780px;color:#c8d7ee}.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:24px}.chip{border:1px solid var(--line);background:rgba(255,255,255,.06);padding:9px 12px;border-radius:999px;font-weight:700;font-size:13px}.chip .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;background:var(--green)}.chip.warn .dot{background:var(--yellow)}.chip.safe .dot{background:var(--cyan)}.hero-card,.card{background:linear-gradient(180deg,rgba(255,255,255,.08),rgba(255,255,255,.035));border:1px solid rgba(255,255,255,.12);border-radius:24px;box-shadow:var(--shadow);backdrop-filter:blur(12px)}.hero-card{padding:30px}.big-number{font-size:40px;font-weight:900;color:var(--green)}.hero-card small{color:var(--muted);overflow-wrap:anywhere}.grid{padding:0 clamp(20px,4vw,58px) 60px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}.card{padding:24px;min-height:220px}.wide{grid-column:1/-1}.card-head{display:flex;justify-content:space-between;gap:16px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em;font-size:12px;font-weight:800;margin-bottom:14px}.card-head strong{color:var(--green)}h2{font-size:30px;margin:8px 0 18px}.metric-row{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:12px 0}.muted{color:var(--muted)}table{width:100%;border-collapse:collapse;overflow:hidden;border-radius:16px}th,td{text-align:left;padding:14px 12px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-size:12px;text-transform:uppercase}tbody tr:hover{background:rgba(56,213,255,.06)}.evidence-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.evidence-card{text-decoration:none;background:rgba(8,17,31,.64);border:1px solid var(--line);border-radius:18px;padding:16px;min-height:210px;display:flex;flex-direction:column;transition:.18s}.evidence-card:hover{transform:translateY(-3px);border-color:var(--cyan)}.evidence-card .source{color:var(--cyan);font-size:12px;font-weight:800}.evidence-card h3{font-size:17px;margin:10px 0}.evidence-card p{color:#b8c8e2;font-size:13px;line-height:1.45;flex:1}.evidence-card footer{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:11px}.button{display:inline-block;margin-top:12px;padding:12px 16px;border-radius:12px;background:linear-gradient(90deg,#19c6ff,#4cf0a1);color:#04101d;text-decoration:none;font-weight:900}.graph-card iframe{width:100%;height:620px;border:0;border-radius:18px;background:#fff}.safety ul{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding-left:20px}.safety li{padding:8px;color:#d9e8ff}@media(max-width:900px){.hero{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.evidence-grid{grid-template-columns:1fr}.safety ul{grid-template-columns:1fr}.graph-card iframe{height:460px}}
</style>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, content: bytes, content_type: str = "text/html; charset=utf-8", code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._send(render_home().encode("utf-8"))
        elif path == "/api/brief":
            self._send(json.dumps(load_brief(), indent=2, default=str).encode("utf-8"), "application/json")
        elif path == "/graph":
            if COGNEE_MAP.exists():
                self._send(COGNEE_MAP.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(b"<h1>Cognee map not found</h1>", code=404)
        else:
            self._send(b"Not found", "text/plain", 404)

    def log_message(self, format, *args):
        return


def run(host: str = "127.0.0.1", port: int = 8765):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Fin Trading Brain demo: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    run(args.host, args.port)
