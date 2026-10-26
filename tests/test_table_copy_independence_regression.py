# -*- coding: utf-8 -*-
"""回归测试：Table.copy() 是纯别名，改动副本静默破坏原表（BUG-504）。

``VoolsBase.copy`` 用 ``copy.copy(self)``（BUG-415 引入，修的是构造式复制的错误）。
对 Table 这种**可变容器**，浅拷贝意味着副本与原表共享同一个 ``_data`` 列表、
每一行 list 与 ``_columns``：

    u = t.copy()
    u.add_col('x')      # ***原表*** 也多出一列 x
    u.del_row(0)        # 原表少一行
    u.replace(1, 1, 99) # 原表数据被改

修复：Table 覆写 ``copy()``，复制内部容器结构（行 list、列名列表、行索引），
单元格对象仍按引用共享（值语义足够）。

另：``add_col`` 的 ``col_name`` 校验——``add_col(123)`` 曾创建整数列名、
``add_col('')`` 创建空名列。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def table():
    return Table([["A", 1], ["B", 2]], columns=["k", "v"])


class TestCopyIndependence:
    def test_add_col_does_not_touch_original(self, table):
        clone = table.copy()
        clone.add_col("x")
        assert table.columns() == ["k", "v"]
        assert clone.columns() == ["k", "v", "x"]

    def test_del_row_does_not_touch_original(self, table):
        clone = table.copy()
        clone.del_row(0)
        assert len(table._data) == 2
        assert len(clone._data) == 1

    def test_replace_does_not_touch_original(self, table):
        clone = table.copy()
        clone.replace(1, 1, 99)
        assert table._data == [["A", 1], ["B", 2]]
        assert clone._data == [["A", 99], ["B", 2]]

    def test_internal_containers_not_shared(self, table):
        clone = table.copy()
        assert clone._data is not table._data
        assert clone._data[0] is not table._data[0]
        assert clone._columns is not table._columns

    def test_clone_equals_original_initially(self, table):
        clone = table.copy()
        assert clone._data == table._data
        assert clone.columns() == table.columns()

    def test_chained_ops_on_clone(self, table):
        result = table.copy().add_col("x").sort("v")
        assert result._data == [["A", 1, None], ["B", 2, None]]
        assert table.columns() == ["k", "v"]
        assert table._data == [["A", 1], ["B", 2]]

    def test_cell_objects_still_shared_by_reference(self):
        shared = [1, 2]
        t = Table([[shared]], columns=["v"])
        clone = t.copy()
        # 值语义：单元格对象本身不深拷贝（Table 不做 deepcopy）
        assert clone._data[0][0] is shared


class TestAddColValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, None, ["x"]])
    def test_non_str_col_name(self, table, bad):
        with pytest.raises(TypeError) as ei:
            table.add_col(bad)
        assert "col_name" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_empty_col_name(self, table, bad):
        with pytest.raises(ValueError) as ei:
            table.add_col(bad)
        assert "col_name" in str(ei.value)

    def test_duplicate_name_still_rejected(self, table):
        with pytest.raises(ValueError):
            table.add_col("k")

    def test_valid_add(self, table):
        table.add_col("x", 0)
        assert table._data == [["A", 1, 0], ["B", 2, 0]]


class TestOtherTableOpsUnchanged:
    def test_del_col(self, table):
        table.del_col("v")
        assert table.columns() == ["k"]
        assert table._data == [["A"], ["B"]]

    def test_del_row_bounds(self, table):
        with pytest.raises(IndexError):
            table.del_row(99)
        with pytest.raises(IndexError):
            table.del_row(-1)

    def test_replace_bounds(self, table):
        with pytest.raises(IndexError):
            table.replace(99, 1, 2)
