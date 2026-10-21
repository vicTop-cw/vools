# -*- coding: utf-8 -*-
"""回归测试：Qax 1-based 行列 API 越界校验与行宽校验（BUG-246）。

原实现直接把 1-based 位置减 1 交给 Python 列表操作，0/负数被负索引语义
静默解释为「从末尾数」：
- `InsertRow(0)`/`InsertCol(0)` → 插入到**倒数位置**（静默错位）；
- `DelCol(0)` → 静默删掉**最后一列**（应报错）；
- `DelRow(0/越界)` → 静默 no-op；`DelCol(5)` 却 IndexError（不一致）；
- `NewRow`/`InsertRow` 列表数据宽于列数 → 行宽 > 列数，破坏表格矩形性。

修复：Qax 层 `_check_1based` 校验（InsertRow/InsertCol 允许 1..n+1，
DelRow/DelCol 允许 1..n，越界抛 IndexError），`_fit_row_data` 对超宽行抛
ValueError（窄行仍补 None）。表名/列名（str）路径不变。
"""

import pytest

from vools.data.qax import Qax


def _mk():
    return Qax([[1, 'a', 10], [2, 'b', 20], [3, 'c', 30]],
               columns=['id', 'name', 'v'])


class TestInsertRowBounds:
    def test_zero_raises(self):
        with pytest.raises(IndexError, match="行号必须在 1..4"):
            _mk().InsertRow(0, ['X', 'Y', 'Z'])

    def test_negative_raises(self):
        with pytest.raises(IndexError):
            _mk().InsertRow(-1, ['X', 'Y', 'Z'])

    def test_beyond_end_raises(self):
        with pytest.raises(IndexError):
            _mk().InsertRow(5, ['X', 'Y', 'Z'])

    def test_first_and_append_positions(self):
        t = _mk()
        t.InsertRow(1, ['X', 'Y', 'Z'])
        assert t.QAXRows() == 4 and t.GetRow(1)['id'] == 'X'
        t.InsertRow(5, ['E', 'F', 'G'])          # len+1 = 末尾
        assert t.GetRow(5)['id'] == 'E'


class TestInsertColBounds:
    def test_zero_raises(self):
        with pytest.raises(IndexError, match="列号必须在 1..4"):
            _mk().InsertCol(0, 'nc')

    def test_negative_raises(self):
        with pytest.raises(IndexError):
            _mk().InsertCol(-1, 'nc')

    def test_beyond_end_raises(self):
        with pytest.raises(IndexError):
            _mk().InsertCol(5, 'nc')

    def test_first_and_append(self):
        t = _mk()
        t.InsertCol(1, 'nc', 0)
        assert t.QAXColNames()[0] == 'nc'
        t.InsertCol(5, 'tail', 0)                # len+1 = 末尾
        assert t.QAXColNames()[-1] == 'tail'


class TestDelBounds:
    def test_delcol_zero_does_not_delete_last(self):
        # 修复前 DelCol(0) 静默删掉最后一列
        with pytest.raises(IndexError):
            _mk().DelCol(0)

    def test_delcol_negative_raises(self):
        with pytest.raises(IndexError):
            _mk().DelCol(-1)

    def test_delcol_beyond_raises(self):
        with pytest.raises(IndexError):
            _mk().DelCol(5)

    def test_delrow_out_of_range_raises(self):
        for bad in (0, -1, 4, 99):
            with pytest.raises(IndexError):
                _mk().DelRow(bad)

    def test_valid_deletes_unchanged(self):
        t = _mk()
        t.DelRow(1)
        assert t.QAXRows() == 2
        t.DelCol(1)
        assert t.QAXColNames() == ['name', 'v']

    def test_delcol_by_name_unchanged(self):
        t = _mk()
        t.DelCol('name')
        assert t.QAXColNames() == ['id', 'v']


class TestRowWidth:
    def test_newrow_too_wide_raises(self):
        with pytest.raises(ValueError, match="超过列数 3"):
            _mk().NewRow(['a', 'b', 'c', 'd'])

    def test_insertrow_too_wide_raises(self):
        with pytest.raises(ValueError):
            _mk().InsertRow(1, ['a', 'b', 'c', 'd'])

    def test_short_list_padded(self):
        t = _mk()
        t.NewRow(['x'])
        assert t.GetRow(4) == {'id': 'x', 'name': None, 'v': None}
        assert all(len(r) == 3 for r in t._data)   # 矩形性保持