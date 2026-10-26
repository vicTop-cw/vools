# -*- coding: utf-8 -*-
"""viz.py 的工作流解析与格式选择（扫第二档发现）。

缺陷：
  1. `parse_workflow_nodes({'nodes': 'abc'})` → 字符串被逐字符迭代后裸抛
     AttributeError；`nodes=[None]` 同样裸抛
  2. **无 id 的节点生成 `[""]`** —— mermaid/dot 里出现空节点名的坏图
  3. **`visualize_workflow(format_='zzz')` 静默回退成 ascii** ——
     要 mermaid 却拿到 ASCII 图，毫无提示（与 export_history 同坑）
  4. `to_dot(label=123)` 在 `.replace` 处裸抛 AttributeError
  5. 依赖字段别名不一致：`DAGScheduler` 认 `depends`/`deps`，
     `viz` 只认 `depends`/`dependencies` → 同一份定义画出不同的边
"""
import pytest

from vools.actus import viz

GOOD = {"nodes": [{"id": "a", "action": "x"},
                  {"id": "b", "action": "y", "depends": ["a"]}]}


# --------------------------------------------------------------------------
# 解析校验
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, "abc", 123, []])
def test_parse_rejects_non_dict(bad):
    with pytest.raises(TypeError) as exc:
        viz.parse_workflow_nodes(bad)
    assert "必须是 dict" in str(exc.value), exc.value


def test_parse_rejects_string_nodes():
    """字符串会被逐字符迭代。"""
    with pytest.raises(TypeError) as exc:
        viz.parse_workflow_nodes({"nodes": "abc"})
    assert "必须是列表" in str(exc.value), exc.value


@pytest.mark.parametrize("bad", [[None], [123], ["str"]])
def test_parse_rejects_non_dict_node(bad):
    with pytest.raises(TypeError) as exc:
        viz.parse_workflow_nodes({"nodes": bad})
    assert "必须是 dict" in str(exc.value), exc.value


@pytest.mark.parametrize("node", [{}, {"id": ""}, {"id": "   "}, {"label": "x"}])
def test_parse_rejects_node_without_id(node):
    """无 id 会生成空节点名的坏图。"""
    with pytest.raises(ValueError) as exc:
        viz.parse_workflow_nodes({"nodes": [node]})
    assert "缺少有效 id" in str(exc.value), exc.value


def test_parse_valid_and_edges():
    nodes, edges = viz.parse_workflow_nodes(GOOD)
    assert len(nodes) == 2
    assert edges == [("a", "b")]


def test_parse_deps_alias():
    """`deps` 与 `dependencies` 都应与 DAGScheduler 一致地产生边。"""
    for key in ("depends", "deps", "dependencies"):
        nodes, edges = viz.parse_workflow_nodes(
            {"nodes": [{"id": "a"}, {"id": "b", key: ["a"]}]})
        assert edges == [("a", "b")], "字段 %s 未产生边: %r" % (key, edges)


def test_parse_explicit_edges():
    nodes, edges = viz.parse_workflow_nodes(
        {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [["a", "b"]]})
    assert ("a", "b") in edges


def test_empty_workflow_ok():
    assert viz.parse_workflow_nodes({}) == ([], [])


# --------------------------------------------------------------------------
# 格式选择
# --------------------------------------------------------------------------
def test_unknown_format_rejected():
    """此前静默回退成 ascii。"""
    with pytest.raises(ValueError) as exc:
        viz.visualize_workflow(GOOD, format_="zzz")
    assert "未知可视化格式" in str(exc.value), exc.value


@pytest.mark.parametrize("fmt", ["ascii", "mermaid", "dot", "html"])
def test_known_formats_render(fmt):
    out = viz.visualize_workflow(GOOD, format_=fmt)
    assert isinstance(out, str) and out


def test_mermaid_has_no_empty_node():
    """修前无 id 节点会渲染成空名节点；现在解析期就拒绝。"""
    out = viz.visualize_workflow(GOOD, format_="mermaid")
    assert '[""]' not in out, out
