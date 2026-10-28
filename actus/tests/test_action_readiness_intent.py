# -*- coding: utf-8 -*-
"""actus/tests/test_action_readiness_intent.py — IntentRouter 依赖级 ready 门禁验收测试。

测什么 / 为什么
---------------
`IntentRouter._is_ready()` 原本只有一道门：**动作出现在探测报告里 = ready**
（PROBE_PLAN.md §9 Phase 3）。这道门看不见动作声明的依赖 —— 一个动作即使要求
`system:definitely-not-a-tool-xyz`，只要它被扫描到就照样可推荐。

本轮把这层接上（PROBE_PLAN.md §4.7 的 `analyze_actions` 产出）：
报告里的 `action_readiness` 条目带 `extra["verdicts"]`，IntentRouter 现在会再读
一层 ——「明确判 blocked 的动作同样不可推荐」。本文件证明：

1. **升级确实有效**：同一份报告，去掉 `action_readiness` 条目 → 动作 ready
   （升级前行为）；带上它且该动作判 blocked → 动作不可推荐（升级后行为）。
   这就是「升级前 ready / 升级后 blocked」的前后对比证据。
2. **向后兼容**：报告没有该条目（旧缓存/旧报告）→ 行为与升级前逐字一致；
   条目 `available=False`（分析失败）或 `verdicts` 结构异常 → **不启用门禁**，
   绝不因为分析失败把所有动作误杀。
3. **两道门都要过**：`_ready_ids`（在报告里）仍是第一道门，verdicts 只能
   **进一步收紧**，不能把报告里没有的动作放出来。
4. 端到端：真跑一次 `probe()`，用「动作在报告里、但 deps 缺工具」的真实场景，
   对比「保留 action_readiness」与「剔除它」两种报告 → 前者 blocked、后者 ready。

怎么做到不依赖仓库真实动作
--------------------------
动作全部 `tmp_path` 现造，扫描根用产品自带覆盖点 `ACTUS_REPO_ROOT`；探测缓存
重定向到 tmp（不写工作区 `_meta/probe_cache.json`）。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import json
import os
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.intent import IntentRouter  # noqa: E402
from vools.actus.probe import cache as cache_mod  # noqa: E402
from vools.actus.probe import probe  # noqa: E402
from vools.actus.probe.base import ProbeItem  # noqa: E402
from vools.actus.probe.report import ProbeReport  # noqa: E402


# ---------------------------------------------------------------------------
# 造报告：一份「扫描到了动作」的报告，可选带 action_readiness 条目
# ---------------------------------------------------------------------------

def _report(action_ids, verdicts=None, readiness_available=True,
            include_readiness=True, readiness_extra=None):
    """构造探测报告。

    action_ids: 出现在 actions 条目里的动作 id（= 升级前的 ready 集合）
    verdicts:   {action_id: {"verdict": ...}}，写进 action_readiness 条目
    """
    items = [
        ProbeItem(
            name="actions",
            category="actions",
            available=True,
            extra={
                "actions_dir": "/stub/actions",
                "action_count": len(action_ids),
                "actions": [{"id": aid, "path": "/stub/%s.actus.md" % aid}
                            for aid in action_ids],
            },
        ),
        ProbeItem(name="action_dependencies", category="actions", available=True,
                  extra={}),
    ]
    if include_readiness:
        extra = {"total": len(verdicts or {}),
                 "ready": 0, "blocked": 0,
                 "verdicts": verdicts or {},
                 "index_source": "probe_report"}
        if readiness_extra:
            extra.update(readiness_extra)
        items.append(ProbeItem(
            name="action_readiness",
            category="actions",
            available=readiness_available,
            extra=extra,
        ))
    return ProbeReport(items=items)


def _router(action_ids, report, keywords=None):
    router = IntentRouter()
    for aid in action_ids:
        router.register_action(aid, "%s action" % aid, tags=[aid.split(".")[-1]])
    if keywords:
        router.set_keyword_map(keywords)
    router.set_probe_report(report)
    return router


def _ready_listed(router):
    return sorted(a["id"] for a in router.list_actions())


# ---------------------------------------------------------------------------
# 1) 核心证据：升级前 ready → 升级后 blocked（同一份报告，只差一条 readiness）
# ---------------------------------------------------------------------------

def test_upgrade_turns_ready_into_blocked_for_action_with_missing_deps():
    """动作在报告里、但 deps 缺工具：升级前 ready，升级后 blocked。

    这是本轮升级的**前后对比证据**：
      * 旧报告（无 action_readiness 条目）→ 旧行为 ready；
      * 新报告（带 verdicts，该动作判 blocked）→ 不可推荐。
    """
    action_ids = ["t.needs_tool", "t.plain"]
    blocked_verdicts = {
        "t.needs_tool": {
            "verdict": "blocked",
            "deps": ["system:definitely-not-a-tool-xyz"],
            "missing_deps": ["system:definitely-not-a-tool-xyz"],
            "blocked_reasons": [{"dep": "system:definitely-not-a-tool-xyz",
                                 "status": "missing",
                                 "reason": "系统工具未被探测到（不在 PATH / 未安装）"}],
            "deps_declared": True,
        },
        "t.plain": {"verdict": "ready", "deps": [], "missing_deps": [],
                    "blocked_reasons": [], "deps_declared": True},
    }

    # ── 升级前：报告里没有 action_readiness ──
    old_report = _report(action_ids, include_readiness=False)
    old_router = _router(action_ids, old_report)
    before = _ready_listed(old_router)
    assert before == ["t.needs_tool", "t.plain"], \
        "升级前语义应是「在报告里 = ready」，实得 %r" % (before,)

    # ── 升级后：带上 verdicts ──
    new_report = _report(action_ids, blocked_verdicts)
    new_router = _router(action_ids, new_report)
    after = _ready_listed(new_router)
    assert after == ["t.plain"], "依赖不满足的动作必须被挡掉，实得 %r" % (after,)
    assert "t.needs_tool" in before and "t.needs_tool" not in after, \
        "前后对比不成立：before=%r after=%r" % (before, after)


def test_blocked_action_cannot_be_routed_by_keyword_or_tag():
    """blocked 的动作既不能被关键词命中，也不能被标签匹配推荐。"""
    action_ids = ["t.ok", "t.broken"]
    verdicts = {
        "t.ok": {"verdict": "ready"},
        "t.broken": {"verdict": "blocked"},
    }
    router = _router(action_ids, _report(action_ids, verdicts),
                     keywords={"执行": "t.broken"})

    hit = router.route("执行")
    assert hit["action_id"] != "t.broken", \
        "关键词命中了 blocked 动作: %r" % (hit,)
    # 标签路径同样不能推荐它
    assert router.route("broken")["action_id"] != "t.broken", \
        "标签匹配推荐了 blocked 动作"


# ---------------------------------------------------------------------------
# 2) 向后兼容：报告里没有 readiness 信息时，行为逐字保持升级前
# ---------------------------------------------------------------------------

def test_backward_compat_without_readiness_item():
    """旧报告（无 action_readiness）：在报告里的动作一律 ready。"""
    action_ids = ["t.a", "t.b"]
    router = _router(action_ids, _report(action_ids, include_readiness=False))
    assert _ready_listed(router) == ["t.a", "t.b"]
    assert router._blocked_ids is None


def test_readiness_unavailable_does_not_block_anything():
    """action_readiness 条目 available=False（分析失败）→ 不启用门禁，不误杀。

    否则「动作依赖分析自己炸了」会被下游解读成「所有动作都 blocked」——
    与 actions 条目 unavailable 时不准误杀全部动作是同一条纪律。
    """
    action_ids = ["t.a"]
    report = _report(action_ids, {"t.a": {"verdict": "blocked"}},
                     readiness_available=False)
    router = _router(action_ids, report)
    assert _ready_listed(router) == ["t.a"], "分析不可用时不许把动作误判 blocked"
    assert router._blocked_ids is None


def test_malformed_verdicts_are_ignored_not_fatal():
    """verdicts 结构异常（不是 dict / 记录不是 dict）→ 忽略，不崩也不误杀。"""
    action_ids = ["t.a", "t.b"]

    # verdicts 不是 dict
    r1 = _router(action_ids, _report(action_ids, readiness_extra={"verdicts": "oops"}))
    assert _ready_listed(r1) == ["t.a", "t.b"]

    # 记录本身是字符串（而不是 {"verdict": ...}）
    r2 = _router(action_ids, _report(action_ids, {"t.a": "blocked", "t.b": "ready"}))
    assert _ready_listed(r2) == ["t.a", "t.b"], "非 dict 记录不应被当成 blocked"

    # 空 verdicts
    r3 = _router(action_ids, _report(action_ids, {}))
    assert _ready_listed(r3) == ["t.a", "t.b"]


def test_only_explicit_blocked_verdict_blocks():
    """只认显式 blocked：ready / 未知状态 / 缺 verdict 键一律放行。"""
    action_ids = ["t.ready", "t.weird", "t.nokey"]
    verdicts = {
        "t.ready": {"verdict": "ready"},
        "t.weird": {"verdict": "pending"},     # 未知状态：不拦
        "t.nokey": {"deps": []},               # 缺 verdict 键：不拦
    }
    router = _router(action_ids, _report(action_ids, verdicts))
    assert _ready_listed(router) == ["t.nokey", "t.ready", "t.weird"]


# ---------------------------------------------------------------------------
# 3) 两道门：verdicts 只能收紧，不能把报告外的动作放出来
# ---------------------------------------------------------------------------

def test_verdict_gate_cannot_release_action_absent_from_report():
    """动作不在 actions 条目里（报告没扫到）但 verdicts 说 ready → 仍 blocked。"""
    report = _report(["t.listed"], {"t.absent": {"verdict": "ready"}})
    router = _router(["t.listed", "t.absent"], report)
    assert _ready_listed(router) == ["t.listed"], \
        "verdicts 不许绕过「动作必须在报告里」这道主门"


def test_manual_set_ready_ids_clears_verdict_gate():
    """手工 set_ready_ids 是显式覆盖：同时清掉报告派生的依赖级门禁。

    否则一份过期报告里的 blocked 判定会偷偷盖掉调用方的显式选择。
    """
    action_ids = ["t.a"]
    router = _router(action_ids, _report(action_ids, {"t.a": {"verdict": "blocked"}}))
    assert _ready_listed(router) == []
    router.set_ready_ids(["t.a"])
    assert _ready_listed(router) == ["t.a"]
    assert router._blocked_ids is None


# ---------------------------------------------------------------------------
# 4) 端到端：真跑 probe()，"动作在报告里但 deps 缺工具"
# ---------------------------------------------------------------------------

def _action_text(action_id, deps_line=""):
    """新规范格式的动作文件（YAML front-matter），deps_line 直接插进元数据。"""
    return (
        "---\n"
        "id: %(id)s\n"
        "name: %(id)s\n"
        "version: 1.0.0\n"
        "trust: sandbox\n"
        "kind: exec\n"
        "purpose: [compute]\n"
        "industry: [general]\n"
        "trigger: [manual]\n"
        "entry: main\n"
        "description: %(id)s action\n"
        "author: vools\n"
        "platform: desktop\n"
        "%(deps)s"
        "---\n"
        "\n# %(id)s\n\n```python\nprint(1)\n```\n"
    ) % {"id": action_id, "deps": deps_line}


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """临时仓库根 + actions/ 目录，并把探测缓存重定向到 tmp。"""
    root = tmp_path / "repo"
    actions = root / "actions"
    actions.mkdir(parents=True)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(root))
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))
    return actions


@pytest.mark.timeout(180)
def test_end_to_end_probe_blocks_action_with_missing_dep(fake_repo):
    """真 probe → 报告 → IntentRouter：缺依赖的动作被挡，无依赖的动作放行。

    同时给出**同一份真实报告**的前后对比：剔除 action_readiness 条目后
    （= 升级前语义）两个动作都 ready；保留时只有无依赖的那个 ready。
    """
    missing = "system:definitely-not-a-tool-xyz"
    (fake_repo / "needs.actus.schema.md").write_text(
        _action_text("t.e2e.needs", "deps:\n  - %s\n" % missing), encoding="utf-8")
    (fake_repo / "plain.actus.schema.md").write_text(
        _action_text("t.e2e.plain", "deps: []\n"), encoding="utf-8")

    report = probe(force_refresh=True)

    acts = [i for i in report.items if i.category == "actions"]
    listed = [i for i in acts if i.name == "actions"][0]
    assert listed.available is True
    scanned_ids = set(entry["id"] for entry in listed.extra["actions"])
    assert {"t.e2e.needs", "t.e2e.plain"} <= scanned_ids

    readiness = [i for i in acts if i.name == "action_readiness"][0]
    assert readiness.available is True
    verdicts = readiness.extra["verdicts"]
    assert verdicts["t.e2e.needs"]["verdict"] == "blocked", \
        "缺依赖的动作应判 blocked: %r" % (verdicts["t.e2e.needs"],)
    assert missing in verdicts["t.e2e.needs"]["missing_deps"]
    assert verdicts["t.e2e.plain"]["verdict"] == "ready"

    action_ids = ["t.e2e.needs", "t.e2e.plain"]

    # ── 升级后：保留 readiness → 只有 plain 可推荐 ──
    router = _router(action_ids, report)
    assert _ready_listed(router) == ["t.e2e.plain"], \
        "实际 ready=%r" % (_ready_listed(router),)

    # ── 升级前：剔除 readiness 条目（模拟旧报告）→ 两个都 ready ──
    legacy_items = [i for i in report.items if i.name != "action_readiness"]
    legacy_router = _router(action_ids, ProbeReport(items=legacy_items))
    assert _ready_listed(legacy_router) == ["t.e2e.needs", "t.e2e.plain"], \
        "升级前语义应两个都 ready，实得 %r" % (_ready_listed(legacy_router),)

    # 报告仍可 JSON 序列化（落缓存 / 给 LLM 消费两条下游都依赖）
    json.dumps(report.to_dict(), ensure_ascii=False)