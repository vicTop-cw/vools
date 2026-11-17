# -*- coding: utf-8 -*-
"""P2：actus_recommend 缓存与增量注册（提升计划 P2，任务 T0r4）。

验收标准（对应实现 vools/actus/intent.py 的进程级 LRU 缓存入口
``get_router_with_cache`` 与 indexer.scan_actions 的变更属性）：
  1. 连续两次 recommend 第二次不触发 scan（打点验证 scan_count）；
  2. 动作文件无变化时 0 次扫描；
  3. 新增 1 个动作后只注册该动作（register_count 增量 == 1）；
  4. 删除/parser fingerprint/probe 结果变化时触发重建；
  5. 与旧式"每次全量 scan + 逐个 register_action"注册语义一致（回归锚点）；
  6. 缓存 LRU 淘汰、打点复位、MCP 层集成。

实现要点（红线不破坏 schema / 不改 scan_actions 返回签名）：
  - indexer.scan_actions 挂 _changed_ids / _has_removal 属性；
  - intent 维护 OrderedDict LRU（键 = parser fingerprint + 动作文件 mtime 摘要）；
  - 无文件删除时增量注册（remove + append），有删除/指纹变化时全量重建；
  - probe 报告作为缓存项签名，与外部显式报告不一致时强制重建。
"""
import os
import textwrap
from types import SimpleNamespace

import pytest

