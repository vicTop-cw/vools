# -*- coding: utf-8 -*-
"""回归测试：Ops 管道命名空间契约（BUG-440）。

``Ops`` 的成员都由 ``static_pipeN`` 包装：**管道值落在第 N 个位置、显式参数在前**。
据此：

* ``filter/where/map/select``（第 2 位）-> ``fn(pred, source)`` ✓ 自然；
* ``starmap/reduce/dropwhile/nlargest``（第 2 位）-> 自然参数序 ✓；
* ``all/any/sum/count``（第 1 位）-> 管道值即唯一参数 ✓。

**BUG-440**：``compress`` 是唯一反例——``itertools.compress(data, selectors)``
需要 (data, selectors)，但原实现用 ``static_pipe2`` 把参数接成
``compress(selectors, data)``，导致自然写法
``[1,2,3] | Ops.compress([T,F,T])`` 返回 ``[True, False, True]``（selector 列表
本身）而不是 ``[1, 3]``。修复后改为 ``static_pipe1`` 并显式固定
``(data, selectors)`` 顺序。

这里把管道约定与修复后的 compress 语义一并锁定。
"""

import pytest

from vools.functional.pipe_ops import O, Ops, P


class TestCompress:
    def test_natural_order(self):
        assert list([1, 2, 3] | Ops.compress([True, False, True])) == [1, 3]

    def test_all_selectors_true(self):
        assert list([1, 2, 3] | Ops.compress([True, True, True])) == [1, 2, 3]

    def test_none_selectors_true(self):
        assert list([1, 2, 3] | Ops.compress([False, False, False])) == []

    def test_empty_selectors(self):
        assert list([1, 2, 3] | Ops.compress([])) == []


class TestPipeConventions:
    def test_pipe1_builtins(self):
        assert [1, 2] | Ops.all is True
        assert [0, 1] | Ops.all is False
        assert [0] | Ops.any is False
        assert [1, 2, 3] | Ops.sum == 6
        assert [1, 2, 3] | Ops.count == 3

    def test_pipe1_arithmetic(self):
        assert 5 | Ops.add(1) == 6
        assert 5 | Ops.mul(2) == 10
        assert 5 | Ops.sub(2) == 3
        assert -5 | Ops.abs() == 5
        assert 0 | Ops.cos == 1.0

    def test_pipe2_map_filter(self):
        assert list([1, 2, 3] | Ops.map(lambda x: x * 2)) == [2, 4, 6]
        assert list([1, 2, 3] | Ops.filter(lambda x: x > 1)) == [2, 3]
        assert list([1, 2, 3] | Ops.select(lambda x: x * 2)) == [2, 4, 6]
        assert list([1, 2, 3] | Ops.where(lambda x: x > 1)) == [2, 3]

    def test_pipe2_starmap_dropwhile(self):
        assert list([(1, 2), (3, 4)] | Ops.starmap(lambda a, b: a + b)) == [3, 7]
        assert list([1, 2, 3, 1] | Ops.dropwhile(lambda x: x < 3)) == [3, 1]

    def test_pipe1_groupby_chain_distinct(self):
        assert list(range(3) | Ops.as_list) == [0, 1, 2]
        assert [1, 1, 2] | Ops.count_by == [(1, 2), (2, 1)]
        assert list([[1, 2], [3]] | Ops.chain) == [[1, 2], [3]]
        assert list([1, 1, 2, 2, 3] | Ops.distinct) == [1, 2, 3]

    def test_zip(self):
        assert list([1, 2, 3] | Ops.zip([10, 20, 30])) == [(1, 10), (2, 20), (3, 30)]


class TestPipeWrapperValidation:
    def test_bad_ix(self):
        with pytest.raises(ValueError):
            P(lambda x: x, ix=0)

    def test_o_expression_needs_lambda(self):
        assert 3 | O("lambda x: x + 1") == 4
        with pytest.raises(TypeError):
            3 | O("x + 1")
