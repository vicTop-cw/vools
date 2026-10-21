# -*- coding: utf-8 -*-
"""回归测试：Qax 访问/写入类 1-based API 越界校验（BUG-248）。

BUG-246/247 同族（1-based API 裸减 1 无校验，0/负数经负索引命中最后行列）：
- `GetRow(0)` → base `row(-1)` → **返回最后一行**（静默错行）
- `GetCol(0)` → base `column(-1)` → **返回最后一列**（静默错列）
- `SetCell(0, c, v)` / `SetCell2(name, 0, v)` → base `set_cell(-1, ...)`
  → **静默改写最后一行**（数据损坏）
- `GetCell(0, ...)` / `GetCell2(name, 0)` → base get_cell 的 `row_index < 0`
  守卫 → 静默返回 None

修复：六个方法复用 `_check_1based`（行 1..行数、列 1..列数 → IndexError）；
列名字符串路径与 base 语义不变。
"""

import pytest

from vools.data.qax import Qax


def _mk():
    return Qax([[1, 'a', 10], [2, 'b', 20], [3, 'c', 30]],
               columns=['id', 'name', 'v'])


class TestGetRowBounds:
    @pytest.mark.parametrize("bad", [0, -1, 4, 99])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(IndexError, match="行号必须在 1..3"):
            _mk().GetRow(bad)

    def test_valid(self):
        assert _mk().GetRow(1)['id'] == 1
        assert _mk().GetRow(3)['id'] == 3


class TestGetColBounds:
    @pytest.mark.parametrize("bad", [0, -1, 4])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(IndexError, match="列号必须在 1..3"):
            _mk().GetCol(bad)

    def test_valid_int(self):
        assert _mk().GetCol(2) == ['a', 'b', 'c']

    def test_valid_name(self):
        assert _mk().GetCol('v') == [10, 20, 30]


class TestSetCellBounds:
    def test_row_zero_does_not_corrupt_last_row(self):
        # 修复前 SetCell(0, 1, 'X') 静默改写最后一行的第一列
        with pytest.raises(IndexError):
            _mk().SetCell(0, 1, 'X')

    def test_col_zero_raises(self):
        with pytest.raises(IndexError):
            _mk().SetCell(1, 0, 'X')

    def test_row_beyond_raises(self):
        with pytest.raises(IndexError):
            _mk().SetCell(4, 1, 'X')

    def test_valid(self):
        t = _mk()
        t.SetCell(1, 2, 26)
        assert t.GetCell(1, 2) == 26
        assert t.GetRow(3)['v'] == 30      # 未波及其它行


class TestSetCell2Bounds:
    def test_row_zero_raises(self):
        with pytest.raises(IndexError):
            _mk().SetCell2('name', 0, 'Y')

    def test_row_beyond_raises(self):
        with pytest.raises(IndexError):
            _mk().SetCell2('name', 4, 'Y')

    def test_valid(self):
        t = _mk()
        t.SetCell2('name', 1, 'Y')
        assert t.GetCell(1, 2) == 'Y'


class TestGetCellBounds:
    @pytest.mark.parametrize("row,col", [(0, 1), (1, 0), (-1, 1), (4, 1), (1, 4)])
    def test_out_of_range_raises(self, row, col):
        # 修复前静默返回 None
        with pytest.raises(IndexError):
            _mk().GetCell(row, col)

    def test_valid(self):
        assert _mk().GetCell(1, 1) == 1
        assert _mk().GetCell(3, 3) == 30


class TestGetCell2Bounds:
    def test_row_zero_raises(self):
        with pytest.raises(IndexError):
            _mk().GetCell2('name', 0)

    def test_valid(self):
        assert _mk().GetCell2('name', 2) == 'b'