# -*- coding: utf-8 -*-
"""workflow DAG 的结构校验（第 23 轮）。

缺陷：`DAGScheduler._build_graph` 用 `if dep in self.nodes` **静默跳过**不存在的
依赖，于是 `b depends: [ghost]` 的边被丢掉，`b` 与 `a` 落在同一层**并发执行**
——本该串行的顺序被破坏。静默错误比硬报错危险，已改为 fail loud
（新错误码 `dag_missing_dep`）。

环检测本来就是对的（`dag_cycle`），本组一并锁住。
"""
import pytest

from vools.actus.workflow import DAGScheduler


def _sched(nodes):
    return DAGScheduler(nodes)


# --------------------------------------------------------------------------
# 正常 DAG
# --------------------------------------------------------------------------
def test_linear_dag_layers():
    s = _sched([
        {"id": "a", "action": "x"},
        {"id": "b", "action": "x", "depends": ["a"]},
    ])
    assert s.topological_sort() == [["a"], ["b"]]


def test_parallel_dag_layers():
    s = _sched([
        {"id": "a", "action": "x"},
        {"id": "b", "action": "x"},
        {"id": "c", "action": "x", "depends": ["a", "b"]},
    ])
    layers = s.topological_sort()
    assert sorted(layers[0]) == ["a", "b"]
    assert layers[1] == ["c"]


def test_deps_alias_field():
    """`deps` 与 `depends` 两种字段名都要认。"""
    s = _sched([
        {"id": "a", "action": "x"},
        {"id": "b", "action": "x", "deps": ["a"]},
    ])
    assert s.topological_sort() == [["a"], ["b"]]


def test_empty_dag():
    assert _sched([]).topological_sort() == []


# --------------------------------------------------------------------------
# 环
# --------------------------------------------------------------------------
def test_two_node_cycle_detected():
    s = _sched([
        {"id": "a", "action": "x", "depends": ["b"]},
        {"id": "b", "action": "x", "depends": ["a"]},
    ])
    with pytest.raises(Exception) as exc:
        s.topological_sort()
    assert getattr(exc.value, "code", "") == "dag_cycle", exc.value


def test_self_cycle_detected():
    s = _sched([{"id": "a", "action": "x", "depends": ["a"]}])
    with pytest.raises(Exception) as exc:
        s.topological_sort()
    assert getattr(exc.value, "code", "") == "dag_cycle", exc.value


# --------------------------------------------------------------------------
# 缺失依赖（本轮缺陷回归）
# --------------------------------------------------------------------------
def test_missing_dependency_raises():
    """依赖不存在的节点必须报 dag_missing_dep，不能静默丢边。"""
    with pytest.raises(Exception) as exc:
        _sched([
            {"id": "a", "action": "x"},
            {"id": "b", "action": "x", "depends": ["ghost"]},
        ])
    assert getattr(exc.value, "code", "") == "dag_missing_dep", exc.value
    details = getattr(exc.value, "details", None) or {}
    assert details.get("unknown") == {"b": ["ghost"]}, details


def test_missing_dependency_does_not_silently_parallelize():
    """核心断言：修前 b 会与 a 同层并发；修后必须报错而不是返回错误的分层。"""
    nodes = [
        {"id": "a", "action": "x"},
        {"id": "b", "action": "x", "depends": ["ghost"]},
    ]
    try:
        layers = _sched(nodes).topological_sort()
    except Exception as exc:
        assert getattr(exc, "code", "") == "dag_missing_dep"
    else:
        pytest.fail("缺失依赖被静默接受，分层=%r（b 与 a 会并发）" % (layers,))
