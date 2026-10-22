# -*- coding: utf-8 -*-
"""回归测试：get_cell / get_cell2 的 None 返回值不被 @rself 吞掉（BUG-313）。

`Table` 被 `@rself` 装饰，其 `_wrap_return_value(..., wrap_none=True)` 会把
**None 返回值兜底成 self**。而 `get_cell(row, col, default_value=None,
null_value=None)` 的文档契约是「越界/空值返回 default_value」——默认即 None。
于是：

    t.get_cell(99, 0)      -> **整个 Table 对象**（is t）而非 None
    t.get_cell(0, 99)      -> Table
    t.get_cell2('nope', 0) -> Table

调用方 `v is None` 恒 False，后续算术/长度判断静默错值。

同文件 BUG-252 已为 `max/min` 建立 `_rself_exclude` 机制，本修复把
`get_cell` / `get_cell2` 一并纳入。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def t():
    return Table([[1, 'a'], [2, 'b']], columns=['id', 'name'])


class TestGetCellReturnsNone:
    def test_row_out_of_range(self, t):
        # 修复前：返回 t 本身（Table 对象）
        assert t.get_cell(99, 0) is None

    def test_negative_row(self, t):
        assert t.get_cell(-1, 0) is None

    def test_col_out_of_range(self, t):
        assert t.get_cell(0, 99) is None

    def test_unknown_column_name(self, t):
        assert t.get_cell2('nope', 0) is None

    def test_null_cell_returns_none(self):
        t = Table([[1, None]], columns=['id', 'v'])
        assert t.get_cell(0, 1) is None

    def test_explicit_default_still_returned(self, t):
        assert t.get_cell(99, 0, 'D') == 'D'
        assert t.get_cell2('nope', 0, default_value=-1) == -1


class TestNormalPathsUnchanged:
    def test_valid_cell(self, t):
        assert t.get_cell(0, 0) == 1
        assert t.get_cell(1, 1) == 'b'

    def test_valid_name(self, t):
        assert t.get_cell2(0, 'name') == 'a'

    def test_max_min_still_none_on_empty(self, t):
        empty = t.filter(lambda r: False)
        assert empty.max('id') is None
        assert empty.min('id') is None

    def test_chaining_still_returns_self(self, t):
        assert t.set_name('x') is t
        assert t.clear() is t