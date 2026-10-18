# -*- coding: utf-8 -*-
"""tests/functional/test_safe_arrow_func.py — safe_arrow_func 安全沙箱（钉 BUG-90）

BUG-90：arrow_func 使用原始 eval/exec 且 env 默认注入 __builtins__，任何表达式
都可调用 __import__/eval/open 等实现任意代码执行（RCE）。同包 iif.py 已使用
safe_lambda 沙箱，但 arrow_func 无安全变体，无文档警告。

修复：新增 safe_arrow_func，基于 safe_lambda 编译，白名单沙箱。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.functional.arrow_func import safe_arrow_func, arrow_func  # noqa: E402
from vools.security.safe_eval import SafeEvalError  # noqa: E402


class TestSafeArrowFuncBasic:
    """safe_arrow_func 基本功能"""

    def test_arithmetic(self):
        f = safe_arrow_func("x => x * 2")
        assert f(21) == 42

    def test_multi_param(self):
        f = safe_arrow_func("x, y => x + y")
        assert f(1, 2) == 3

    def test_comparison(self):
        f = safe_arrow_func("x => x > 3")
        assert f(5) is True
        assert f(1) is False

    def test_no_params(self):
        f = safe_arrow_func("=> 42")
        assert f() == 42


class TestSafeArrowFuncSecurity:
    """safe_arrow_func 必须阻止代码注入"""

    def test_import_blocked(self):
        with pytest.raises(Exception):
            safe_arrow_func("x => __import__('os').system('echo hi')")

    def test_eval_blocked(self):
        with pytest.raises(Exception):
            safe_arrow_func("x => eval('1+1')")

    def test_open_blocked(self):
        with pytest.raises(Exception):
            safe_arrow_func("x => open('/etc/passwd').read()")

    def test_builtins_blocked(self):
        with pytest.raises(Exception):
            safe_arrow_func("x => __builtins__")

    def test_exec_blocked(self):
        with pytest.raises(Exception):
            safe_arrow_func("x => exec('print(1)')")


class TestArrowFuncVsSafe:
    """arrow_func 与 safe_arrow_func 行为差异"""

    def test_arrow_func_allows_import(self):
        """arrow_func 是原始能力（不沙箱）——文档明确说明"""
        f = arrow_func("x => __import__('os')")
        result = f(0)
        assert result is not None

    def test_safe_arrow_blocks_import(self):
        """safe_arrow_func 必须沙箱"""
        with pytest.raises(Exception):
            safe_arrow_func("x => __import__('os')")

    def test_both_support_basic(self):
        """两者都支持基本表达式"""
        f1 = arrow_func("x => x + 1")
        f2 = safe_arrow_func("x => x + 1")
        assert f1(1) == f2(1) == 2