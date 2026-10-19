# -*- coding: utf-8 -*-
"""回归测试：safe_lambda 不误拒合法 lambda 表达式（BUG-202）。

safe_lambda 曾用 _Placeholder 求值 AST 做"预校验"（结果被丢弃的死代码），导致
Subscript / Attribute / IfExp / 内置函数调用等合法表达式被 SafeEvalError 误拒。
现删除该死代码，安全边界由 _is_safe_expr 黑名单 + 空 __builtins__ 的 eval 提供。
"""

import pytest

from vools.security.safe_eval import SafeEvalError, safe_lambda


class TestSafeLambdaLegalExpressions:
    """合法 lambda 表达式必须可用（BUG-202）。"""

    def test_binary_op(self):
        f = safe_lambda(('x', 'y'), "x + y")
        assert f(1, 2) == 3

    def test_subscript(self):
        f = safe_lambda(('x',), "x[0]")
        assert f([10, 20]) == 10

    def test_attribute_call(self):
        f = safe_lambda(('x',), "x.upper()")
        assert f("ab") == "AB"

    def test_if_exp(self):
        f = safe_lambda(('x',), "1 if x else 0")
        assert f(True) == 1
        assert f(False) == 0

    def test_multi_op(self):
        f = safe_lambda(('x',), "x * 2 + 1")
        assert f(5) == 11

    def test_mixed_args(self):
        f = safe_lambda(('x', 'y', 'z'), "(x + y) * z")
        assert f(1, 2, 3) == 9


class TestSafeLambdaStillRejects:
    """危险表达式仍须被拒绝（安全边界未降级）。"""

    @pytest.mark.parametrize(
        "expr",
        [
            "__import__('os')",
            "x.__class__",
            "getattr(x,'real')",
            "open('/etc/passwd')",
            "import os",
        ],
    )
    def test_dangerous_rejected(self, expr):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), expr)

    def test_syntax_error_rejected(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), "x +")

    def test_invalid_param_name_rejected(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('1x',), "1")