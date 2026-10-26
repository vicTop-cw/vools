# -*- coding: utf-8 -*-
"""回归测试：VList 其余方法的校验/静默错值（BUG-509）。

修复前（全部裸错或无提示）：

    v.filter_not(123)        # → [1, 2, 3, 4]  **静默返回全部元素**！
                             #   （VList 继承 Seq 的惰性 ops 版 filter_not，
                             #    对已物化的 _data 不生效，等于没过滤）
    v.wherenot(123)          # → TypeError: 'int' object is not callable
    v.filterfalse(123)       # → 同上
    v.reduce_by(123, f)      # → 同上（key_func 裸错）
    v.reduce_by(f, 123)      # → 同上（reduce_func 裸错）
    v.accummap(123)          # → 同上
    v.do(123)                # → 同上（VoolsBase.do 对 VList/Seq/Table 共享）
    VList.dotproduct([1,2], [3])   # → 3  **静默算出部分点积**！
    VList.dotproduct(None, [1])    # → TypeError: 'NoneType' object is not iterable
"""

import pytest

from vools.data.vlist import VList


@pytest.fixture()
def vlist():
    return VList([1, 2, 3, 4])


class TestFilterNotActuallyFilters:
    def test_callable_filters(self, vlist):
        assert list(vlist.filter_not(lambda x: x > 2)) == [1, 2]

    def test_expression_string_filters(self, vlist):
        assert list(vlist.filter_not("x > 2")) == [1, 2]

    def test_non_callable_rejected(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.filter_not(123)
        assert "filter_not" in str(ei.value)

    def test_matches_wherenot(self, vlist):
        assert list(vlist.filter_not(lambda x: x > 2)) == list(vlist.wherenot(lambda x: x > 2))


class TestValidationConsistency:
    @pytest.mark.parametrize("method", ["filterfalse", "wherenot"])
    def test_filter_family(self, vlist, method):
        with pytest.raises(TypeError) as ei:
            getattr(vlist, method)(123)
        assert method in str(ei.value)

    def test_reduce_by_key_func(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.reduce_by(123, lambda a, b: a + b)
        assert "key_func" in str(ei.value)

    def test_reduce_by_reduce_func(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.reduce_by(lambda x: x % 2, 123)
        assert "reduce_func" in str(ei.value)

    def test_accummap_func(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.accummap(123)
        assert "accummap" in str(ei.value)

    @pytest.mark.parametrize("kwargs", [
        {"f": 123},
        {"f": lambda x: x, "pre_f": 123},
        {"f": lambda x: x, "sub_f": 123},
    ])
    def test_do_callables(self, vlist, kwargs):
        with pytest.raises(TypeError) as ei:
            vlist.do(**kwargs)
        assert "do()" in str(ei.value)


class TestDotProductValidation:
    def test_length_mismatch_rejected(self):
        with pytest.raises(ValueError) as ei:
            VList.dotproduct([1, 2], [3])
        assert "长度" in str(ei.value)

    def test_non_sequence_rejected(self):
        with pytest.raises(TypeError):
            VList.dotproduct(None, [1])

    def test_normal(self):
        assert VList.dotproduct([1, 2], [3, 4]) == 11

    def test_empty(self):
        assert VList.dotproduct([], []) == 0


class TestValidPathsUnchanged:
    def test_reduce_by(self, vlist):
        assert vlist.reduce_by(lambda x: x % 2, lambda a, b: a + b) == {1: 4, 0: 6}

    def test_do_returns_self(self, vlist):
        assert vlist.do(lambda lst: lst) is vlist

    def test_filterfalse_expression(self, vlist):
        assert list(vlist.filterfalse("x > 2")) == [1, 2]
