# -*- coding: utf-8 -*-
"""回归测试：Seq.cycle 的 times 语义/校验 与 Seq.tee 文档纠偏（BUG-413）。

**cycle(func, times)** 是「循环调用 func 生成序列」的工厂方法，原实现三处问题：

    list(Seq.cycle(lambda: 'x', 0))     # 修复前：**无限产出**（times 减到 -1，永不 == 0）
    list(Seq.cycle(lambda: 'x', 1.5))   # 被 int() 静默截断为 1
    list(Seq.cycle(lambda: 'x', '3'))   # 字符串被静默当成 3
    Seq.cycle(generator_func, 2)        # times 被完全忽略（生成器分支直接 return）

**tee(n, fillvalue)** 文档写「tee 成 n 路并行迭代器」，但实现（BUG-175 起）
是**按 n 元组分块**（与 grouper 一致，末组补 fillvalue）：

    list(Seq([1, 2, 3]).tee(2))         # -> [(1, 2), (3, None)]
    # 按旧文档写法 `a, b = seq.tee(2)` 会得到 (1,2) 与 (3,None) 两个元组

修复：times 必须 int（bool 除外）且非负，0 返回空序列；生成器函数分支按
times 截断（islice）；tee 的 docstring 改为「分块」并给出示例。
"""

import itertools

import pytest

from vools.data.seq import Seq


class TestCycleTimes:
    def test_zero_returns_empty(self):
        # 修复前：无限产出（times 递减到 -1 永不等于 0）
        assert list(Seq.cycle(lambda: 'x', 0)) == []

    def test_positive_limit(self):
        assert list(Seq.cycle(lambda: 'x', 3)) == ['x', 'x', 'x']

    def test_none_is_infinite(self):
        assert list(itertools.islice(Seq.cycle(lambda: 'x'), 4)) == ['x'] * 4

    @pytest.mark.parametrize('bad', [-1, -100])
    def test_negative_rejected(self, bad):
        with pytest.raises(ValueError):
            Seq.cycle(lambda: 'x', bad)

    @pytest.mark.parametrize('bad', [1.5, 2.0, '3', True, [2]])
    def test_non_int_rejected(self, bad):
        with pytest.raises(TypeError):
            Seq.cycle(lambda: 'x', bad)

    def test_generator_function_with_times(self):
        def gen():
            yield from range(10)

        # 修复前：times 被忽略，产出全部 10 个
        assert list(Seq.cycle(gen, 2)) == [0, 1]

    def test_generator_function_without_times(self):
        def gen():
            yield from range(5)

        assert list(Seq.cycle(gen)) == [0, 1, 2, 3, 4]


class TestTeeDocumentedAsChunking:
    def test_two_per_chunk(self):
        assert list(Seq([1, 2, 3]).tee(2)) == [(1, 2), (3, None)]

    def test_three_per_chunk(self):
        assert list(Seq([1, 2, 3, 4]).tee(3)) == [(1, 2, 3), (4, None, None)]

    def test_fillvalue(self):
        assert list(Seq([1, 2, 3]).tee(2, fillvalue=0)) == [(1, 2), (3, 0)]

    def test_exact_multiple(self):
        assert list(Seq([1, 2, 3, 4]).tee(2)) == [(1, 2), (3, 4)]

    def test_docstring_mentions_chunking(self):
        doc = (Seq.tee.__doc__ or '').strip()
        # 首句必须是「分块」语义（旧文档首句写的是"tee 成 n 路并行迭代器"）
        first_line = doc.splitlines()[0]
        assert '分块' in first_line
        assert 'grouper' in doc