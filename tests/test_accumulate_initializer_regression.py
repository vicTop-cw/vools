# -*- coding: utf-8 -*-
"""回归测试：curried.accumulate 的 initializer 可用且对齐 stdlib 语义（BUG-214）。

原实现把 initializer 作为 `itertools.accumulate` 第三个位置参数传入——该
参数是 keyword-only ``initial``（py3.8+），py3.6/3.7（本包声明最低版本）
不存在，带 initializer 的调用在所有 Python 版本 100% TypeError。

修复：initializer 非 None 时走确定性手动累积——X 为输出首元素，其后每步
func(prev, x)，对齐 stdlib py3.8 ``accumulate(iterable, func, initial=X)``。
"""

import itertools
import operator

import pytest

from vools.curried.iteration import accumulate


class TestAccumulateWithInitializer:
    """initializer 分支可用（BUG-214 核心）。"""

    def test_add_with_initializer(self):
        assert accumulate(operator.add, [1, 2, 3], 10) == [10, 11, 13, 16]

    def test_matches_stdlib_initial(self):
        for iterable, init in (
            ([1, 2, 3], 10),
            ([], 5),
            ([7], 0),
            ([1, 2, 3, 4, 5], 100),
        ):
            std = list(itertools.accumulate(
                iterable, operator.add, initial=init))
            assert accumulate(operator.add, iterable, init) == std

    def test_empty_iterable_returns_initial_only(self):
        assert accumulate(operator.add, [], 10) == [10]

    def test_mul_with_initializer(self):
        assert accumulate(operator.mul, [2, 3, 4], 5) == [5, 10, 30, 120]

    def test_curried_stepwise(self):
        step = accumulate(operator.add)
        assert step([1, 2], 7) == [7, 8, 10]


class TestAccumulateWithoutInitializerUnchanged:
    """无 initializer 路径保持原语义（防修复串扰）。"""

    def test_basic_add(self):
        assert accumulate(operator.add, [1, 2, 3, 4, 5]) == [1, 3, 6, 10, 15]

    def test_mul(self):
        assert accumulate(lambda x, y: x * y, [1, 2, 3, 4]) == [1, 2, 6, 24]

    def test_empty(self):
        assert accumulate(operator.add, []) == []

    def test_single(self):
        assert accumulate(operator.add, [7]) == [7]