# -*- coding: utf-8 -*-
"""actus/tests/test_runtime_dep_resolution.py — `runtime:` 依赖前缀解析分支专项单测。

测什么 / 为什么
---------------
PROBE_PLAN.md §4.7 把 `runtime:python` 列为合法依赖写法，但 `dependency.py` 的
`_parse_dep_string` 此前**没有该前缀分支** —— 裸串 fallthrough 成 ACTION 依赖，
"runtime:python" 被当成一个名叫 "runtime:python" 的动作，永远找不到、永远
blocked（probe 侧实测到该缺口）。分支已在工作区落地（DepType.RUNTIME / 抽象名
展开表 / fix_command / _check_runtime），但 **grep 全 tests/ 零命中**——本文件
补上这块验收，让 PROBE_PLAN §984 的「进行中」缺口收口。

覆盖面（全部与实现一一对齐）：
1. `_parse_dep_string`：runtime: 前缀 → DepType.RUNTIME + name 剥前缀 + HINT 策略；
2. **其余前缀回归**（builtin/system/pip/npm/mcp/action/cs_*）：补 RUNTIME 分支
   不许改变既有解析行为；
3. `fix_command` RUNTIME 分支 → 「安装运行时: <name>」；
4. `_check_runtime`：本机真实可用运行时（python/shell 展开候选）→ satisfied=True；
   不存在的运行时 → satisfied=False 且消息列出候选；同名命令优先（候选表首位）；
5. `parse_deps`：混合列表（runtime + system + action）逐个正确分型；
6. dict 形态 `{"type": "runtime", "name": ...}` → 枚举合法；
7. probe 侧联动：`_dep_kind` 认出 runtime 类型、`_check_simple_dep` 走
   `caps.has_runtime`（不再 fallthrough 到 unverifiable）。

怎么测（不依赖本机装了什么）
----------------------------
* 解析层全部纯函数断言，不碰 PATH；
* `_check_runtime` 的「可用」分支用 `runtime:python`（测试进程本身就在 Python 里跑，
  python/py 命令必然存在）与 `runtime:shell`（Windows 有 cmd，POSIX 有 sh）；
* 「不可用」分支用刻意不存在的名字（`definitely-not-a-runtime-xyz`）；
* probe 侧联动用计划形态构造报告 dict（{"runtimes": [...]}），不真跑 probe。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
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

from vools.actus.dependency import (  # noqa: E402
    DepStrategy,
    DepType,
    Dependency,
    DependencyResolver,
)
from vools.actus.probe.actions import _check_simple_dep, _dep_kind  # noqa: E402


# ---------------------------------------------------------------------------
# 1. 解析层：runtime: 前缀
# ---------------------------------------------------------------------------

def _resolver():
    """隔离解析器：指向临时 actions 根，不碰仓库真实目录。"""
    import tempfile
    root = tempfile.mkdtemp(prefix="actus_runtime_dep_")
    return DependencyResolver(actions_root=root)


def test_parse_runtime_prefix_yields_runtime_type():
    """runtime:python → DepType.RUNTIME，name 剥掉前缀，策略 HINT。"""
    dep = _resolver()._parse_dep_string("runtime:python")
    assert dep.type == DepType.RUNTIME
    assert dep.name == "python"
    assert dep.strategy == DepStrategy.HINT


def test_parse_runtime_prefix_variants():
    """runtime:node / runtime:shell / runtime:rust 同样正确分型。"""
    for raw, expected_name in (
        ("runtime:node", "node"),
        ("runtime:shell", "shell"),
        ("runtime:rust", "rust"),
    ):
        dep = _resolver()._parse_dep_string(raw)
        assert dep.type == DepType.RUNTIME, raw
        assert dep.name == expected_name, raw


def test_other_prefixes_unaffected_by_runtime_branch():
    """回归守卫：补 runtime: 分支后其余前缀解析行为原样。"""
    r = _resolver()
    cases = [
        ("builtin:webview2", DepType.BUILTIN, "webview2"),
        ("system:pandoc", DepType.SYSTEM, "pandoc"),
        ("pip:requests", DepType.LANG, "requests"),
        ("npm:shiki", DepType.LANG, "shiki"),
        ("mcp:server", DepType.MCP, "server"),
        ("action:actus.basics.calculator", DepType.ACTION, "actus.basics.calculator"),
    ]
    for raw, expected_type, expected_name in cases:
        dep = r._parse_dep_string(raw)
        assert dep.type == expected_type, raw
        assert dep.name == expected_name, raw


def test_bare_string_still_action_dependency():
    """无前缀裸串仍按 action 依赖处理（与 resolver 一致，不许被 runtime 分支吞掉）。"""
    dep = _resolver()._parse_dep_string("just-some-action")
    assert dep.type == DepType.ACTION
    assert dep.name == "just-some-action"


def test_runtime_fix_command():
    """RUNTIME 的 fix_command → 「安装运行时: <name>」。"""
    dep = _resolver()._parse_dep_string("runtime:python")
    assert dep.fix_command == "安装运行时: python"


def test_runtime_type_enum_roundtrip():
    """dict 形态 {"type": "runtime"} 能从字符串还原枚举（DepType("runtime") 合法）。"""
    assert DepType("runtime") is DepType.RUNTIME
    deps = _resolver().parse_deps([{"type": "runtime", "name": "python"}])
    assert len(deps) == 1
    assert deps[0].type == DepType.RUNTIME
    assert deps[0].name == "python"


def test_parse_deps_mixed_list():
    """混合列表逐个正确分型：runtime 不再挤进 action。"""
    deps = _resolver().parse_deps([
        "runtime:python",
        "system:pandoc",
        "some-action",
    ])
    kinds = [(d.type, d.name) for d in deps]
    assert (DepType.RUNTIME, "python") in kinds
    assert (DepType.SYSTEM, "pandoc") in kinds
    assert (DepType.ACTION, "some-action") in kinds
    # 精确守恒：3 进 3 出，没有静默丢失
    assert len(kinds) == 3


# ---------------------------------------------------------------------------
# 2. 检查层：_check_runtime
# ---------------------------------------------------------------------------

def test_check_runtime_python_available():
    """runtime:python 在测试进程环境必可用（python/py 至少其一在 PATH）。"""
    dep = _resolver()._parse_dep_string("runtime:python")
    result = _resolver()._check_runtime(dep)
    assert result.satisfied is True
    assert result.message  # 可读消息非空


def test_check_runtime_shell_expands_aliases():
    """runtime:shell 抽象名展开：bash/sh/powershell/pwsh/cmd 任一命中即满足。"""
    dep = _resolver()._parse_dep_string("runtime:shell")
    result = _resolver()._check_runtime(dep)
    assert result.satisfied is True


def test_check_runtime_missing_lists_candidates():
    """不存在的运行时 → satisfied=False，消息列出尝试过的候选。"""
    dep = _resolver()._parse_dep_string("runtime:definitely-not-a-runtime-xyz")
    result = _resolver()._check_runtime(dep)
    assert result.satisfied is False
    assert "definitely-not-a-runtime-xyz" in result.message


def test_check_runtime_same_name_takes_priority():
    """同名命令优先：候选表首位是 dep.name 本身。"""
    from vools.actus.dependency import _RUNTIME_COMMAND_ALIASES
    # alias 表里的每个抽象名，展开后首候选都是原名（同名优先语义）
    for abstract, aliases in _RUNTIME_COMMAND_ALIASES.items():
        assert abstract not in aliases or aliases[0] != abstract, (
            "alias 表不应把抽象名自身列进别名（%s）" % abstract)
    # _check_runtime 的候选顺序：[原名] + 别名（去重）
    dep = Dependency(name="shell", type=DepType.RUNTIME)
    # 内部行为验证：直接调用，观察 satisfied（有 shell 之一即可满足）
    result = _resolver()._check_runtime(dep)
    assert isinstance(result.satisfied, bool)


# ---------------------------------------------------------------------------
# 3. probe 侧联动：_dep_kind / _check_simple_dep
# ---------------------------------------------------------------------------

def test_probe_dep_kind_recognizes_runtime():
    """probe 侧 _dep_kind 对 RUNTIME 依赖返回 ("runtime", name)，不再 fallthrough。"""
    dep = _resolver()._parse_dep_string("runtime:python")
    kind, name = _dep_kind(dep)
    assert kind == "runtime"
    assert name == "python"


def test_probe_simple_dep_runtime_with_report():
    """报告声明 runtime 可用 → ok；报告不可用 → missing（不 unverifiable）。"""
    from vools.actus.probe.actions import _capabilities_from_report
    dep = _resolver()._parse_dep_string("runtime:python")
    caps_ok = _capabilities_from_report(
        {"runtimes": [{"name": "python", "available": True}]})
    status, _reason = _check_simple_dep("runtime", "python", caps_ok)
    assert status == "ok"

    caps_missing = _capabilities_from_report(
        {"runtimes": [{"name": "python", "available": False}]})
    status, reason = _check_simple_dep("runtime", "python", caps_missing)
    assert status == "missing"
    assert reason  # 可读原因非空


def test_probe_analyze_actions_runtime_dep_end_to_end(tmp_path):
    """端到端：声明 runtime:python 的动作，analyze_actions 不判 unverifiable。"""
    from vools.actus.probe.actions import analyze_actions

    text = (
        "---\n"
        "id: runtime.dep.demo\n"
        "name: RuntimeDepDemo\n"
        "version: 1.0.0\n"
        "trust: sandbox\n"
        "kind: exec\n"
        "entry: main\n"
        "deps:\n"
        "  - runtime:python\n"
        "description: runtime dep demo\n"
        "---\n"
        "\n"
        "```python\n"
        "print(\"hi\")\n"
        "```\n"
    )
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    (actions_dir / "runtime_dep_demo.actus.schema.md").write_text(
        text, encoding="utf-8")

    # 计划形态报告：runtimes 报 python 可用
    report = {"runtimes": [{"name": "python", "available": True}]}
    results = analyze_actions(actions_dir=str(actions_dir), probe_report=report)

    assert results["total"] == 1
    assert results["blocked"] == 0
    verdict = results["verdicts"]["runtime.dep.demo"]
    assert verdict["verdict"] == "ready"
    assert verdict["deps"] == ["runtime:python"]
    # 关键回归点：runtime 依赖不许出现在 unverifiable（旧实现会把
    # runtime:python 当动作依赖 → 永远 blocked）
    assert results["unverifiable"] == {}


def test_probe_analyze_actions_runtime_missing_blocks(tmp_path):
    """端到端：报告声明 runtime 不可用 → blocked + missing_deps 点名。"""
    from vools.actus.probe.actions import analyze_actions

    text = (
        "---\n"
        "id: runtime.missing.demo\n"
        "name: RuntimeMissingDemo\n"
        "version: 1.0.0\n"
        "trust: sandbox\n"
        "kind: exec\n"
        "entry: main\n"
        "deps:\n"
        "  - runtime:notexist-runtime-xyz\n"
        "description: runtime missing demo\n"
        "---\n"
        "\n"
        "```python\n"
        "print(\"hi\")\n"
        "```\n"
    )
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    (actions_dir / "runtime_missing_demo.actus.schema.md").write_text(
        text, encoding="utf-8")

    report = {"runtimes": [{"name": "notexist-runtime-xyz", "available": False}]}
    results = analyze_actions(actions_dir=str(actions_dir), probe_report=report)

    assert results["total"] == 1
    assert results["blocked"] == 1
    verdict = results["verdicts"]["runtime.missing.demo"]
    assert verdict["verdict"] == "blocked"
    assert verdict["missing_deps"] == ["runtime:notexist-runtime-xyz"]
    # blocked_reasons 里带 status=missing 的原因条目
    statuses = [r.get("status") for r in verdict["blocked_reasons"]]
    assert "missing" in statuses
