# -*- coding: utf-8 -*-
"""回归测试：filter_not 的组合语义（BUG-439）+ 管道/柯里化契约。

原实现 ``filter_not = _pipe(filter, _not)``：``_inn(source)`` 实际展开为
``filter(_not(source))``——``filter`` 需要 (pred, source) 两个参数，因此**任何
调用都抛** ``TypeError: filter expected 2 arguments, got 1``；即便参数凑齐，
``_not(filter_obj)`` 也只是把 filter 对象取反得到 bool，与 "filter_not" 语义
完全无关。

修复：``filter_not`` 改为正确的柯里化函数，返回
``filter(lambda x: not pred(x), source)``（保留不满足条件的元素）。

同时锁定 ``curry`` 与 ``P/O`` 管道语义（``x | O(f)``）。
"""

import pytest

from vools.functional.pipe_ops import O, P, curry, filter_not


class TestFilterNot:
    def test_curried(self):
        assert list(filter_not(lambda x: x > 1)([1, 2, 3])) == [1]

    def test_direct(self):
        assert list(filter_not(lambda x: x > 1, [1, 2, 3])) == [1]

    def test_string_source(self):
        assert list(filter_not(lambda c: c != "a")("abc")) == ["a"]

    def test_empty_source(self):
        assert list(filter_not(lambda x: x > 1, [])) == []

    def test_keeps_all_when_pred_false(self):
        assert list(filter_not(lambda x: False, [1, 2])) == [1, 2]

    def test_keeps_none_when_pred_true(self):
        assert list(filter_not(lambda x: True, [1, 2])) == []

    def test_generator_source(self):
        assert list(filter_not(lambda x: x % 2 == 0)(range(4))) == [1, 3]

    def test_curried_partial_returned(self):
        """原实现会抛 'filter expected 2 arguments'；现在返回可继续柯里化的偏函数。"""
        partial = filter_not(lambda x: x > 1)
        assert callable(partial)
        assert list(partial([1, 2, 3])) == [1]

    def test_old_error_message_gone(self):
        try:
            filter_not(lambda x: x > 1)([1, 2, 3])
        except TypeError as e:
            assert "filter expected 2 arguments" not in str(e)


class TestCurryContract:
    def test_curried(self):
        assert curry(lambda a, b: a + b)(1)(2) == 3

    def test_direct(self):
        assert curry(lambda a, b: a + b)(1, 2) == 3

    def test_non_callable_rejected(self):
        with pytest.raises(TypeError):
            curry("x")


class TestPipeContract:
    def test_pipe_into_O(self):
        assert (5 | O(lambda x: x + 1)) == 6

    def test_pipe_string_expr_lambda(self):
        assert (3 | O("lambda x: x + 1")) == 4

    def test_pipe_string_expr_underscore(self):
        assert (3 | O("_ + 1")) == 4

    def test_pipe_bad_string_expr(self):
        """表达式字符串需 lambda/下划线形式（与 where 表达式同口径）。"""
        with pytest.raises(TypeError):
            3 | O("x + 1")

    def test_pipe_with_ix(self):
        assert (5 | P(lambda x, y: x * y, 2)) == 10

    def test_bad_ix(self):
        with pytest.raises(ValueError):
            P(lambda x: x, ix=0)
