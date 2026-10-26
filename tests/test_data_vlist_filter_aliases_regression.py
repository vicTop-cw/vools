# -*- coding: utf-8 -*-
"""回归测试：VList 过滤别名静默不过滤 + 委托方法报错归属错误（BUG-510）。

## 静默不过滤（与 BUG-509 的 filter_not 同源）

``Seq`` 把 ``filter_not`` / ``filter_false`` / ``filternot`` 三个名字都绑定到
**惰性 ops 版** ``filterfalse``；``VList`` 上一轮只覆盖了 ``filter_not``：

    VList([1,2,3,4]).filter_false(lambda x: x > 2)   # → [1,2,3,4]（一个都没过滤）
    VList([1,2,3,4]).filternot(123)                  # → [1,2,3,4]（不报错、不过滤）

## 报错归属错误

``select`` / ``where`` / ``foreach`` 直接委托 map/filter，错误信息写成
``VList.map()`` / ``VList.filter()`` —— 调用 foreach 的人看不出是哪个方法；
``mapmap(123)`` 则抛误导性的 "All items of self must be a Iterable item"。

修复：覆盖 ``filter_false`` / ``filternot``（走已校验的 ``filterfalse``）；
``select`` / ``where`` / ``foreach`` / ``mapmap`` 入口用自己的方法名校验。
"""

import pytest

from vools.data.vlist import VList


@pytest.fixture()
def vlist():
    return VList([1, 2, 3, 4])


class TestFilterAliasesActuallyFilter:
    @pytest.mark.parametrize("method", ["filter_not", "filter_false", "filternot"])
    def test_callable(self, vlist, method):
        assert list(getattr(vlist, method)(lambda x: x > 2)) == [1, 2]

    @pytest.mark.parametrize("method", ["filter_not", "filter_false", "filternot"])
    def test_expression_string(self, vlist, method):
        assert list(getattr(vlist, method)("x > 2")) == [1, 2]

    @pytest.mark.parametrize("method", ["filter_not", "filter_false", "filternot"])
    def test_non_callable_rejected(self, vlist, method):
        with pytest.raises(TypeError) as ei:
            getattr(vlist, method)(123)
        assert method in str(ei.value)

    def test_all_three_consistent(self, vlist):
        results = {
            name: list(getattr(vlist, name)(lambda x: x > 2))
            for name in ("filter_not", "filter_false", "filternot")
        }
        assert len(set(map(tuple, results.values()))) == 1


class TestDelegatingMethodsErrorAttribution:
    def test_select(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.select(123)
        assert "VList.select()" in str(ei.value)

    def test_where(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.where(123)
        assert "VList.where()" in str(ei.value)

    def test_foreach_func(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.foreach(123)
        assert "VList.foreach()" in str(ei.value)

    def test_foreach_filter_func(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.foreach(lambda x: x, 123)
        assert "filter_func" in str(ei.value)
        assert "VList.foreach()" in str(ei.value)

    def test_mapmap_inner(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.mapmap(123)
        assert "inner_func" in str(ei.value)

    def test_mapmap_outer(self):
        nested = VList([[1], [2]])
        with pytest.raises(TypeError) as ei:
            nested.mapmap(lambda x: x, 123)
        assert "outer_func" in str(ei.value)


class TestValidPathsUnchanged:
    def test_select_maps(self, vlist):
        assert list(vlist.select(lambda x: x * 2)) == [2, 4, 6, 8]

    def test_where_filters(self, vlist):
        assert list(vlist.where(lambda x: x > 2)) == [3, 4]

    def test_foreach_returns_vlist(self, vlist):
        assert isinstance(vlist.foreach(lambda x: x), VList)

    def test_foreach_only_filter(self, vlist):
        assert list(vlist.foreach(None, lambda x: x > 2)) == [3, 4]

    def test_mapmap_nested(self):
        result = VList([[1, 2], [3]]).mapmap(lambda x: x * 10)
        assert [list(inner) for inner in result] == [[10, 20], [30]]
