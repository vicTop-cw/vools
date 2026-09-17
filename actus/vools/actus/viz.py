"""viz.py — 工作流 DAG 可视化 (Phase M4)。

生成工作流图的可视化表示：
- ASCII 文本图（终端查看）
- Mermaid 格式（Markdown 嵌入）
- DOT 格式（Graphviz 渲染）
- HTML 交互式（D3.js）
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_workflow_nodes(workflow_def: dict) -> Tuple[List[dict], List[tuple]]:
    """解析工作流定义为节点和边。

    参数:
        workflow_def: 工作流定义字典（含 nodes/edges）。

    返回:
        (nodes, edges) — nodes 为节点列表，edges 为 (from, to) 元组列表。
    """
    nodes = workflow_def.get("nodes", [])
    edges = []

    # 从节点依赖构建边
    node_map = {n.get("id", n.get("name", "")): n for n in nodes}
    for node in nodes:
        node_id = node.get("id", node.get("name", ""))
        deps = node.get("depends", node.get("dependencies", []))
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            if dep in node_map:
                edges.append((dep, node_id))

    # 也支持显式 edges
    for edge in workflow_def.get("edges", []):
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            edges.append((edge[0], edge[1]))
        elif isinstance(edge, dict):
            edges.append((edge.get("from", edge.get("source", "")),
                          edge.get("to", edge.get("target", ""))))

    return nodes, edges


def to_ascii(nodes: List[dict], edges: List[tuple]) -> str:
    """生成 ASCII 文本图。

    简单的层级布局，展示节点和依赖关系。
    """
    if not nodes:
        return "(空工作流)"

    # 计算入度
    in_degree = {n.get("id", n.get("name", "")): 0 for n in nodes}
    for src, dst in edges:
        if dst in in_degree:
            in_degree[dst] = in_degree.get(dst, 0) + 1

    # 分层（BFS）
    layers = []
    visited = set()
    current = [n for n in in_degree if in_degree[n] == 0]

    while current:
        layers.append(current)
        visited.update(current)
        next_layer = []
        for src in current:
            for s, d in edges:
                if s == src and d not in visited:
                    if all(dep in visited for dep, dst in edges if dst == d):
                        if d not in next_layer:
                            next_layer.append(d)
        current = next_layer

    # 添加孤立节点
    all_ids = {n.get("id", n.get("name", "")) for n in nodes}
    remaining = all_ids - visited
    if remaining:
        layers.append(list(remaining))

    # 渲染
    lines = []
    node_labels = {}
    for n in nodes:
        nid = n.get("id", n.get("name", ""))
        label = n.get("label", n.get("action_id", n.get("name", nid)))
        node_labels[nid] = label[:20]

    for i, layer in enumerate(layers):
        if len(layer) == 1:
            nid = layer[0]
            prefix = "  ┌─" if i > 0 else "┌─"
            suffix = "─┐" if i < len(layers) - 1 else "─┐"
            label = node_labels.get(nid, nid)
            lines.append(f"{prefix}[{nid}] {label}{suffix}")
        else:
            for nid in layer:
                label = node_labels.get(nid, nid)
                lines.append(f"  ├─[{nid}] {label}")

        if i < len(layers) - 1:
            lines.append("  │")

    return "\n".join(lines)


def to_mermaid(nodes: List[dict], edges: List[tuple]) -> str:
    """生成 Mermaid 流程图格式。

    可直接嵌入 Markdown 渲染。
    """
    lines = ["graph TD"]

    # 节点定义
    node_ids = set()
    for n in nodes:
        nid = n.get("id", n.get("name", ""))
        label = n.get("label", n.get("action_id", n.get("name", nid)))
        safe_label = label.replace('"', "'")
        lines.append(f'    {nid}["{safe_label}"]')
        node_ids.add(nid)

    # 边
    for src, dst in edges:
        if src in node_ids and dst in node_ids:
            lines.append(f"    {src} --> {dst}")

    return "\n".join(lines)


def to_dot(nodes: List[dict], edges: List[tuple]) -> str:
    """生成 Graphviz DOT 格式。

    可用 `dot -Tpng workflow.dot -o workflow.png` 渲染为图片。
    """
    lines = ["digraph workflow {"]
    lines.append('    rankdir=TB;')
    lines.append('    node [shape=box, style="rounded,filled", fillcolor="#16213e", fontcolor="#eee"];')
    lines.append('    edge [color="#e94560"];')

    # 节点
    for n in nodes:
        nid = n.get("id", n.get("name", ""))
        label = n.get("label", n.get("action_id", n.get("name", nid)))
        safe_label = label.replace('"', '\\"')
        color = "#0f3460"
        if n.get("type") == "trigger":
            color = "#e94560"
        elif n.get("type") == "condition":
            color = "#f5a623"
        lines.append(f'    {nid} [label="{safe_label}", fillcolor="{color}"];')

    # 边
    for src, dst in edges:
        lines.append(f"    {src} -> {dst};")

    lines.append("}")
    return "\n".join(lines)


def to_html(nodes: List[dict], edges: List[tuple],
            title: str = "Actus Workflow") -> str:
    """生成 HTML + D3.js 交互式可视化。

    浏览器中打开即可查看可缩放/拖拽的工作流图。
    """
    # 准备数据
    node_data = []
    for n in nodes:
        nid = n.get("id", n.get("name", ""))
        label = n.get("label", n.get("action_id", n.get("name", nid)))
        node_data.append({"id": nid, "label": label})

    edge_data = [{"source": s, "target": d} for s, d in edges]

    nodes_json = json.dumps(node_data, ensure_ascii=False)
    edges_json = json.dumps(edge_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
body {{ margin: 0; background: #1a1a2e; font-family: 'Segoe UI', sans-serif; }}
#graph {{ width: 100vw; height: 100vh; }}
.node rect {{ rx: 8; ry: 8; cursor: move; }}
.node text {{ fill: #eee; font-size: 12px; pointer-events: none; }}
.link {{ fill: none; stroke: #e94560; stroke-width: 2; }}
</style>
</head>
<body>
<svg id="graph"></svg>
<script>
const nodes = {nodes_json};
const links = {edges_json};

const svg = d3.select("#graph");
const width = window.innerWidth;
const height = window.innerHeight;

svg.attr("viewBox", [0, 0, width, height]);

const g = svg.append("g");

const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(120))
    .force("charge", d3.forceManyBody().strength(-300))
    .force("center", d3.forceCenter(width / 2, height / 2));

const link = g.append("g")
    .selectAll("line")
    .data(links)
    .join("line")
    .attr("class", "link");

const node = g.append("g")
    .selectAll("g")
    .data(nodes)
    .join("g")
    .attr("class", "node")
    .call(d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended));

node.append("rect")
    .attr("width", 120)
    .attr("height", 40)
    .attr("x", -60)
    .attr("y", -20)
    .attr("fill", "#16213e")
    .attr("stroke", "#0f3460")
    .attr("stroke-width", 2);

node.append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .text(d => d.label);

simulation.on("tick", () => {{
    link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});

function dragstarted(event, d) {{
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x; d.fy = d.y;
}}
function dragged(event, d) {{
    d.fx = event.x; d.fy = event.y;
}}
function dragended(event, d) {{
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null; d.fy = null;
}}
</script>
</body>
</html>"""


def visualize_workflow(workflow_def: dict, format_: str = "ascii") -> str:
    """可视化工作流。

    参数:
        workflow_def: 工作流定义。
        format_: 输出格式 (ascii/mermaid/dot/html)。

    返回:
        可视化字符串。
    """
    nodes, edges = parse_workflow_nodes(workflow_def)

    renderers = {
        "ascii": to_ascii,
        "mermaid": to_mermaid,
        "dot": to_dot,
        "html": to_html,
    }

    renderer = renderers.get(format_, to_ascii)
    return renderer(nodes, edges)


def visualize_action_workflow(action_meta: dict, format_: str = "ascii") -> str:
    """从动作元数据中的 workflow 字段可视化。

    参数:
        action_meta: 动作的 meta 字典。
        format_: 输出格式。

    返回:
        可视化字符串。
    """
    wf = action_meta.get("workflow", {})
    if not wf:
        return "(无工作流定义)"
    return visualize_workflow(wf, format_)


__all__ = [
    'logger',
    'parse_workflow_nodes',
    'to_ascii',
    'to_dot',
    'to_html',
    'to_mermaid',
    'visualize_action_workflow',
    'visualize_workflow'
]
