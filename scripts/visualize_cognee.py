from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from agent.memory.cognee_client import CogneeClient

DEFAULT_QUERY = "environment production structured memory semiconductor research AMAT NVDA AMD AVGO MU QQQ SMA50 regime evidence source"
OUT_DIR = ROOT / "results" / "cognee"


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or node.get("name") or node.get("label") or "")


def _node_label(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("name") or node.get("type") or _node_id(node))[:120]


def _edge_label(edge: dict[str, Any]) -> str:
    return str(edge.get("relation") or edge.get("label") or edge.get("relationship_type") or edge.get("edge_class") or "related_to")[:80]


def graph_counts(graph: dict[str, Any]) -> tuple[int, int]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    links = graph.get("links") if isinstance(graph.get("links"), list) else []
    return len(nodes), len(links)


def filter_obvious_test_junk(graph: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Best-effort production map cleanup when hosted Cognee cannot metadata-filter.

    This only removes nodes returned by Cognee that carry explicit test markers
    such as M7_TEST. It does not invent or rewrite graph content.
    """
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    links = graph.get("links") if isinstance(graph.get("links"), list) else []
    kept = []
    removed_ids = set()
    for n in nodes:
        marker_text = json.dumps(n, default=str).lower() if isinstance(n, dict) else str(n).lower()
        if "m7_test" in marker_text or "environment=test" in marker_text:
            if isinstance(n, dict) and n.get("id") is not None:
                removed_ids.add(str(n.get("id")))
            continue
        kept.append(n)
    kept_ids = {str(n.get("id")) for n in kept if isinstance(n, dict) and n.get("id") is not None}
    kept_links = [e for e in links if isinstance(e, dict) and str(e.get("source")) in kept_ids and str(e.get("target")) in kept_ids]
    out = dict(graph)
    out["nodes"] = kept
    out["links"] = kept_links
    out["filtered_test_nodes"] = len(nodes) - len(kept)
    return out, len(nodes) - len(kept)


def safe_graph_export(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    links = graph.get("links") if isinstance(graph.get("links"), list) else []
    return {
        "source": "hosted_cognee",
        "dataset": graph.get("dataset"),
        "dataset_id": graph.get("dataset_id"),
        "query": graph.get("query"),
        "node_count": len(nodes),
        "edge_count": len(links),
        "filtered_test_nodes": graph.get("filtered_test_nodes", 0),
        "nodes": nodes,
        "links": links,
    }


def local_html_from_graph(graph: dict[str, Any]) -> str:
    """Render only Cognee-returned nodes/links; do not invent graph content."""
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    links = [e for e in graph.get("links", []) if isinstance(e, dict)]
    vis_nodes = [{"id": _node_id(n), "label": _node_label(n), "type": str(n.get("type") or n.get("stage") or "node"), "title": json.dumps(n, default=str)[:2000]} for n in nodes if _node_id(n)]
    ids = {n["id"] for n in vis_nodes}
    vis_links = [{"source": str(e.get("source")), "target": str(e.get("target")), "label": _edge_label(e), "title": json.dumps(e, default=str)[:1000]} for e in links if str(e.get("source")) in ids and str(e.get("target")) in ids]
    payload = json.dumps({"nodes": vis_nodes, "links": vis_links}, default=str)
    title = html.escape(f"Fin Trading Brain Cognee Map — {graph.get('dataset') or ''}")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>{title}</title>
<style>
body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background:#0b1020; color:#e8eefc; }}
#bar {{ padding:12px 16px; background:#121a33; border-bottom:1px solid #26365f; }}
#graph {{ width:100vw; height:calc(100vh - 58px); }}
.node circle {{ stroke:#fff; stroke-width:1.2px; cursor:grab; }}
.node text {{ fill:#e8eefc; font-size:11px; pointer-events:none; text-shadow:0 1px 2px #000; }}
.link {{ stroke:#7183b5; stroke-opacity:.65; }}
.link-label {{ fill:#aebdec; font-size:9px; pointer-events:none; }}
</style>
</head>
<body>
<div id=\"bar\"><strong>Fin Trading Brain Cognee Knowledge Map</strong> — hosted Cognee data, nodes: {len(vis_nodes)}, edges: {len(vis_links)}</div>
<svg id=\"graph\"></svg>
<script src=\"https://d3js.org/d3.v7.min.js\"></script>
<script>
const data = {payload};
const svg = d3.select('#graph'), width = window.innerWidth, height = window.innerHeight - 58;
const g = svg.append('g');
svg.call(d3.zoom().scaleExtent([0.1, 8]).on('zoom', (event) => g.attr('transform', event.transform)));
const color = d3.scaleOrdinal(d3.schemeTableau10);
const sim = d3.forceSimulation(data.nodes)
  .force('link', d3.forceLink(data.links).id(d => d.id).distance(95))
  .force('charge', d3.forceManyBody().strength(-260))
  .force('center', d3.forceCenter(width/2, height/2));
const link = g.append('g').selectAll('line').data(data.links).enter().append('line').attr('class','link').attr('stroke-width',1.4);
link.append('title').text(d => d.title || d.label);
const linkText = g.append('g').selectAll('text').data(data.links).enter().append('text').attr('class','link-label').text(d => d.label);
const node = g.append('g').selectAll('g').data(data.nodes).enter().append('g').attr('class','node').call(d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended));
node.append('circle').attr('r', 8).attr('fill', d => color(d.type));
node.append('title').text(d => d.title);
node.append('text').attr('x', 11).attr('y', 4).text(d => d.label);
sim.on('tick', () => {{
  link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  linkText.attr('x', d => (d.source.x + d.target.x)/2).attr('y', d => (d.source.y + d.target.y)/2);
  node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
}});
function dragstarted(event,d) {{ if (!event.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; }}
function dragged(event,d) {{ d.fx=event.x; d.fy=event.y; }}
function dragended(event,d) {{ if (!event.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }}
</script>
</body>
</html>"""


def build_visualization(query: str | None, max_nodes: int, depth: int, out_dir: Path = OUT_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    client = CogneeClient()
    graph = client.visualize_graph_json(query=query, max_nodes=max_nodes, depth=depth)
    graph, filtered_test_nodes = filter_obvious_test_junk(graph)
    nodes, edges = graph_counts(graph)
    json_path = out_dir / "fin_trading_brain_graph.json"
    html_path = out_dir / "fin_trading_brain_map.html"
    json_path.write_text(json.dumps(safe_graph_export(graph), indent=2, default=str), encoding="utf-8")

    native = client.visualize_graph_html(query=query, max_nodes=max_nodes, depth=depth)
    mode = "native_cognee_html"
    if filtered_test_nodes:
        mode = "local_html_from_cognee_graph_data_filtered"
        html_path.write_text(local_html_from_graph(graph), encoding="utf-8")
    elif native.get("available") and native.get("html"):
        html_path.write_text(native["html"], encoding="utf-8")
    else:
        mode = "local_html_from_cognee_graph_data"
        html_path.write_text(local_html_from_graph(graph), encoding="utf-8")

    return {
        "status": "PASS" if graph.get("available") and nodes > 0 else "DEGRADED",
        "source": "hosted_cognee",
        "dataset": graph.get("dataset"),
        "query": query,
        "nodes": nodes,
        "edges": edges,
        "html_path": str(html_path),
        "json_path": str(json_path),
        "mode": mode,
        "filtered_test_nodes": filtered_test_nodes,
        "reason": graph.get("reason") or native.get("reason"),
    }


def main() -> int:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(description="Create a Cognee knowledge map for Fin Trading Brain memories.")
    p.add_argument("--query", default=DEFAULT_QUERY)
    p.add_argument("--max-nodes", type=int, default=300)
    p.add_argument("--depth", type=int, default=2)
    args = p.parse_args()
    result = build_visualization(args.query, args.max_nodes, args.depth)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] in {"PASS", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
