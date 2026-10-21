# -*- coding: utf-8 -*-
"""回归测试：iif 的 supp 开关在 data 模式生效（BUG-225）。

原 `_eval_string_condition` 声明 `supp: bool` 参数但函数体从不引用——
supp=False 时普通字符串条件仍被无条件编译求值，docstring 的
「supp: 是否启用字符串表达式编译」开关静默失效（同模块
ConditionBuilder 三处认真分支该开关，唯顶层路径不认）。

修复：supp=False 且无 '->' 前缀 → 不编译，按 docstring 兜底返回
bool(condition)；'->' 前缀保持强制编译。
"""

import pytest

from vools.functional.iif import iif


class TestSuppSwitchHonored:
    """BUG-225 核心：supp=False 真的关掉表达式编译。"""

    def test_supp_false_no_compile(self):
        # "x > 99"：bool(非空串)=True → big；若编译则 10>99=False → small
        assert iif("x > 99", "big", "small", data=10, supp=False) == "big"

    def test_supp_true_compiles(self):
        assert iif("x > 99", "big", "small", data=10, supp=True) == "small"

    def test_switch_discriminates(self):
        # 开关两态必须可区分（修复前恒同值）
        r_off = iif("x > 99", "big", "small", data=10, supp=False)
        r_on = iif("x > 99", "big", "small", data=10, supp=True)
        assert r_off != r_on


class TestArrowPrefixForced:
    """'->' 前缀=强制编译，不受 supp=False 影响（docstring 契约）。"""

    def test_arrow_compiles_even_supp_false(self):
        assert iif("-> x > 99", "big", "small", data=10, supp=False) == "small"

    def test_arrow_supp_true(self):
        assert iif("-> x > 3", "big", "small", data=10, supp=True) == "big"


class TestDefaultPathsUnchanged:
    """默认 supp=True 既有语义保持（防修复过度）。"""

    def test_plain_compile(self):
        assert iif("x > 3", "big", "small", data=10) == "big"

    def test_callable_condition(self):
        assert iif(lambda v: v > 5, "y", "n", data=3) == "n"

    def test_bool_condition(self):
        assert iif(True, "y", "n") == "y"

    def test_non_compile_fallback_still_bool(self):
        # 编译失败的普通串（含非法语法）→ bool(condition) 兜底不变
        assert iif("x >", "big", "small", data=1) == "big"