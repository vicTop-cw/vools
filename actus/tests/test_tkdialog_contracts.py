# -*- coding: utf-8 -*-
"""actus/tests/test_tkdialog_contracts.py — tkdialog 纯校验函数契约（0% 覆盖）。

`tkdialog.py` 是等待类弹窗共用引擎（800 行、11 处 tkinter），整体 0% 覆盖。
本文件**只测不依赖 GUI 的纯逻辑**：`validate_spec` / `validate_options` /
`validate_fields`（模块 docstring 明确"供 dry_run 与单测复用"）。
**绝不建 Tk root**：CI 无显示，真实窗口路径（run_modal/run_dialog…）不在此测。

语义钉点（与产品 docstring 对齐，不按直觉假设）：
  * `timeout_confirm` / `timeout_cancel` 的 timeout_seconds **可以缺省**
    （timeout_confirm 默认 30s）；`locked` 下给 timeout 是**安全阀**（到时取消），
    所以"非 timeout 类带 timeout"是合法组合；
  * `validate_*` 返回 None=合法，否则结构化 `{code:'param_invalid', message}`，
    **不抛异常**；
  * 模块目前全仓零引用（未接线）；本文件用"全仓 import 扫描"钉住这一点，
    将来接线会红、提醒同步更新声明与测试。
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import tkdialog  # noqa: E402


_FOUR_POLICIES = ["locked", "blur_cancel", "timeout_confirm", "timeout_cancel"]
_FOUR_KINDS = ["info", "warning", "error", "success"]


def _assert_param_invalid(result, needle=None):
    assert isinstance(result, dict), result
    assert result.get("code") == "param_invalid", result
    assert isinstance(result.get("message"), str) and result["message"], result
    if needle is not None:
        assert needle in result["message"], result


# ===========================================================================
# validate_spec：消息 / 四种 focus_policy / 四种 kind / timeout 边界
# ===========================================================================

@pytest.mark.parametrize("policy", _FOUR_POLICIES)
@pytest.mark.parametrize("kind", _FOUR_KINDS)
def test_validate_spec_accepts_all_policy_kind_combinations(policy, kind):
    """退步了会怎样：四种焦点策略 × 四种 kind 的正交组合被误拒（弹窗动作文件
    组合爆炸的初衷就是允许任意组合）——合法声明被判 param_invalid。

    断言：16 种组合 + 缺省 timeout_seconds 全部返回 None。
    """
    assert tkdialog.validate_spec("hello", policy, None, kind) is None


def test_validate_spec_timeout_semantics_are_documented_contract():
    """退步了会怎样：把 timeout 规则改成"timeout_* 必须带 / 非 timeout 必须不带"——
    违反产品 docstring（timeout_confirm 默认 30s；locked 下 timeout 是安全阀），
    已有动作文件会被误拒。

    断言（钉住当前声明语义）：
      * timeout_confirm / timeout_cancel 缺省 timeout → 合法（默认 30s）；
      * locked + timeout=5 → 合法（安全阀：到时自动取消）。
    """
    assert tkdialog.validate_spec("hi", "timeout_confirm", None, "info") is None
    assert tkdialog.validate_spec("hi", "timeout_cancel", None, "info") is None
    assert tkdialog.validate_spec("hi", "locked", 5, "info") is None


def test_validate_spec_message_and_timeout_boundaries():
    """退步了会怎样：边界被放松/收紧 —— 2000 字符边界错位、timeout 0 或 24h+1
    被接受（倒计时异常/无限挂起）。

    断言：message=None 合法；非字符串/2001 字符 → 报错；timeout 1 与 86400 合法，
    0 / 86401 / 非数字 → 报错。
    """
    assert tkdialog.validate_spec(None, "locked", None, "info") is None
    _assert_param_invalid(tkdialog.validate_spec(123, "locked", None, "info"), "message")
    _assert_param_invalid(
        tkdialog.validate_spec("x" * 2001, "locked", None, "info"), "message")

    assert tkdialog.validate_spec("hi", "locked", 1, "info") is None
    assert tkdialog.validate_spec("hi", "locked", 86400, "info") is None
    _assert_param_invalid(tkdialog.validate_spec("hi", "locked", 0, "info"),
                          "timeout_seconds")
    _assert_param_invalid(tkdialog.validate_spec("hi", "locked", 86401, "info"),
                          "timeout_seconds")
    _assert_param_invalid(tkdialog.validate_spec("hi", "locked", "abc", "info"),
                          "timeout_seconds")


def test_validate_spec_rejects_unknown_policy_and_kind():
    """退步了会怎样（变异重点）：非法 focus_policy/kind 被静默接受 —— 运行期才
    走错焦点策略（如把 locked 写成 lock），等待类弹窗行为完全不符预期。

    断言：未知 policy/kind 均返回 param_invalid，且消息里点名合法取值。
    """
    bad_policy = tkdialog.validate_spec("hi", "lock", None, "info")
    _assert_param_invalid(bad_policy, "focus_policy")
    assert "locked" in bad_policy["message"]

    bad_kind = tkdialog.validate_spec("hi", "locked", None, "fatal")
    _assert_param_invalid(bad_kind, "kind")
    assert "info" in bad_kind["message"]


# ===========================================================================
# validate_options
# ===========================================================================

def test_validate_options_accepts_valid_single_and_max():
    """退步了会怎样：合法选项被拒（1 项/20 项/60 字符边界）—— single/multi 弹窗
    声明的选项无法通过 dry_run 校验。

    断言：1 项、20 项、60 字符项全部返回 None。
    """
    assert tkdialog.validate_options(["a"]) is None
    assert tkdialog.validate_options(["opt%d" % i for i in range(20)]) is None
    assert tkdialog.validate_options(["x" * 60]) is None


@pytest.mark.parametrize("options,needle", [
    ([], "options"),
    ("not-a-list", "options"),
    (["opt%d" % i for i in range(21)], "20"),
    ([1], "options[0]"),
    (["   "], "options[0]"),
    (["x" * 61], "options[0]"),
])
def test_validate_options_rejects_invalid(options, needle):
    """退步了会怎样：空/非数组/超 20 项/非字符串/空白/超 60 字符的选项被接受 ——
    GUI 渲染出空格子或 index 越界。

    断言：全部返回 param_invalid，消息点名具体约束。
    """
    _assert_param_invalid(tkdialog.validate_options(options), needle)


# ===========================================================================
# validate_fields
# ===========================================================================

def test_validate_fields_accepts_valid_forms():
    """退步了会怎样：合法表单被误拒（text/checkbox/select 三种字段形态）——
    form 弹窗声明无法通过校验。

    断言：text（默认 type）、checkbox(bool default)、select(default 属于 options)
    全部返回 None。
    """
    assert tkdialog.validate_fields([{"key": "name", "label": "Name"}]) is None
    assert tkdialog.validate_fields([
        {"key": "agree", "label": "Agree", "type": "checkbox", "default": True}]) is None
    assert tkdialog.validate_fields([
        {"key": "env", "label": "Env", "type": "select",
         "options": ["dev", "prod"], "default": "dev"}]) is None


@pytest.mark.parametrize("fields,needle", [
    ([], "fields"),
    ("not-a-list", "fields"),
    ([{"key": "k", "label": "L"}] * 13, "12"),
    (["not-a-dict"], "fields[0]"),
    ([{"key": "Bad-Key", "label": "L"}], "fields[0].key"),
    ([{"key": "1abc", "label": "L"}], "fields[0].key"),
    ([{"key": "a" * 31, "label": "L"}], "fields[0].key"),
    ([{"key": "a", "label": "A"}, {"key": "a", "label": "B"}], "重复"),
    ([{"key": "a"}], "fields[0].label"),
    ([{"key": "a", "label": ""}], "fields[0].label"),
    ([{"key": "a", "label": "L" * 31}], "fields[0].label"),
    ([{"key": "a", "label": "A", "type": "radio"}], "fields[0].type"),
    ([{"key": "a", "label": "A", "type": "select"}], "fields[0].options"),
    ([{"key": "a", "label": "A", "type": "select",
       "options": ["x"], "default": "y"}], "fields[0].default"),
    ([{"key": "a", "label": "A", "type": "checkbox",
       "default": "yes"}], "fields[0].default"),
    ([{"key": "a", "label": "A", "default": 123}], "fields[0].default"),
    ([{"key": "a", "label": "A", "default": "x" * 501}], "fields[0].default"),
])
def test_validate_fields_rejects_invalid(fields, needle):
    """退步了会怎样：缺 key/重复 key/非法 key 字符/超长 label/未知 type/
    select 缺 options/default 不在 options/checkbox 非布尔 default 被静默接受 ——
    运行期表单渲染崩或提交值类型错。

    断言：全部返回 param_invalid，消息点名具体字段与约束。
    """
    _assert_param_invalid(tkdialog.validate_fields(fields), needle)


# ===========================================================================
# 声明与"未接线"守卫
# ===========================================================================

def test_module_declares_shared_engine_and_not_wired():
    """退步了会怎样：有人删掉 "供 dry_run 与单测复用 / 共用底座" 的声明，或**把
    tkdialog 接进产品路径却不同步更新声明与测试** —— 后来人不知道这是"仅库/未接线"
    模块，误以为改它不会影响任何入口。

    断言（两部分）：
      * module docstring 仍声明其"共用底座 / 供单测复用"定位（未接线的语义声明）；
      * 全仓（vools/ 下 .py，排除自身）**没有任何 import/引用 tkdialog**。
    说明：当前 docstring 没有字面"未接线"三个字，故按语义钉；若将来产品加了字面
    声明，可把关键词收紧。
    """
    doc = tkdialog.__doc__ or ""
    assert any(word in doc for word in ("共用底座", "单测复用", "未接线", "仅库")), doc[:200]

    pattern = re.compile(r"(from\s+(?:\.|vools\.actus\.)tkdialog\s+import"
                         r"|import\s+tkdialog\b|from\s+vools\.actus\s+import\s+tkdialog)")
    vools_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vools_root = os.path.join(vools_root, "vools")
    hits = []
    for dirpath, dirnames, filenames in os.walk(vools_root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            if os.path.abspath(full) == os.path.abspath(tkdialog.__file__):
                continue
            with open(full, "r", encoding="utf-8", errors="replace") as handle:
                for lineno, line in enumerate(handle, 1):
                    if pattern.search(line):
                        hits.append((os.path.relpath(full, vools_root), lineno, line.strip()))
    assert not hits, (
        "tkdialog 已被接线（%r）；请同步更新模块声明与测试（本守卫故意会红）" % (hits,))


def test_public_validate_helpers_are_exported():
    """退步了会怎样：`__all__` 漏掉 validate_* —— dry_run / 单测按公开接口导入
    直接 ImportError。

    断言：`__all__` 同时包含三个纯校验函数与 FOCUS_POLICIES。
    """
    exported = set(tkdialog.__all__)
    for name in ("validate_spec", "validate_options", "validate_fields",
                 "FOCUS_POLICIES"):
        assert name in exported, (name, sorted(exported))
