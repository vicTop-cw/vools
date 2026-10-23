# -*- coding: utf-8 -*-
"""回归测试：vic_execute 不再把字符串拆成字符（BUG-359）。

`vools.decorators.trd.vic_execute`（`trd`/`proc` 的实现）原实现：

    its = iterable if isinstance(iterable, Iterable) else [iterable]

`str`/`bytes`/`bytearray` 都是 `Iterable`，于是「单个字符串」被**逐字符**展开：

    @vic_execute()
    def up(x): return x.upper()
    up('abc')        # -> ['A', 'B', 'C']     （期望 ['ABC']）
    up(b'ab')        # -> [97, 98]            （bytes 迭代出整数）

这是最容易踩的静默错值（每个字符单独跑一次，结果看起来"像列表"）。
修复：str/bytes/bytearray 视为**单个值**；其它可迭代对象仍逐元素执行。
"""

import pytest

from vools.decorators.trd import proc, trd, vic_execute


@vic_execute(max_workers=3)
def _upper(x):
    return str(x).upper()


class TestStringIsSingleValue:
    def test_str(self):
        # 修复前：['A', 'B', 'C']
        assert _upper('abc') == ['ABC']

    def test_bytes(self):
        # 修复前：[97, 98]
        assert _upper(b'ab') == ["B'AB'"]

    def test_bytearray(self):
        assert _upper(bytearray(b'ab')) == ["BYTEARRAY(B'AB')"]

    def test_empty_str(self):
        assert _upper('') == ['']


class TestIterablesStillExpanded:
    def test_list(self):
        assert sorted(_upper(['a', 'b'])) == ['A', 'B']

    def test_tuple(self):
        assert sorted(_upper(('a', 'b'))) == ['A', 'B']

    def test_set(self):
        assert sorted(_upper({'a', 'b'})) == ['A', 'B']

    def test_dict_iterates_keys(self):
        assert sorted(_upper({'x': 1, 'y': 2})) == ['X', 'Y']

    def test_generator(self):
        @vic_execute(max_workers=1)
        def ident(x):
            return x

        assert ident(iter([1, 2])) == [1, 2]

    def test_empty_list(self):
        assert _upper([]) == []


class TestSingleNonIterable:
    def test_int(self):
        assert _upper(5) == ['5']

    def test_none(self):
        assert _upper(None) == ['NONE']


class TestPredefinedDecorators:
    def test_trd_exists_and_runs(self):
        @trd
        def double(x):
            return x * 2

        assert sorted(double([1, 2])) == [2, 4]

    def test_exception_propagates(self):
        @vic_execute(max_workers=2)
        def boom(x):
            if x == 2:
                raise ValueError('boom')
            return x

        with pytest.raises(ValueError):
            boom([1, 2, 3])