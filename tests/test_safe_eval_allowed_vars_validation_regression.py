# -*- coding: utf-8 -*-
"""回归测试：SafeExpressionEvaluator 的 allowed_vars 入口校验（BUG-425）。

原实现 ``self.allowed_vars = allowed_vars or {}`` 接受任意值：

    SafeExpressionEvaluator("x")     # 非空字符串被当成白名单，变量永远找不到
    SafeExpressionEvaluator([1, 2])  # 白名单看似生效，取值时抛 TypeError/KeyError

修复：非 dict（且非 None）在构造时即抛带类名的 TypeError。安全拒绝语义
（属性访问、dunder、import、open、getattr）保持不变。
"""

import pytest

from vools.security.safe_eval import SafeExpressionEvaluator, SafeEvalError


class TestAllowedVarsValidation:
    @pytest.mark.parametrize("bad", ["x", [1, 2], (1, 2), 123, object()])
    def test_non_dict_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            SafeExpressionEvaluator(bad)
        assert "SafeExpressionEvaluator" in str(ei.value)

    def test_none_and_dict_accepted(self):
        assert SafeExpressionEvaluator().allowed_vars == {}
        assert SafeExpressionEvaluator({"x": 1}).allowed_vars == {"x": 1}
        assert SafeExpressionEvaluator({}).allowed_vars == {}


class TestEvaluationUnchanged:
    def test_arithmetic(self):
        assert SafeExpressionEvaluator().evaluate("1 + 1") == 2

    def test_allowed_variable(self):
        assert SafeExpressionEvaluator({"x": 3}).evaluate("x * 2") == 6

    def test_unknown_variable_denied(self):
        with pytest.raises(SafeEvalError):
            SafeExpressionEvaluator({"x": 3}).evaluate("y")

    def test_attribute_access_denied(self):
        with pytest.raises(SafeEvalError):
            SafeExpressionEvaluator({"x": 3}).evaluate("x.__class__")

    def test_dunder_globals_escape_denied(self):
        with pytest.raises(SafeEvalError):
            SafeExpressionEvaluator({"x": 3}).evaluate(
                "x.__class__.__init__.__globals__")

    def test_import_denied(self):
        with pytest.raises(SafeEvalError):
            SafeExpressionEvaluator().evaluate("import os")

    def test_builtin_call_denied(self):
        with pytest.raises(SafeEvalError):
            SafeExpressionEvaluator().evaluate("open('/etc/passwd')")

    def test_getattr_denied(self):
        with pytest.raises(SafeEvalError):
            SafeExpressionEvaluator({"x": 3}).evaluate("getattr(x, 'y')")
