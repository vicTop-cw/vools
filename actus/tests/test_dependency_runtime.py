# -*- coding: utf-8 -*-
"""actus/tests/test_dependency_runtime.py — `dependency.py` 的 `runtime:` 依赖前缀验收测试。

测什么 / 为什么
---------------
PROBE_PLAN.md §4.7 把 `runtime:python` 列为合法依赖写法，但 `DependencyResolver`
此前没有这个前缀：裸字符串会 fallthrough 成 **action 依赖**，于是 `runtime:python`
被当成一个名叫 "runtime:python" 的动作 —— 永远找不到、永远判 blocked（probe 侧
实测到该缺口）。补齐后：

* `parse_deps` 把 `runtime:<name>` 解析成 `DepType.RUNTIME`，`name` 去掉前缀；
* `check_dep` 走 `_check_runtime`：判据是 PATH 里有没有对应可执行文件，并支持
  **抽象名展开**（`runtime:shell` → bash/sh/powershell/pwsh/cmd；`runtime:rust` →
  rustc/cargo；同名命令优先）；
* 旧前缀（system/pip/npm/mcp/action/builtin/cs_*）与裸字符串（默认 action）行为不变。

为什么需要这份测试：`grep -rn "runtime:" actus/tests/` 此前**零命中** —— 这条新语法
没有任何回归保护，谁把 `_parse_dep_string` 的分支顺序挪一下（`runtime:` 写在
`s` 开头的 system 之后、却又误落 action 分支），测试不会红。

测试策略（不依赖本机装了什么）
------------------------------
* 解析/枚举类断言用 `get_resolver()`（真源单例）；
* 展开行为用**打桩的 `shutil.which`** + **新建 `DependencyResolver()` 实例**：
  打桩让「命中哪个候选命令」确定可复现；新建实例是为了绕开 `check_dep` 按
  `dep.name` 的缓存（单例上缓存了打桩结果会污染后续用例）；
* 「本机确定没有的运行时」用一个不存在的名字，不靠机器快照。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import os
import shutil
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus.dependency as dependency_mod  # noqa: E402
from vools.actus.dependency import (  # noqa: E402
    DepStrategy,
    DepType,
    Dependency,
    DependencyResolver,
    get_resolver,
)

_SHELL_CANDIDATES = ("bash", "sh", "powershell", "pwsh", "cmd")
_RUST_CANDIDATES = ("rustc", "cargo")


def _runtime_dep(name):
    return Dependency(name=name, type=DepType.RUNTIME)


def _fresh_resolver():
    """新建解析器：`check_dep` 按 dep.name 缓存，用单例会串味（见模块 docstring）。"""
    return DependencyResolver()


# ---------------------------------------------------------------------------
# 1) 解析：runtime: 前缀
# ---------------------------------------------------------------------------

def test_runtime_prefix_parses_into_runtime_type():
    """`runtime:python` → DepType.RUNTIME、name 去掉前缀、策略沿用 system 的 HINT。"""
    deps = get_resolver().parse_deps(["runtime:python"])
    assert len(deps) == 1
    dep = deps[0]
    assert dep.type is DepType.RUNTIME
    assert dep.name == "python", "name 必须去掉 runtime: 前缀，实得 %r" % (dep.name,)
    assert dep.strategy is DepStrategy.HINT


def test_dep_type_has_runtime_member():
    """DepType 里必须有 runtime 成员（值 "runtime"），且与 action 区分开。"""
    assert hasattr(DepType, "RUNTIME"), "DepType 缺 RUNTIME 成员"
    assert DepType.RUNTIME.value == "runtime"
    assert DepType("runtime") is DepType.RUNTIME
    assert DepType.RUNTIME is not DepType.ACTION


def test_other_prefixes_and_bare_strings_unchanged():
    """旧行为不回归：其它前缀照旧，裸字符串仍是 action 依赖。

    回归点：补齐 `runtime:` 时很容易把分支插错位置（例如插在 system 之前），
    或把默认分支改掉；这里把既有前缀与裸字符串一起钉住。
    """
    resolver = get_resolver()
    deps = resolver.parse_deps([
        "system:pandoc", "pip:requests", "npm:shiki", "mcp:server",
        "action:actus.system.dialog_alert", "builtin:engine",
        "some.old.action",
    ])
    by_input = dict(zip(
        ["system:pandoc", "pip:requests", "npm:shiki", "mcp:server",
         "action:actus.system.dialog_alert", "builtin:engine", "some.old.action"],
        deps))
    assert by_input["system:pandoc"].type is DepType.SYSTEM
    assert by_input["system:pandoc"].name == "pandoc"
    assert by_input["pip:requests"].type is DepType.LANG
    assert by_input["pip:requests"].lang_manager == "pip"
    assert by_input["npm:shiki"].type is DepType.LANG
    assert by_input["npm:shiki"].lang_manager == "npm"
    assert by_input["mcp:server"].type is DepType.MCP
    assert by_input["action:actus.system.dialog_alert"].type is DepType.ACTION
    assert by_input["builtin:engine"].type is DepType.BUILTIN
    # 裸字符串：旧行为 = action 依赖（名字原样保留）
    bare = by_input["some.old.action"]
    assert bare.type is DepType.ACTION
    assert bare.name == "some.old.action"


def test_runtime_prefix_does_not_leak_into_action_dependency():
    """回归护栏：`runtime:python` 绝不能被当成「名为 runtime:python 的动作」。"""
    dep = get_resolver().parse_deps(["runtime:python"])[0]
    assert dep.type is not DepType.ACTION
    assert dep.name != "runtime:python"


def test_dict_form_carries_runtime_type():
    """dict 形态 `{"name": "python", "type": "runtime"}` 同样解析成 RUNTIME。"""
    deps = get_resolver().parse_deps([{"name": "python", "type": "runtime"}])
    assert len(deps) == 1
    assert deps[0].type is DepType.RUNTIME
    assert deps[0].name == "python"
    # 不写 type 时维持旧的 action 默认
    assert get_resolver().parse_deps([{"name": "x"}])[0].type is DepType.ACTION


# ---------------------------------------------------------------------------
# 2) 检查：抽象名展开
# ---------------------------------------------------------------------------

def test_runtime_shell_expands_to_shell_commands(monkeypatch):
    """`runtime:shell` 不是一个命令：按 bash/sh/powershell/pwsh/cmd 依次展开。

    两个方向都钉：命中即停（bash 命中后不再试 sh…），未命中时按表顺序试完全部候选。
    """
    tried = []

    def fake_which(cmd):
        tried.append(cmd)
        return "/fake/bash" if cmd == "bash" else None

    monkeypatch.setattr(dependency_mod.shutil, "which", fake_which)
    result = _fresh_resolver().check_dep(_runtime_dep("shell"))

    assert result.satisfied is True, result.message
    assert tried[0] == "shell", "同名命令必须优先尝试（否则 shell 依赖会被误判）"
    assert tried == ["shell", "bash"], \
        "命中后应停止展开，实得尝试序列 %r" % (tried,)
    assert result.name == "shell"

    # 一个都不命中：候选必须按展开表顺序全部试过（失败信息才有排障价值）
    tried = []

    def fake_none(cmd):
        tried.append(cmd)
        return None

    monkeypatch.setattr(dependency_mod.shutil, "which", fake_none)
    result = _fresh_resolver().check_dep(_runtime_dep("shell"))
    assert result.satisfied is False
    assert tried == ["shell"] + list(_SHELL_CANDIDATES), \
        "shell 展开顺序不对: %r" % (tried,)


def test_runtime_rust_expands_to_rustc_or_cargo(monkeypatch):
    """`runtime:rust` → rustc/cargo：任意一个命中即满足（两个方向都验）。"""
    def only(name):
        def fake_which(cmd):
            return "/fake/%s" % name if cmd == name else None
        return fake_which

    monkeypatch.setattr(dependency_mod.shutil, "which", only("cargo"))
    result = _fresh_resolver().check_dep(_runtime_dep("rust"))
    assert result.satisfied is True, "只有 cargo 时 rust 运行时也应满足"

    monkeypatch.setattr(dependency_mod.shutil, "which", only("rustc"))
    result = _fresh_resolver().check_dep(_runtime_dep("rust"))
    assert result.satisfied is True, "只有 rustc 时 rust 运行时也应满足"

    monkeypatch.setattr(dependency_mod.shutil, "which", only("none-of-them"))
    result = _fresh_resolver().check_dep(_runtime_dep("rust"))
    assert result.satisfied is False
    assert "未找到" in result.message
    # 失败信息必须列出试过的候选，排障时才知道展开表长什么样
    assert "rustc" in result.message and "cargo" in result.message


def test_runtime_check_consults_which_and_reports_message(monkeypatch):
    """`check_dep` 的判据必须就是 `shutil.which`（打桩成找不到 → 不满足）。"""
    monkeypatch.setattr(dependency_mod.shutil, "which", lambda cmd: None)
    result = _fresh_resolver().check_dep(_runtime_dep("python"))
    assert result.satisfied is False
    assert "python" in result.message
    assert result.strategy is DepStrategy.HINT

    monkeypatch.setattr(
        dependency_mod.shutil, "which",
        lambda cmd: "/fake/python" if cmd == "python" else None)
    result = _fresh_resolver().check_dep(_runtime_dep("python"))
    assert result.satisfied is True
    assert "/fake/python" in result.message


def test_unknown_runtime_name_is_unsatisfied():
    """本机确定不存在的运行时名 → satisfied=False（不抛异常、不误判可用）。"""
    result = _fresh_resolver().check_dep(_runtime_dep("definitely-not-a-runtime-xyz"))
    assert result.satisfied is False
    assert "definitely-not-a-runtime-xyz" in result.message


def test_shell_runtime_satisfied_on_this_machine():
    """真机对照：任意一个 shell 候选存在 → shell 运行时判可用（真实 PATH，非打桩）。

    用 `get_resolver()`（真源单例）且只读；候选一个都没有的极简环境上 skip。
    """
    present = [c for c in _SHELL_CANDIDATES if shutil.which(c)]
    if not present:
        pytest.skip("本机 PATH 里没有任何 shell 候选（%r），无法做真机对照"
                    % (list(_SHELL_CANDIDATES),))
    result = get_resolver().check_dep(_runtime_dep("shell"))
    assert result.satisfied is True, "本机存在 %r，shell 运行时却判不可用: %s" % (
        present, result.message)
