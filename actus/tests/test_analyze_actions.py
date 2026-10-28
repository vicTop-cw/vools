# -*- coding: utf-8 -*-
"""actus/tests/test_analyze_actions.py — `analyze_actions()` 九类信号的逐条固化测试。

测什么 / 为什么
---------------
`probe/actions.py::analyze_actions()` 是 PROBE_PLAN.md §4.7 的落地：逐动作读 `deps`
字段，与探测到的能力比对，产出 ready / blocked / missing_deps。实施时它长出了
**9 类显式信号**，每一类都对应一种「绝不能静默当 ready」的失败形态：

    blocked（依赖探测不到）   undeclared（没声明 deps）      parse_failed（文件解析失败）
    unverifiable（报告无法判定）duplicate_ids（同 id 多份）   cycle（依赖成环）
    invalid_deps_field（deps 不是列表）  invalid_dep_entry（列表里有非 str/dict 元素）
    missing（action: 引用的动作不存在）

这些信号此前只有实施者手工跑 fixture 验过，`grep -rn "blocked_reasons|undeclared|
unverifiable|duplicate_ids" actus/tests/` 只在别的文件里作为 fixture 数据出现、
没有断言 —— 也就是说**语义没有回归保护**：哪天某个分支被改坏（比如把 unverifiable
静默放行、或把 undeclared 当满足），现有一套测试不会红。

本文件把九类信号逐条钉住，另外钉两条纪律：
* **探测报告是权威**：报告说某个工具不可用，就不能偷偷回退到本地自查（哪怕本机
  其实装了它）；
* **输入形态**：`ProbeReport` / `to_dict()` / 计划 §4.7 的分类 dict / 条目列表 /
  `None`（本地原语兜底）都要能工作，并如实标注 `index_source`。

怎么测（不依赖仓库里的真实动作）
--------------------------------
* 动作全部 `tmp_path` 现造（JSON `#!cfg` 形态 + 故意写坏的文件），绝大多数用例用
  `analyze_actions(actions_dir=<tmp>)` 显式指定单根，扫描结果只含本用例造的动作；
* 只有 `duplicate_ids` 用例需要「用户目录 + 包内种子」两个根（产品里重复 id 只可能
  在这两者之间发生）：它**动态**从包内种子取一个 id 造同名副本，种子目录不存在/
  为空时 skip，不硬编码任何真实动作 id；
* 不跑 `probe()`，全部是纯内存 + tmp 文件，整份套件秒级。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import json
import os
import shutil
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.indexer import _seed_actions_dir  # noqa: E402
from vools.actus.probe.actions import (  # noqa: E402
    _scan_actions_dir,
    analyze_actions,
)
from vools.actus.probe.base import ProbeItem  # noqa: E402
from vools.actus.probe.report import ProbeReport  # noqa: E402


# ---------------------------------------------------------------------------
# 造数据
# ---------------------------------------------------------------------------

_NO_DEPS = object()          # 哨兵：deps 键**整块不出现**（= undeclared）


def _action_text(action_id, deps=_NO_DEPS, name=None):
    """造一个最小可解析的动作文件正文（JSON `#!cfg` 形态）。

    deps 传 `_NO_DEPS` 时整块不写（测 undeclared）；传其它值原样写进 meta
    （因此可以塞非法形态，如字符串或 [123, ...]）。
    """
    meta = {
        "id": action_id,
        "name": name or action_id,
        "version": "1.0.0",
        "entry": "main",
    }
    if deps is not _NO_DEPS:
        meta["deps"] = deps
    return (
        "---\n"
        "AIGC:\n"
        '    Label: "1"\n'
        "---\n"
        "\n"
        "# %s\n"
        "\n"
        "```json #!cfg\n"
        "%s\n"
        "```\n"
        "\n"
        "```python #!run tag=main\n"
        "def main():\n"
        '    return {"status": "ok"}\n'
        "```\n"
    ) % (meta["name"], json.dumps(meta, ensure_ascii=False))


def _write(directory, filename, text):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(text, encoding="utf-8")
    return path


def _report(*items):
    return ProbeReport(items=list(items))


def _available(name, category="system_tools"):
    return ProbeItem(name=name, category=category, available=True, path="/stub/" + name)


def _unavailable(name, category="system_tools"):
    return ProbeItem(name=name, category=category, available=False, error="not found")


def _statuses(record):
    """verdict 里 blocked_reasons 的 (status, dep) 列表（便于断言）。"""
    return [(reason.get("status"), reason.get("dep"))
            for reason in record.get("blocked_reasons", [])]


def _verdict(result, action_id):
    assert action_id in result["verdicts"], (
        "结果里没有 %r 的判定（实得 %s）" % (action_id, sorted(result["verdicts"])))
    return result["verdicts"][action_id]


@pytest.fixture
def actions_dir(tmp_path):
    """空动作目录（用例往里写假动作）。"""
    directory = tmp_path / "actions"
    directory.mkdir()
    return directory


# ---------------------------------------------------------------------------
# 1) blocked：声明的依赖探测不到
# ---------------------------------------------------------------------------

def test_blocked_when_declared_dep_missing(actions_dir):
    """依赖 `system:<tool>` 不在报告里 → blocked，missing_deps / blocked_reasons 都点名。"""
    _write(actions_dir, "blocked.actus.md",
           _action_text("test.blocked", ["system:definitely-not-a-tool-xyz"]))
    result = analyze_actions(str(actions_dir), _report())     # 报告里什么都没有

    record = _verdict(result, "test.blocked")
    assert record["verdict"] == "blocked"
    assert record["missing_deps"] == ["system:definitely-not-a-tool-xyz"]
    assert _statuses(record) == [("missing", "system:definitely-not-a-tool-xyz")]
    assert "未被探测到" in record["blocked_reasons"][0]["reason"]

    # §4.7 契约字段同步
    assert result["total"] == 1
    assert result["ready"] == 0 and result["blocked"] == 1
    assert result["missing_deps"] == {
        "test.blocked": ["system:definitely-not-a-tool-xyz"]}
    assert result["index_source"] == "probe_report"
    assert isinstance(result["elapsed_ms"], (int, float))


def test_ready_when_declared_deps_satisfied(actions_dir):
    """依赖在报告里确认可用 → ready，且不带任何 blocked_reason。"""
    _write(actions_dir, "ok.actus.md",
           _action_text("test.ok", ["system:python"]))
    result = analyze_actions(str(actions_dir), _report(_available("python")))

    record = _verdict(result, "test.ok")
    assert record["verdict"] == "ready"
    assert record["missing_deps"] == []
    assert record["blocked_reasons"] == []
    assert record["deps"] == ["system:python"]
    assert result["ready"] == 1 and result["blocked"] == 0


# ---------------------------------------------------------------------------
# 2) undeclared：没声明 deps
# ---------------------------------------------------------------------------

def test_undeclared_deps_is_ready_but_explicitly_flagged(actions_dir):
    """没写 deps：判 ready（没有未满足的依赖），但必须**明确标注未做核实**。"""
    _write(actions_dir, "undeclared.actus.md", _action_text("test.undeclared"))
    result = analyze_actions(str(actions_dir), _report())

    record = _verdict(result, "test.undeclared")
    assert record["verdict"] == "ready"
    assert record["deps_declared"] is False
    assert result["undeclared"] == ["test.undeclared"]

    statuses = _statuses(record)
    assert ("undeclared", "<deps>") in statuses
    reason = record["blocked_reasons"][0]["reason"]
    assert "核实" in reason, "undeclared 的原因必须说明「未做核实」，实得 %r" % reason


# ---------------------------------------------------------------------------
# 3) invalid_deps_field：deps 不是列表
# ---------------------------------------------------------------------------

def test_invalid_deps_field_blocks_with_signal(actions_dir):
    """`deps: "not-a-list"` → blocked，并留下 invalid_deps_field 信号。"""
    _write(actions_dir, "badfield.actus.md",
           _action_text("test.badfield", "not-a-list"))
    result = analyze_actions(str(actions_dir), _report())

    record = _verdict(result, "test.badfield")
    assert record["verdict"] == "blocked"
    assert record["blocked_reasons"][0]["status"] == "invalid_deps_field"
    assert "必须是列表" in record["blocked_reasons"][0]["reason"]
    assert record["deps"] == []


# ---------------------------------------------------------------------------
# 4) invalid_dep_entry：列表里有非 str/dict 元素
# ---------------------------------------------------------------------------

def test_invalid_dep_entry_blocks_even_when_other_deps_satisfied(actions_dir):
    """`deps: [123, "system:python"]` → blocked；即使 python 可用也不放行。

    resolver 本身对非 str/dict 元素是**静默跳过**的，实现必须先把它们筛出来留痕，
    否则 `deps: [123]` 会被当成「没有依赖」而误判 ready。
    """
    _write(actions_dir, "badentry.actus.md",
           _action_text("test.badentry", [123, "system:python"]))
    result = analyze_actions(str(actions_dir), _report(_available("python")))

    record = _verdict(result, "test.badentry")
    assert record["verdict"] == "blocked"
    signals = _statuses(record)
    assert ("invalid_dep_entry", "123") in signals, "非法元素必须点名: %r" % (signals,)
    # 合法那一项照常解析（不被非法元素带偏），且它本身是满足的
    assert record["deps"] == ["system:python"]
    assert record["missing_deps"] == [], \
        "python 已可用，非法元素才是唯一的 blocked 原因"


# ---------------------------------------------------------------------------
# 5) parse_failed：动作文件解析失败
# ---------------------------------------------------------------------------

def test_parse_failed_action_is_blocked_and_listed(actions_dir):
    """坏 YAML 动作文件 → blocked + `parse_failed` 点名（不能静默丢弃/当成 ready）。"""
    _write(actions_dir, "ok.actus.md", _action_text("test.ok", []))
    _write(actions_dir, "broken.actus.schema.md",
           "---\nid: [unclosed\nname: broken\n---\n\n# broken\n")
    result = analyze_actions(str(actions_dir), _report())

    assert result["parse_failed"] == ["broken.actus.schema.md"], \
        "解析失败的动作必须在 parse_failed 里点名，实得 %r" % (result["parse_failed"],)
    record = _verdict(result, "broken.actus.schema.md")
    assert record["verdict"] == "blocked"
    assert record["parse_error"], "verdict 必须带 parse_error 原文"
    assert record["blocked_reasons"][0]["status"] == "parse_error"
    # 解析失败的动作不重复计入 undeclared
    assert "broken.actus.schema.md" not in result["undeclared"]
    assert result["ready"] == 1 and result["blocked"] == 1


# ---------------------------------------------------------------------------
# 6) cycle：action 依赖成环
# ---------------------------------------------------------------------------

def test_action_dependency_cycle_blocks_both_sides(actions_dir):
    """A→B、B→A：两个都不可能就绪 → 都 blocked，并留下 cycle 信号。"""
    _write(actions_dir, "a.actus.md", _action_text("test.cyc_a", ["action:test.cyc_b"]))
    _write(actions_dir, "b.actus.md", _action_text("test.cyc_b", ["action:test.cyc_a"]))
    result = analyze_actions(str(actions_dir), _report())

    for ident, dep in (("test.cyc_a", "action:test.cyc_b"),
                       ("test.cyc_b", "action:test.cyc_a")):
        record = _verdict(result, ident)
        assert record["verdict"] == "blocked", "%s 在环上必须 blocked" % ident
        assert ("cycle", "<cycle>") in _statuses(record)
        assert dep in record["missing_deps"]
    assert result["ready"] == 0 and result["blocked"] == 2


# ---------------------------------------------------------------------------
# 7) missing：action: 引用的动作不存在
# ---------------------------------------------------------------------------

def test_missing_action_reference_blocks(actions_dir):
    """`action:no.such.action` 不在本次扫描里 → blocked，missing 信号点名该引用。"""
    _write(actions_dir, "missing.actus.md",
           _action_text("test.missing", ["action:no.such.action"]))
    result = analyze_actions(str(actions_dir), _report())

    record = _verdict(result, "test.missing")
    assert record["verdict"] == "blocked"
    assert ("missing", "action:no.such.action") in _statuses(record)
    assert "不存在" in record["blocked_reasons"][0]["reason"]
    assert record["missing_deps"] == ["action:no.such.action"]


# ---------------------------------------------------------------------------
# 8) unverifiable：报告无法判定的依赖类型（npm / mcp / cs_build）
# ---------------------------------------------------------------------------

def test_unverifiable_dep_kinds_block_and_are_named(actions_dir):
    """`npm:` / `mcp:` 探不出来 → blocked（不放行），并在 unverifiable 里点名原因。"""
    _write(actions_dir, "unver.actus.md",
           _action_text("test.unver", ["npm:left-pad", "mcp:some-server"]))
    result = analyze_actions(str(actions_dir), _report())

    record = _verdict(result, "test.unver")
    assert record["verdict"] == "blocked", "无法判定的依赖必须 blocked，不能静默放行"
    assert result["unverifiable"] == {
        "test.unver": ["npm:left-pad", "mcp:some-server"]}
    statuses = _statuses(record)
    assert ("unverifiable", "npm:left-pad") in statuses
    assert ("unverifiable", "mcp:some-server") in statuses
    assert set(result["missing_deps"]["test.unver"]) == {
        "npm:left-pad", "mcp:some-server"}
    # 两类依赖的原因说明必须不同（npm 缺包探测 / mcp 缺 server 探测）
    reasons = {reason["dep"]: reason["reason"]
               for reason in record["blocked_reasons"]}
    assert "npm" in reasons["npm:left-pad"]
    assert "MCP" in reasons["mcp:some-server"]


# ---------------------------------------------------------------------------
# 9) duplicate_ids：同 id 多份，用户目录优先
# ---------------------------------------------------------------------------

def test_duplicate_ids_keep_user_dir_over_seed(tmp_path, monkeypatch):
    """用户项目动作与包内种子同 id → duplicate_ids 记录，且**用户目录那份胜出**。

    产品里重复 id 只可能发生在「用户项目 actions/」与「包内种子 actions/」之间，
    所以这里动态从种子目录取一个 id 造同名副本；种子不可用时 skip，不硬编码真实 id。
    """
    seed_dir = _seed_actions_dir()
    if not os.path.isdir(seed_dir):
        pytest.skip("包内种子动作目录不存在（源码树异常形态），无法构造重复 id 场景")
    seed_ids = [entry["id"] for entry in _scan_actions_dir(seed_dir)["actions"]]
    if not seed_ids:
        pytest.skip("包内种子动作目录为空，无法构造重复 id 场景")
    duplicated_id = seed_ids[0]

    user_root = tmp_path / "repo"
    user_actions = user_root / "actions"
    user_file = _write(user_actions, "dup.actus.md", _action_text(duplicated_id, []))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(user_root))

    result = analyze_actions()        # 默认多根：用户目录在前，包内种子在后

    assert result["roots"], "默认扫描根不应为空"
    assert len(result["roots"]) >= 2, \
        "默认应为「用户目录 + 包内种子」两个根，实得 %r" % (result["roots"],)
    duplicates = result["duplicate_ids"]
    assert any(entry["id"] == duplicated_id for entry in duplicates), \
        "同名动作必须被记录到 duplicate_ids: %r" % (duplicates,)
    entry = [e for e in duplicates if e["id"] == duplicated_id][0]
    assert os.path.normcase(entry["kept"]) == os.path.normcase(str(user_file)), \
        "用户目录必须优先（kept 应是用户那份）"
    assert os.path.normcase(entry["ignored"]) != os.path.normcase(str(user_file))
    # 判定用胜出的那份：verdict 的 path 指向用户文件
    record = _verdict(result, duplicated_id)
    assert os.path.normcase(record["path"]) == os.path.normcase(str(user_file))


# ---------------------------------------------------------------------------
# 10) 探测报告权威：报告说不可用 → 不得回退本地自查
# ---------------------------------------------------------------------------

def test_probe_report_is_authoritative_over_local_self_check(actions_dir):
    """报告说 `git` 不可用（本机其实装了 git）→ 动作必须 blocked，不许偷偷自查。

    这是「报告 vs 自查」的判据：如果把 report 结果丢掉回退 `shutil.which`，
    同一个动作就会在本机判 ready、在目标机判 blocked，判定随执行环境漂移。
    """
    if not shutil.which("git"):
        pytest.skip("本机没有 git，无法构造「报告说不可用但本机有」的对照场景")

    _write(actions_dir, "auth.actus.md", _action_text("test.auth", ["system:git"]))
    blocked = analyze_actions(str(actions_dir), _report(_unavailable("git")))
    record = _verdict(blocked, "test.auth")
    assert blocked["index_source"] == "probe_report"
    assert record["verdict"] == "blocked", \
        "报告说 git 不可用时不得回退到本机自查（本机 which('git') 为真）"
    assert record["missing_deps"] == ["system:git"]

    # 同一份动作、同一台机器：报告说可用 → ready（证明判据确实是报告）
    ready = analyze_actions(str(actions_dir), _report(_available("git")))
    assert _verdict(ready, "test.auth")["verdict"] == "ready"


# ---------------------------------------------------------------------------
# 11) 输入形态：ProbeReport / to_dict() / 计划分类 dict / 条目列表 / None
# ---------------------------------------------------------------------------

def test_probe_report_input_forms_are_all_accepted(actions_dir):
    """四种报告形态结果一致；`None` 走本地原语兜底并如实标注 index_source。"""
    dep = "system:definitely-not-a-tool-xyz"
    _write(actions_dir, "x.actus.md", _action_text("test.forms", [dep]))

    report = _report(_unavailable("definitely-not-a-tool-xyz"))
    forms = [
        ("ProbeReport", report),
        ("to_dict", report.to_dict()),
        ("plan-dict", {"system_tools": [
            {"name": "definitely-not-a-tool-xyz", "available": False}]}),
        ("item-list", list(report.items)),
    ]
    for label, payload in forms:
        result = analyze_actions(str(actions_dir), payload)
        record = _verdict(result, "test.forms")
        assert result["index_source"] == "probe_report", label
        assert record["verdict"] == "blocked", label
        assert record["missing_deps"] == [dep], label

    # 不给报告：本地原语兜底（不存在的工具照样判 blocked），来源如实标注
    fallback = analyze_actions(str(actions_dir))
    assert fallback["index_source"] == "self-probe"
    record = _verdict(fallback, "test.forms")
    assert record["verdict"] == "blocked"
    assert record["missing_deps"] == [dep]


# ---------------------------------------------------------------------------
# 12) 空目录 / 目录不存在
# ---------------------------------------------------------------------------

def test_empty_and_missing_actions_dir(actions_dir, tmp_path):
    """空目录 exists=True 且计数全 0；目录不存在 exists=False —— 都不抛异常。"""
    empty = analyze_actions(str(actions_dir), _report())
    assert empty["exists"] is True
    assert empty["total"] == 0 and empty["ready"] == 0 and empty["blocked"] == 0
    assert empty["verdicts"] == {}

    missing = analyze_actions(str(tmp_path / "no_such_dir"), _report())
    assert missing["exists"] is False
    assert missing["total"] == 0
