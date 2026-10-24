# -*- coding: utf-8 -*-
"""回归测试：表达式字符串的 lambda 形式静默失效（BUG-443）。

``safe_compile_expression`` 原实现无条件把表达式拼成 ``lambda {args}: {expr}``。
当 ``expr`` 本身已经是 lambda 形式时，会编译成嵌套 lambda：

    VList([1, 2, 3]).filter('lambda x: x > 1')
    # 修复前 -> [1, 2, 3]   ← 返回内层 lambda 对象（恒真），过滤静默失效
    # 修复后 -> [2, 3]

同一根因也影响 ``generate_lambda('lambda x: x > 1')(5)``（返回 lambda 对象而非
True）等所有 ``safe_compile_expression`` 调用方。另 ``Seq.filter`` 原先不支持
字符串形式（`'str' object is not callable`），现与 ``VList.filter`` 同口径。

非 lambda 的裸表达式（如 ``'x > 1'``）与多参数表达式（``'x + y'``）行为保持
不变；``where`` 的「必须 lambda 形式」守卫也不受影响。
"""

import pytest

from vools.data.seq import Seq
from vools.data.vlist import VList
from vools.security.expression_handler import create_filter_func, safe_compile_expression
from vools.utils.tools import generate_lambda


class TestCreateFilterFunc:
    @pytest.mark.parametrize("expr", ["x > 1", "lambda x: x > 1"])
    def test_both_forms_filter(self, expr):
        fn = create_filter_func(expr)
        assert [bool(fn(v)) for v in (0, 1, 2)] == [False, False, True]

    def test_lambda_is_not_returned_as_value(self):
        """修复前 fn(v) 返回的是内层 lambda 对象（恒真）。"""
        fn = create_filter_func("lambda x: x > 1")
        result = fn(0)
        assert result is False or result == False  # noqa: E712
        assert not callable(result)


class TestVListFilter:
    @pytest.mark.parametrize("expr", ["x > 1", "lambda x: x > 1"])
    def test_string_forms(self, expr):
        assert list(VList([1, 2, 3]).filter(expr)) == [2, 3]

    def test_callable_unchanged(self):
        assert list(VList([1, 2, 3]).filter(lambda x: x > 1)) == [2, 3]

    def test_keeps_none_when_all_false(self):
        assert list(VList([1, 2, 3]).filter("lambda x: x > 99")) == []


class TestSeqFilterStringSupport:
    def test_string_expression(self):
        assert list(Seq([1, 2, 3]).filter("x > 1")) == [2, 3]

    def test_lambda_expression(self):
        assert list(Seq([1, 2, 3]).filter("lambda x: x > 1")) == [2, 3]

    def test_callable_unchanged(self):
        assert list(Seq([1, 2, 3]).filter(lambda x: x > 1)) == [2, 3]


class TestGenerateLambda:
    def test_lambda_form_returns_bool(self):
        fn = generate_lambda("lambda x: x > 1")
        assert fn(5) is True
        assert fn(0) is False

    def test_bare_form_unchanged(self):
        fn = generate_lambda("x > 1")
        assert fn(5) is True
        assert fn(0) is False


class TestUnchangedContracts:
    def test_multi_param_expression(self):
        fn = safe_compile_expression("x + y", ("x", "y"))
        assert fn(1, 2) == 3

    def test_where_requires_lambda_form(self):
        with pytest.raises(ValueError):
            list(Seq([1, 2, 3]).where("x > 1"))

    def test_where_lambda_string(self):
        assert list(Seq([1, 2, 3]).where("lambda x: x > 1")) == [2, 3]

    def test_unsafe_expression_rejected(self):
        from vools.security.expression_handler import ExpressionSecurityError

        with pytest.raises(ExpressionSecurityError):
            safe_compile_expression("__import__('os')")
