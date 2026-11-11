# -*- coding: utf-8 -*-
"""actus/tests/test_analyze_actions_signals.py — analyze_actions 细粒度信号专项单测。

测什么 / 为什么
---------------
`analyze_actions()`（probe/actions.py，PROBE_PLAN §4.7）的顶层契约
（total/ready/blocked）已由 `tests/test_probe_actions.py` 的粗判定间接覆盖，
但 **细粒度信号分支此前零专项单测**（grep 全 tests/ 零命中，PROBE_PLAN §982
明言「靠 fixture 手工验证，建议补测」、CHANGELOG Unreleased「两个测试缺口
（已排期补测）」之一）：

* `verdicts` 逐动作记录：verdict / ready_scope / deps / missing_deps /
  blocked_reasons / deps_declared / deps_field / path / parse_error；
* `undeclared`：deps 键缺失（`<deps>`）与 deps=null（`<deps:null>`）双标签
  都要进信号，`deps: []`（明确声明无依赖）不算 undeclared；
* `parse_failed`：文件解析失败 → blocked + parse_failed 点名，不进 undeclared；
* `unverifiable`：npm/mcp/cs_build 报告无法判定 → blocked + reasons 点名；
* `duplicate_ids`：同 id 多份（用户项目优先于种子）；
* `index_source`：传报告 → "probe_report"，不传 → "self-probe"；
* 三档 verdict（ready/degraded/blocked）与顶层计数守恒；
* action: 依赖的不动点迭代：引用不存在动作 → missing；依赖 blocked 动作 →
  连坐 blocked；成环 → cycle。

怎么测（不依赖本机环境）
------------------------
* 动作文件全部 tmp_path 现造（YAML front-matter 形态），显式 actions_dir
  只扫该目录，不混入包内种子；
* 探测报告用计划形态 dict（{"runtimes": [...], "system_tools": [...],
  "python_packages": [...]}）构造「完全可控」的能力面；
* degraded 分支依赖 bridge 指令白名单：入口块写引擎不认识的指令
  （devtools=…）触发，复用 PROBE_PLAN 记载的 calculator 实测形态。

py3.8+ 口径（pyproject requires-python>=3.8，24ea2d53 升级）：只用标准库，% 格式化（保持文件间一致风格）。
"""

import os
import sys

import pytest

# 真实 IO / 真实执行型测试 —— 用 `pytest -m "not slow"` 跳过
pytestmark = pytest.mark.slow

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.probe.actions import (  # noqa: E402
    READY_SCOPE_DEPS_AND_ENTRY_DIRECTIVES,
    analyze_actions,
)


# ---------------------------------------------------------------------------
# 动作文件工厂（YAML front-matter 形态，deps 可控）
# ---------------------------------------------------------------------------

def _action_text(action_id, deps_lines=None, body_lang="python",
                 body_directive="", name=None):
    """造一个最小可解析动作；deps_lines 为 None 表示键缺失，
    为 [] 表示明确声明无依赖（inline `deps: []`），为 ["  - xxx"]
    行列表表示有依赖。"""
    name = name or action_id.rsplit(".", 1)[-1]
    lines = [
        "---",
        "id: %s" % action_id,
        "name: %s" % name,
        "version: 1.0.0",
        "trust: sandbox",
        "kind: exec",
        "entry: main",
    ]
    if deps_lines is not None:
        if deps_lines == []:
            lines.append("deps: []")          # inline 空列表：YAML 才解析为 []
        else:
            lines.append("deps:")
            lines.extend(deps_lines)
    lines.extend([
        "description: %s signal test" % action_id,
        "---",
        "",
        "```%s %s" % (body_lang, body_directive),
        'print("hi")',
        "```",
    ])
    return "\n".join(lines) + "\n"


def _make_dir(tmp_path, **files):
    """files: {filename: text} → 返回 actions 目录字符串。"""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for fn, text in files.items():
        (actions_dir / fn).write_text(text, encoding="utf-8")
    return str(actions_dir)


