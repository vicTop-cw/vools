# -*- coding: utf-8 -*-
"""回归测试：vools.api 解析器的 expr 非字符串裸错（BUG-518）。

``curry_cmd.parse_lambda_or_func`` / ``memoize_cmd.parse_lambda_or_func`` 都先用
``safe_eval_expression``（安全），失败后回退到 builtins 函数名查找。问题在回退段：

    parse_lambda_or_func(None)   # safe_eval 抛错被 except Exception 吞掉，
                                 # 随后 hasattr(builtins, None) →
                                 # TypeError: attribute name must be string, not 'NoneType'
    parse_lambda_or_func(123)    # 同上（'int'）

修复后：入口校验 expr 为字符串，错误带实际类型/值。

安全性保持不变：两个解析器仍走 safe_eval_expression，危险表达式被拒；
``ops_cmd.parse_lambda`` / ``seq_cmd.parse_lambda`` 原本就抛 ExpressionSecurityError。
"""

import importlib

import pytest

curry_mod = importlib.import_module("vools.api.curry_cmd")
memo_mod = importlib.import_module("vools.api.memoize_cmd")
ops_mod = importlib.import_module("vools.api.ops_cmd")
seq_mod = importlib.import_module("vools.api.seq_cmd")


class TestParserValidation:
    @pytest.mark.parametrize("bad", [None, 123, 1.5, [1]])
    def test_curry_parser(self, bad):
        with pytest.raises(TypeError) as ei:
            curry_mod.parse_lambda_or_func(bad)
        assert "字符串" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_memoize_parser(self, bad):
        with pytest.raises(TypeError) as ei:
            memo_mod.parse_lambda_or_func(bad)
        assert "字符串" in str(ei.value)


class TestParserBehaviourUnchanged:
    def test_curry_lambda(self):
        assert curry_mod.parse_lambda_or_func("lambda x: x + 1")(2) == 3

    def test_curry_builtin_name(self):
        assert curry_mod.parse_lambda_or_func("abs")(-3) == 3

    def test_memoize_lambda(self):
        assert memo_mod.parse_lambda_or_func("lambda x: x * 2")(3) == 6

    def test_memoize_builtin_name(self):
        assert memo_mod.parse_lambda_or_func("len")([1, 2]) == 2

    def test_unparsable_expression_loud(self):
        with pytest.raises(ValueError) as ei:
            curry_mod.parse_lambda_or_func("x+1")
        assert "无法解析表达式" in str(ei.value)


class TestSecurityUnchanged:
    @pytest.mark.parametrize("mod", [curry_mod, memo_mod])
    @pytest.mark.parametrize("expr", [
        "__import__('os')",
        "lambda x: __import__('os')",
        "lambda x: open('/etc/passwd')",
    ])
    def test_dangerous_rejected(self, mod, expr):
        with pytest.raises((ValueError, Exception)):
            mod.parse_lambda_or_func(expr)

    @pytest.mark.parametrize("expr", [
        "__import__('os')",
        "lambda x: open('/etc/passwd')",
    ])
    def test_ops_parser_raises_security_error(self, expr):
        from vools.security.expression_handler import ExpressionSecurityError

        with pytest.raises(ExpressionSecurityError):
            ops_mod.parse_lambda(expr)

    def test_seq_parser_none_loud(self):
        from vools.security.expression_handler import ExpressionSecurityError

        with pytest.raises(ExpressionSecurityError):
            seq_mod.parse_lambda(None)
