# -*- coding: utf-8 -*-
"""回归测试：VList.copy 别名 + Table.concat 参数零校验（BUG-505）。

## VList.copy 是纯别名（同 BUG-504 家族）

    v = VList([1, 2, 3]); u = v.copy(); u.add(4)
    # 修复前 → **原表** 也变成 [1, 2, 3, 4]（共享同一个 _data 列表）

## Table.concat 参数零校验

    t.concat('name', [])          # → 把 name 列**清成空串**（静默销毁原列数据）
    t.concat(None, ['tag'])       # → 创建**名为 None 的列**
    t.concat('name', 'tag')       # → 逐字符当列名（KeyError: 't'）
    t.concat('name', None)        # → 裸 "'NoneType' object is not iterable"
"""

import pytest

from vools.data.table import Table
from vools.data.vlist import VList


def fresh_table():
    return Table([["Alice", "a"], ["Bob", "b"]], columns=["name", "tag"])


class TestVListCopyIndependence:
    def test_add_does_not_touch_original(self):
        v = VList([1, 2, 3])
        u = v.copy()
        u.add(4)
        assert list(v) == [1, 2, 3]
        assert list(u) == [1, 2, 3, 4]

    def test_internal_list_not_shared(self):
        v = VList([1, 2, 3])
        u = v.copy()
        assert v._data is not u._data

    def test_clone_content_equal_initially(self):
        v = VList([1, 2, 3])
        assert list(v.copy()) == [1, 2, 3]


class TestConcatValidation:
    def test_empty_concat_array_rejected(self):
        with pytest.raises(ValueError) as ei:
            fresh_table().concat("name", [])
        assert "concat_array" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, "", "   "])
    def test_invalid_to_field(self, bad):
        with pytest.raises(ValueError) as ei:
            fresh_table().concat(bad, ["tag"])
        assert "to_field" in str(ei.value)

    @pytest.mark.parametrize("bad", ["tag", None, 123, {"a": 1}])
    def test_non_sequence_concat_array(self, bad):
        with pytest.raises(TypeError) as ei:
            fresh_table().concat("name", bad)
        assert "concat_array" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None, ""])
    def test_non_str_elements(self, bad):
        with pytest.raises(TypeError) as ei:
            fresh_table().concat("name", [bad])
        assert "concat_array" in str(ei.value)


class TestConcatBehaviourUnchanged:
    def test_new_target_column(self):
        t = fresh_table()
        t.concat("nope", ["tag"])
        assert t.columns() == ["name", "tag", "nope"]
        assert t._data == [["Alice", "a", "a"], ["Bob", "b", "b"]]

    def test_overwrite_existing_column(self):
        t = fresh_table()
        t.concat("tag", ["name"])
        assert t.columns() == ["name", "tag"]
        assert t._data == [["Alice", "Alice"], ["Bob", "Bob"]]

    def test_filter_str_works(self):
        t = fresh_table()
        t.concat("tag", ["name"], filter_str="name == 'Alice'")
        assert t._data == [["Alice", "a"], ["Bob", "b"]]

    def test_multiple_source_columns(self):
        t = Table([["a", "b", "c"]], columns=["x", "y", "z"])
        t.concat("all", ["x", "y", "z"])
        assert t.columns() == ["x", "y", "z", "all"]
        assert t._data[0][3] == "abc"


class TestNoCollateralDamage:
    def test_count_still_works(self):
        """误插补丁曾把校验块塞进 count()——此处防回归。"""
        assert fresh_table().count() == 2
        assert Table([], columns=["a"]).count() == 0

    def test_table_copy_still_independent(self):
        t = fresh_table()
        c = t.copy()
        c.add_col("x")
        assert t.columns() == ["name", "tag"]