def _report(system=(), runtimes=(), packages=()):
    """计划形态探测报告：三个分类的 available 全部显式可控。"""
    return {
        "system_tools": [{"name": n, "available": True} for n in system],
        "runtimes": [{"name": n, "available": True} for n in runtimes],
        "python_packages": [{"name": n, "available": True} for n in packages],
    }


# ---------------------------------------------------------------------------
# 1. verdicts 基本结构与 ready_scope
# ---------------------------------------------------------------------------

def test_verdicts_structure_and_ready_scope(tmp_path):
    """每个 verdict 记录都带契约字段；ready_scope 恒为语义限定符。"""
    d = _make_dir(tmp_path, **{
        "a.actus.schema.md": _action_text("sig.basic", deps_lines=[]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())

    assert results["total"] == 1
    assert results["ready_scope"] == READY_SCOPE_DEPS_AND_ENTRY_DIRECTIVES
    record = results["verdicts"]["sig.basic"]
    for key in ("verdict", "ready_scope", "deps", "missing_deps",
                "blocked_reasons", "deps_declared", "deps_field",
                "path", "parse_error"):
        assert key in record, "verdicts 记录缺字段 %s" % key
    assert record["verdict"] == "ready"
    assert record["deps_declared"] is True
    assert record["deps_field"] == "list"
    assert record["parse_error"] is None


def test_top_level_counts_conserved(tmp_path):
    """顶层计数守恒：ready + degraded + blocked == total。"""
    d = _make_dir(tmp_path, **{
        "ok.actus.schema.md": _action_text("sig.ok", deps_lines=[]),
        "bad.actus.schema.md": _action_text(
            "sig.blocked", deps_lines=["  - pip:no-such-pkg-xyz"]),
        "broken.actus.schema.md": "---\nid: sig.broken\n---\n```python\n((",
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["total"] == 3
    assert results["ready"] + results["degraded"] + results["blocked"] == \
        results["total"]
    assert results["blocked"] == 2
    assert results["ready"] == 1


# ---------------------------------------------------------------------------
# 2. undeclared 三态（缺失 / null / 空列表）
# ---------------------------------------------------------------------------

def test_undeclared_missing_deps_key(tmp_path):
    """deps 键整块缺失 → ready 但进 undeclared，reasons 带 <deps> 标签。"""
    d = _make_dir(tmp_path, **{
        "u.actus.schema.md": _action_text("sig.undeclared", deps_lines=None),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["undeclared"] == ["sig.undeclared"]
    record = results["verdicts"]["sig.undeclared"]
    assert record["verdict"] == "ready"
    assert record["deps_declared"] is False
    assert record["deps_field"] == "missing"
    statuses = [(r.get("dep"), r.get("status")) for r in record["blocked_reasons"]]
    assert ("<deps>", "undeclared") in statuses


def test_undeclared_null_deps_label(tmp_path):
    """deps=null → ready 但进 undeclared，标签 <deps:null>（与键缺失可区分）。"""
    text = _action_text("sig.null", deps_lines=None).replace(
        "---\n",
        "---\n",
        1,
    )
    # 用显式 null 写法：front-matter 里 deps:（值为空 → YAML null）
    text = _action_text("sig.null", deps_lines=None).replace(
        "description:",
        "deps:\ndescription:",
        1,
    )
    d = _make_dir(tmp_path, **{"n.actus.schema.md": text})
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["undeclared"] == ["sig.null"]
    record = results["verdicts"]["sig.null"]
    assert record["verdict"] == "ready"
    assert record["deps_field"] == "null"
    statuses = [(r.get("dep"), r.get("status")) for r in record["blocked_reasons"]]
    assert ("<deps:null>", "undeclared") in statuses


def test_empty_deps_list_is_declared_no_signal(tmp_path):
    """deps: [] 是作者明确声明「无依赖」→ ready 且**不进** undeclared、无信号。"""
    d = _make_dir(tmp_path, **{
        "e.actus.schema.md": _action_text("sig.empty", deps_lines=[]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["undeclared"] == []
    record = results["verdicts"]["sig.empty"]
    assert record["verdict"] == "ready"
    assert record["blocked_reasons"] == []


def test_invalid_deps_field_type(tmp_path):
    """deps 类型错（写成字符串）→ invalid_deps_field 信号 → blocked。"""
    text = _action_text("sig.invalid", deps_lines=[]).replace(
        "deps: []",
        'deps: "not-a-list"',
        1,
    )
    assert 'deps: "not-a-list"' in text   # 守卫：replace 必须命中，否则测的是空
    d = _make_dir(tmp_path, **{"i.actus.schema.md": text})
    results = analyze_actions(actions_dir=d, probe_report=_report())
    record = results["verdicts"]["sig.invalid"]
    assert record["verdict"] == "blocked"
    statuses = [r.get("status") for r in record["blocked_reasons"]]
    assert "invalid_deps_field" in statuses


# ---------------------------------------------------------------------------
# 3. 各依赖类型判定（missing / unverifiable / ok）
# ---------------------------------------------------------------------------

def test_pip_missing_blocks(tmp_path):
    """pip: 不存在的包 → missing → blocked + missing_deps 点名。"""
    d = _make_dir(tmp_path, **{
        "p.actus.schema.md": _action_text(
            "sig.pip", deps_lines=["  - pip:no-such-pkg-xyz"]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    record = results["verdicts"]["sig.pip"]
    assert record["verdict"] == "blocked"
    assert record["missing_deps"] == ["pip:no-such-pkg-xyz"]
    statuses = [r.get("status") for r in record["blocked_reasons"]]
    assert "missing" in statuses


def test_pip_present_ready(tmp_path):
    """pip: 报告里可用的包 → ok → ready。"""
    d = _make_dir(tmp_path, **{
        "p.actus.schema.md": _action_text(
            "sig.pip.ok", deps_lines=["  - pip:requests"]),
    })
    results = analyze_actions(
        actions_dir=d, probe_report=_report(packages=["requests"]))
    record = results["verdicts"]["sig.pip.ok"]
    assert record["verdict"] == "ready"
    assert record["missing_deps"] == []


def test_npm_and_mcp_unverifiable(tmp_path):
    """npm:/mcp: 报告无法判定 → blocked + results.unverifiable 点名。"""
    d = _make_dir(tmp_path, **{
        "a.actus.schema.md": _action_text(
            "sig.npm", deps_lines=["  - npm:shiki"]),
        "b.actus.schema.md": _action_text(
            "sig.mcp", deps_lines=["  - mcp:some-server"]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["blocked"] == 2
    assert set(results["unverifiable"]) == {"sig.npm", "sig.mcp"}
    for ident, deps in results["unverifiable"].items():
        assert deps, "%s 的 unverifiable 依赖列表不应为空" % ident


def test_system_dep_ok_and_missing(tmp_path):
    """system: 命令：报告有 → ready；报告无 → blocked。"""
    d = _make_dir(tmp_path, **{
        "ok.actus.schema.md": _action_text(
            "sig.sys.ok", deps_lines=["  - system:pandoc"]),
        "bad.actus.schema.md": _action_text(
            "sig.sys.bad", deps_lines=["  - system:no-such-cmd-xyz"]),
    })
    results = analyze_actions(
        actions_dir=d, probe_report=_report(system=["pandoc"]))
    assert results["verdicts"]["sig.sys.ok"]["verdict"] == "ready"
    assert results["verdicts"]["sig.sys.bad"]["verdict"] == "blocked"


def test_runtime_dep_ok_and_missing(tmp_path):
    """runtime: 运行时：报告有 → ready；报告无 → blocked（不 unverifiable）。"""
    d = _make_dir(tmp_path, **{
        "ok.actus.schema.md": _action_text(
            "sig.rt.ok", deps_lines=["  - runtime:python"]),
        "bad.actus.schema.md": _action_text(
            "sig.rt.bad", deps_lines=["  - runtime:no-such-rt-xyz"]),
    })
    results = analyze_actions(
        actions_dir=d, probe_report=_report(runtimes=["python"]))
    assert results["verdicts"]["sig.rt.ok"]["verdict"] == "ready"
    assert results["verdicts"]["sig.rt.bad"]["verdict"] == "blocked"
    # runtime 是可判定类型，不许混进 unverifiable
    assert results["unverifiable"] == {}


# ---------------------------------------------------------------------------
# 4. action: 依赖（不动点迭代 / 缺失 / 连坐 / 成环）
# ---------------------------------------------------------------------------

def test_action_dep_missing_target(tmp_path):
    """action: 引用不存在的动作 → missing → blocked。"""
    d = _make_dir(tmp_path, **{
        "a.actus.schema.md": _action_text(
            "sig.ref", deps_lines=["  - action:no-such-target"]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    record = results["verdicts"]["sig.ref"]
    assert record["verdict"] == "blocked"
    statuses = [r.get("status") for r in record["blocked_reasons"]]
    assert "missing" in statuses


def test_action_dep_blocked_target_contaminates(tmp_path):
    """action: 依赖的动作自身 blocked → 连坐 blocked（依赖的动作未就绪）。"""
    d = _make_dir(tmp_path, **{
        "base.actus.schema.md": _action_text(
            "sig.base", deps_lines=["  - pip:no-such-pkg-xyz"]),
        "ref.actus.schema.md": _action_text(
            "sig.ref2", deps_lines=["  - action:sig.base"]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["verdicts"]["sig.base"]["verdict"] == "blocked"
    record = results["verdicts"]["sig.ref2"]
    assert record["verdict"] == "blocked"
    statuses = [r.get("status") for r in record["blocked_reasons"]]
    assert "blocked" in statuses
    assert "action:sig.base" in record["missing_deps"]


def test_action_dep_ready_chain(tmp_path):
    """action: 依赖链全部 ready → 链尾 ready（不动点迭代收敛）。"""
    d = _make_dir(tmp_path, **{
        "leaf.actus.schema.md": _action_text("sig.leaf", deps_lines=[]),
        "mid.actus.schema.md": _action_text(
            "sig.mid", deps_lines=["  - action:sig.leaf"]),
        "top.actus.schema.md": _action_text(
            "sig.top", deps_lines=["  - action:sig.mid"]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["ready"] == 3
    assert results["blocked"] == 0
    assert results["verdicts"]["sig.top"]["verdict"] == "ready"


def test_action_dep_cycle_blocked(tmp_path):
    """action: 成环（a→b→a）→ 两边 cycle blocked，不可能就绪。"""
    d = _make_dir(tmp_path, **{
        "a.actus.schema.md": _action_text(
            "sig.cyc.a", deps_lines=["  - action:sig.cyc.b"]),
        "b.actus.schema.md": _action_text(
            "sig.cyc.b", deps_lines=["  - action:sig.cyc.a"]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    for ident in ("sig.cyc.a", "sig.cyc.b"):
        record = results["verdicts"][ident]
        assert record["verdict"] == "blocked"
        statuses = [r.get("status") for r in record["blocked_reasons"]]
        assert "cycle" in statuses


# ---------------------------------------------------------------------------
# 5. parse_failed / duplicate_ids / index_source
# ---------------------------------------------------------------------------

def test_parse_failed_signal(tmp_path):
    """解析失败的动作 → blocked + parse_failed 点名，不进 undeclared。

    注意 id 语义：解析失败拿不到 front-matter 的 id，退化为相对路径 id
    （docstring 明言的正确行为）。
    """
    d = _make_dir(tmp_path, **{
        "broken.actus.schema.md": "---\nid: sig.broken\n---\n```python\n((",
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["parse_failed"] == ["broken.actus.schema.md"]
    assert results["undeclared"] == []          # 解析失败不重复计入
    record = results["verdicts"]["broken.actus.schema.md"]
    assert record["verdict"] == "blocked"
    statuses = [r.get("status") for r in record["blocked_reasons"]]
    assert "parse_error" in statuses


def test_duplicate_ids_signal(tmp_path):
    """同 id 两份 → duplicate_ids 记录 kept/ignored，只判一份。"""
    d = _make_dir(tmp_path, **{
        "first.actus.schema.md": _action_text("sig.dup", deps_lines=[]),
        "second.actus.schema.md": _action_text("sig.dup", deps_lines=[]),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    assert results["total"] == 1                 # 同 id 去重后只判一份
    dups = results["duplicate_ids"]
    assert len(dups) == 1
    assert dups[0]["id"] == "sig.dup"
    assert dups[0]["kept"] and dups[0]["ignored"]
    assert dups[0]["kept"] != dups[0]["ignored"]


def test_index_source_probe_report(tmp_path):
    """传**非空**探测报告 → index_source="probe_report"。

    空报告（三个分类全空 → 收集不到任何条目）按实现语义视为不可用报告，
    退回 self-probe —— 那是另一条路径，在 test_index_source_self_probe 覆盖。
    """
    d = _make_dir(tmp_path, **{
        "a.actus.schema.md": _action_text("sig.src", deps_lines=[]),
    })
    results = analyze_actions(
        actions_dir=d, probe_report=_report(system=["pandoc"]))
    assert results["index_source"] == "probe_report"


def test_index_source_self_probe(tmp_path):
    """不传报告 → index_source="self-probe"（兜底判定如实标注）。"""
    d = _make_dir(tmp_path, **{
        "a.actus.schema.md": _action_text("sig.src2", deps_lines=[]),
    })
    results = analyze_actions(actions_dir=d, probe_report=None)
    assert results["index_source"] == "self-probe"


# ---------------------------------------------------------------------------
# 6. degraded（deps 满足但入口块指令不被引擎支持）
# ---------------------------------------------------------------------------

def test_degraded_entry_block_directive(tmp_path):
    """入口块写引擎不认识的指令 → degraded（不进 blocked 计数）。

    注意：PROBE_PLAN 记载的 calculator 反例（devtools 指令）在 0.9.0 后
    已被 bridge 白名单收编（webview2+devtools 现在合法），degraded 触发
    需要真正未知的指令名。
    """
    d = _make_dir(tmp_path, **{
        "dev.actus.schema.md": _action_text(
            "sig.degraded", deps_lines=[],
            body_lang="python",
            body_directive="#!run tag=main zzz_totally_unknown_directive=1"),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    record = results["verdicts"]["sig.degraded"]
    assert record["verdict"] == "degraded"
    assert results["degraded"] == 1
    assert results["blocked"] == 0               # degraded 不进 blocked
    assert record.get("degraded_reasons"), "degraded 必须带可查原因"
    assert record["blocked_reasons"] == []       # degraded 不混进 blocked_reasons


def test_ready_entry_block_clean(tmp_path):
    """入口块指令全部被引擎认识 → ready（entry_block.checked=True）。"""
    d = _make_dir(tmp_path, **{
        "clean.actus.schema.md": _action_text(
            "sig.clean", deps_lines=[],
            body_lang="python", body_directive="#!run tag=main"),
    })
    results = analyze_actions(actions_dir=d, probe_report=_report())
    record = results["verdicts"]["sig.clean"]
    assert record["verdict"] == "ready"
    info = record.get("entry_block") or {}
    assert info.get("checked") is True