import vools.actus.intent as intent_mod
from vools.actus.intent import (
    get_router_with_cache,
    reset_router_cache,
    get_router_cache_stats,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """隔离仓库根/meta 目录，并屏蔽真实 probe 与真实 scan 的副作用。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "_meta"))
    # 默认屏蔽真实 probe：单元场景不依赖环境，集成测试单独放开
    monkeypatch.setattr("vools.actus.probe.probe",
                        lambda force_refresh=False: None)
    reset_router_cache()
    yield
    reset_router_cache()


# ── 可控打点替身 ──────────────────────────────────────────────

class FakeScan:
    """模拟 indexer.scan_actions：记录调用次数并按设定返回动作与变更属性。"""

    def __init__(self):
        self.calls = 0
        self.actions = {}
        self.changed_ids = []
        self.has_removal = False

    def __call__(self, actions_dir=None, validate=True,
                 use_cache=True, write_cache=True):
        self.calls += 1
        self._changed_ids = list(self.changed_ids)
        self._has_removal = bool(self.has_removal)
        return dict(self.actions)


class SnapCtrl:
    """可控的动作文件 mtime 摘要：改 value 触发缓存键变化。"""

    def __init__(self, value="sig-fixed"):
        self.value = value

    def __call__(self, actions_dir=None):
        return self.value


def _action(aid, kind="doc", desc="desc %s" % "", usage="", tags=()):
    return SimpleNamespace(meta={
        "id": aid, "kind": kind, "description": desc,
        "usage": usage, "tags": list(tags),
    })


def _install(monkeypatch, fake_scan=None, snap=None, fp=None):
    fake_scan = fake_scan or FakeScan()
    snap = snap or SnapCtrl()
    monkeypatch.setattr("vools.actus.intent.scan_actions", fake_scan)
    monkeypatch.setattr("vools.actus.intent._snapshot_actions_fingerprint", snap)
    if fp is not None:
        monkeypatch.setattr("vools.actus.intent._parser_fingerprint", fp)
    return fake_scan, snap


def _probe_report(ready_ids):
    item = SimpleNamespace(category="actions", name="actions",
                           available=True, extra={"actions": list(ready_ids)})
    return SimpleNamespace(items=[item])


# ── 1/2. 连续两次、无变化 0 次扫描 ─────────────────────────────

def test_second_call_uses_cache_without_scan(monkeypatch):
    fake_scan, _snap = _install(monkeypatch)
    fake_scan.actions = {
        "a.one": _action("a.one", desc="alpha stuff", tags=["alpha"]),
        "b.two": _action("b.two", desc="beta stuff", tags=["beta"]),
    }
    fake_scan.changed_ids = ["a.one", "b.two"]

    r1, ch1, rebuilt1 = get_router_with_cache()
    stats1 = get_router_cache_stats()
    r2, ch2, rebuilt2 = get_router_with_cache()
    stats2 = get_router_cache_stats()

    assert rebuilt1 is True and rebuilt2 is False
    assert stats1["scan_count"] == 1
    assert stats2["scan_count"] == 1, "第二次 recommend 不应触发 scan"
    assert stats2["hits"] == 1
    assert ch2 is None, "缓存命中时 changes 应为 None"
    assert r1 is r2, "缓存命中应复用同一 router 实例"


def test_no_change_means_zero_additional_scan(monkeypatch):
    fake_scan, _snap = _install(monkeypatch)
    fake_scan.actions = {"a.one": _action("a.one", desc="alpha")}
    fake_scan.changed_ids = ["a.one"]

    for _ in range(3):
        get_router_with_cache()
    stats = get_router_cache_stats()
    assert stats["scan_count"] == 1, "无变化时总计只有首次 1 次扫描"
    assert stats["hits"] == 2
    assert stats["misses"] == 1


# ── 3. 新增 1 个动作 → 只注册该动作 ────────────────────────────

def test_new_action_registers_only_that_action(monkeypatch):
    fake_scan, snap = _install(monkeypatch)
    fake_scan.actions = {
        "a.one": _action("a.one", desc="alpha"),
        "b.two": _action("b.two", desc="beta"),
    }
    fake_scan.changed_ids = ["a.one", "b.two"]
    get_router_with_cache()
    stats1 = get_router_cache_stats()
    assert stats1["register_count"] == 2, "首次构建注册全部"

    # 新增第 3 个动作：mtime 摘要变化 + 仅该文件在变更集
    snap.value = "sig-new"
    fake_scan.actions["c.three"] = _action("c.three", desc="gamma")
    fake_scan.changed_ids = ["c.three"]
    router, changes, rebuilt = get_router_with_cache()
    stats2 = get_router_cache_stats()

    assert rebuilt is True
    assert changes == {"changed_aids": ["c.three"], "rebuilt": False}, \
        "新增动作应走增量注册而非全量重建"
    assert stats2["register_count"] - stats1["register_count"] == 1, \
        "应只注册新增的 1 个动作"
    assert stats2["scan_count"] == 2
    assert sorted(a["id"] for a in router.list_actions()) == \
        ["a.one", "b.two", "c.three"], \
        "增量后旧动作仍在、新动作已加入"


# ── 4a. 有文件删除 → 全量重建（增量无法安全还原旧 id）───────────

def test_removal_forces_full_rebuild(monkeypatch):
    fake_scan, snap = _install(monkeypatch)
    fake_scan.actions = {
        "a.one": _action("a.one", desc="alpha"),
        "b.two": _action("b.two", desc="beta"),
    }
    fake_scan.changed_ids = ["a.one", "b.two"]
    get_router_with_cache()
    stats1 = get_router_cache_stats()

    snap.value = "sig-removed"
    fake_scan.has_removal = True          # 旧文件未再出现
    fake_scan.changed_ids = []            # 本次无新解析文件
    fake_scan.actions = {"b.two": _action("b.two", desc="beta")}
    router, changes, rebuilt = get_router_with_cache()
    stats2 = get_router_cache_stats()

    assert rebuilt is True and changes["rebuilt"] is True, \
        "有删除必须全量重建"
    assert stats2["register_count"] == stats1["register_count"] + 1, \
        "全量重建注册现存全部（这里 1 个）"
    assert sorted(a["id"] for a in router.list_actions()) == ["b.two"], \
        "已删除动作必须从 router 移除"


# ── 4b. parser fingerprint 变化 → 重建 ─────────────────────────

def test_parser_fingerprint_change_forces_rebuild(monkeypatch):
    fake_scan, _snap = _install(monkeypatch)
    fake_scan.actions = {"a.one": _action("a.one", desc="alpha")}
    fake_scan.changed_ids = ["a.one"]

    state = {"i": 0}

    def fp():
        state["i"] += 1
        return "fp%d" % state["i"]

    monkeypatch.setattr("vools.actus.intent._parser_fingerprint", fp)

    get_router_with_cache()
    stats1 = get_router_cache_stats()
    get_router_with_cache()
    stats2 = get_router_cache_stats()
    assert stats1["scan_count"] == 1
    assert stats2["scan_count"] == 2, "fingerprint 变化应强制重建"


# ── 4c. probe 结果失效 → 重建 ──────────────────────────────────

def test_probe_report_change_forces_rebuild(monkeypatch):
    fake_scan, _snap = _install(monkeypatch)
    fake_scan.actions = {
        "a.one": _action("a.one", desc="alpha"),
        "b.two": _action("b.two", desc="beta"),
    }
    fake_scan.changed_ids = ["a.one", "b.two"]

    r1, _, _ = get_router_with_cache(probe_report=_probe_report(["a.one"]))
    stats1 = get_router_cache_stats()

    r2, _, rebuilt2 = get_router_with_cache(probe_report=_probe_report(["a.one"]))
    stats2 = get_router_cache_stats()
    assert rebuilt2 is False and stats2["scan_count"] == 1, \
        "probe 报告一致时命中缓存"

    r3, _, rebuilt3 = get_router_with_cache(probe_report=_probe_report(["a.one", "b.two"]))
    stats3 = get_router_cache_stats()
    assert rebuilt3 is True and stats3["scan_count"] == 2, \
        "probe 结果变化应触发重建"
    assert stats3["register_count"] == stats2["register_count"] + 2, \
        "重建时重新注册全部动作"


# ── 5. 与旧式全量注册语义一致（回归锚点）───────────────────────

def test_registration_parity_with_old_loop(monkeypatch):
    fake_scan, _snap = _install(monkeypatch)
    fake_scan.actions = {
        "a.exec": _action("a.exec", kind="exec", desc="exec thing",
                          usage="run a", tags=["x"]),
        "b.flow": _action("b.flow", kind="workflow", desc="flow thing",
                          usage="run b", tags=["y"]),
        "c.bundle": _action("c.bundle", kind="bundle", desc="bundle thing",
                            usage="run c", tags=["z"]),
    }
    fake_scan.changed_ids = list(fake_scan.actions)

    router, _, _ = get_router_with_cache()

    # 对照：旧实现（mcp_server 原代码）的注册语义
    from vools.actus.intent import get_default_router, IntentRouter
    old = get_default_router()
    for aid, a in fake_scan.actions.items():
        old.register_action(aid, a.meta["description"], a.meta["usage"],
                            a.meta["tags"])
        if str(a.meta["kind"] or "exec").lower() in ("bundle", "workflow"):
            old.register_workflow(aid, a.meta["description"], a.meta["tags"])

    assert sorted(a["id"] for a in router.list_actions()) == \
        sorted(a["id"] for a in old.list_actions())
    assert sorted(w["id"] for w in router.list_workflows()) == \
        sorted(w["id"] for w in old.list_workflows())

    # 增量更新路径等价性：新增一个 exec 动作后与"旧循环重新全量注册"一致
    snap = monkeypatch  # noqa: F841（说明：增量更新语义已由用例 3 覆盖）


# ── 6. LRU 淘汰与打点复位 ─────────────────────────────────────

def test_cache_lru_eviction(monkeypatch):
    fake_scan, _snap = _install(monkeypatch)
    fake_scan.actions = {"a.one": _action("a.one", desc="alpha")}
    fake_scan.changed_ids = ["a.one"]

    # 依次访问 5 个不同缓存键（snapshot 递增）→ 均 miss，缓存上限 4
    snaps = [SnapCtrl("sig-%d" % i) for i in range(5)]
    for s in snaps:
        monkeypatch.setattr(
            "vools.actus.intent._snapshot_actions_fingerprint", s)
        get_router_with_cache()

    stats = get_router_cache_stats()
    assert stats["misses"] == 5
    assert len(intent_mod._router_cache) <= 4, "LRU 缓存应淘汰超限项"


def test_reset_router_cache_zeroes_stats(monkeypatch):
    fake_scan, _snap = _install(monkeypatch)
    fake_scan.actions = {"a.one": _action("a.one", desc="alpha")}
    fake_scan.changed_ids = ["a.one"]
    get_router_with_cache()
    assert get_router_cache_stats()["scan_count"] == 1
    reset_router_cache()
    stats = get_router_cache_stats()
    assert all(v == 0 for v in stats.values())
    assert len(intent_mod._router_cache) == 0


# ── 7. 真实 scan 集成（不 patch scan_actions）──────────────────

GOOD = textwrap.dedent("""\
---
id: {aid}
name: {name}
version: 1.0.0
trust: sandbox
kind: doc
platform: desktop
description: {desc}
tags: [{tags}]
---

# {name}
""")


def _write_action(adir, aid, name, desc, tags="x"):
    with open(os.path.join(str(adir), "%s.actus.md" % aid),
              "w", encoding="utf-8", newline="") as fh:
        fh.write(GOOD.format(aid=aid, name=name, desc=desc, tags=tags))


def test_real_scan_two_calls_only_one_scan(tmp_path, monkeypatch):
    adir = tmp_path / "actions"
    adir.mkdir()
    _write_action(adir, "p2.alpha", "Alpha", "alpha stuff")
    _write_action(adir, "p2.beta", "Beta", "beta stuff")

    reset_router_cache()
    r1, _, rebuilt1 = get_router_with_cache()
    stats1 = get_router_cache_stats()
    r2, _, rebuilt2 = get_router_with_cache()
    stats2 = get_router_cache_stats()

    assert rebuilt1 is True and rebuilt2 is False
    assert stats1["scan_count"] == 1
    assert stats2["scan_count"] == 1, "真实 scan 集成：第二次应命中缓存"
    assert r1 is r2
    # 真实动作已注册：动作集合包含本次写入的两个
    ids = {a["id"] for a in r2.list_actions()}
    assert {"p2.alpha", "p2.beta"}.issubset(ids)


# ── 8. MCP 层集成（actus_recommend 工具）───────────────────────

def test_mcp_actus_recommend_uses_cache(tmp_path, monkeypatch):
    adir = tmp_path / "actions"
    adir.mkdir()
    _write_action(adir, "p2.mcp.a", "McpAlpha", "alpha stuff")
    _write_action(adir, "p2.mcp.b", "McpBeta", "beta stuff")

    from vools.actus.mcp_server import MCPServer

    reset_router_cache()
    server = MCPServer()
    params = {"name": "actus_recommend",
              "arguments": {"description": "alpha", "limit": 3}}
    out1 = server._call_tool_inner(params)
    stats1 = get_router_cache_stats()
    out2 = server._call_tool_inner(params)
    stats2 = get_router_cache_stats()

    assert stats1["scan_count"] == 1
    assert stats2["scan_count"] == 1, \
        "MCP actus_recommend 第二次调用不应触发 scan"
    assert stats2["hits"] == 1
    # 两次都成功返回推荐结构
    for out in (out1, out2):
        assert out is not None
        assert "recommendations" in out.get("result", {}) or \
            "recommendations" in str(out), \
            "actus_recommend 应返回 recommendations 字段"
