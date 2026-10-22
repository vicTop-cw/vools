# -*- coding: utf-8 -*-
"""回归测试：@rself 的 None→self 兜底不得吞掉文档化的 None 返回（BUG-314）。

`@rself`（vools/decorators/rself.py）的 `_wrap_return_value(wrap_none=True)`
会把 **None 返回值兜底成 self**，被装饰类可用 `_rself_exclude` 豁免。
BUG-252 为 max/min、BUG-313 为 get_cell/get_cell2 建立过豁免；本修复补齐：

A. `Table.compute(expression, ..., default_value=None)`：
   SUM/AVG/COUNT/MAX/MIN 之外的分支 `return default_value`；SUM/AVG/MAX/MIN
   在列内无 int/float 时也返回 default_value。未豁免时「算不出来」变成
   **返回整个 Table**（实测 5/5 稳定复现）。
B. `VList.map(func=None)`：文档明写「Returns: 映射后的 VList 或 None
   （当 func 为 None 时）」，未豁免时返回 self。
C/D. `Row.map()` / `Column.map()`（func=None）：源码 `return None`，
   未豁免时返回 self。

修复：Table._rself_exclude 增加 'compute'；VList 增加 'map'；
Row / Column 新增 `_rself_exclude = ('map',)`。
"""

import pytest

from vools.data.table import Table
from vools.data.vlist import VList


@pytest.fixture()
def t():
    return Table([[1, 'a'], [2, 'b']], columns=['id', 'name'])


class TestComputeReturnsDefault:
    def test_unmatched_expression(self, t):
        # 修复前：返回整个 Table
        assert t.compute('BOGUS(x)') is None

    def test_all_non_numeric_column(self, t):
        # name 列全是字符串 → nums 为空 → default_value(None)
        assert t.compute('SUM(name)') is None
        assert t.compute('AVG(name)') is None
        assert t.compute('MAX(name)') is None
        assert t.compute('MIN(name)') is None

    def test_explicit_default_value(self, t):
        assert t.compute('BOGUS(x)', default_value=-1) == -1
        assert t.compute('SUM(name)', default_value='N/A') == 'N/A'

    def test_normal_aggregations_unchanged(self, t):
        assert t.compute('SUM(id)') == 3
        assert t.compute('COUNT(id)') == 2
        assert t.compute('MAX(id)') == 2
        assert t.compute('MIN(id)') == 1


class TestMapPrintModeReturnsNone:
    def test_vlist_map_no_func(self):
        vl = VList([1, 2])
        assert vl.map() is None

    def test_vlist_map_with_func_unchanged(self):
        assert list(VList([1, 2]).map(lambda x: x * 2)) == [2, 4]

    def test_row_map_no_func(self, t):
        assert t.get_row(0).map() is None

    def test_column_map_no_func(self, t):
        assert t.get_col('id').map() is None


class TestEarlierExclusionsStillHold:
    def test_max_min_none_on_empty(self, t):
        empty = t.filter(lambda r: False)
        assert empty.max('id') is None
        assert empty.min('id') is None

    def test_get_cell_none(self, t):
        assert t.get_cell(99, 0) is None
        assert t.get_cell2('nope', 0) is None

    def test_vlist_pop_shift_unchanged(self):
        vl = VList([1, 2, 3])
        assert vl.pop() == 3
        assert vl.shift() == 1