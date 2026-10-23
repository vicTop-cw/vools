# -*- coding: utf-8 -*-
"""回归测试：Table 写操作的行列校验与矩形不变量（BUG-377）。

`set_cell` / `set_cell2` / `del_row` 的三个实测缺陷：

1. **负索引未校验**：`set_cell(-1, 0, v)` 静默写入**最后一行**——与
   `del_col` / `_get_col_index` 明确拒绝负索引（BUG-253）的口径不一致；
2. **按 int 列索引扩容只加宽当前行**：`set_cell(0, 9, v)` 把第 0 行补到 10 列，
   其它行仍是 2 列、`_columns` 不变 → **锯齿行**（行宽 != 列数），后续
   `row()/to_file/zip` 全部错乱；
3. **`del_row` 越界/负值静默无操作**（`del_col` 早已抛错）。

修复后：
- 负索引 / 非 int 索引 → IndexError / TypeError；
- 越界写入仍**自动扩容**（表格语义），但按「整表加宽 + 补 `col_N` 列名」处理，
  保证每行宽度 == 列数；
- `del_row` 越界 → IndexError；
- 按列名写入未知列仍自动建列（既有语义，已写入 docstring）。
"""

import pytest

from vools.data.table import Table


def _fresh():
    return Table([[1, 'a'], [2, 'b']], columns=['id', 'name'], name='T')


class TestNegativeIndexRejected:
    def test_set_cell_negative_row(self):
        # 修复前：静默写入最后一行
        with pytest.raises(IndexError):
            _fresh().set_cell(-1, 0, 9)

    def test_set_cell_negative_col(self):
        with pytest.raises(IndexError):
            _fresh().set_cell(0, -1, 9)

    def test_set_cell2_negative_row(self):
        with pytest.raises(IndexError):
            _fresh().set_cell2(-1, 'name', 'Z')

    @pytest.mark.parametrize('bad', ['0', None, 1.5, True])
    def test_set_cell_bad_types(self, bad):
        with pytest.raises(TypeError):
            _fresh().set_cell(bad, 0, 9)


class TestAutoGrowKeepsRectangle:
    def test_grow_rows(self):
        t = _fresh()
        t.set_cell(5, 0, 9)
        assert t.rows() == 6
        assert all(len(r) == len(t._columns) for r in t._data)
        assert t.get_cell2(5, 'id') == 9

    def test_grow_columns_int_index(self):
        t = _fresh()
        t.set_cell(0, 4, 7)
        # 修复前：只有第 0 行被加宽（锯齿）
        assert all(len(r) == len(t._columns) for r in t._data)
        assert len(t._columns) == 5
        assert t._columns[2:] == ['col_2', 'col_3', 'col_4']
        assert t.get_cell(0, 4) == 7
        assert t.get_cell(1, 4) is None

    def test_grow_by_column_name_creates_column(self):
        t = _fresh()
        t.set_cell2(0, 'extra', 'v')
        assert t._columns == ['id', 'name', 'extra']
        assert all(len(r) == 3 for r in t._data)
        assert t.get_cell2(0, 'extra') == 'v'
        assert t.get_cell2(1, 'extra') is None

    def test_normal_write_unchanged(self):
        t = _fresh()
        t.set_cell(0, 0, 9)
        t.set_cell2(1, 'name', 'Z')
        assert t._data == [[9, 'a'], [2, 'Z']]
        assert t._columns == ['id', 'name']


class TestDelRowValidated:
    def test_valid(self):
        t = _fresh()
        t.del_row(0)
        assert t._data == [[2, 'b']]

    @pytest.mark.parametrize('idx', [-1, 2, 99])
    def test_out_of_range_rejected(self, idx):
        # 修复前：静默无操作
        with pytest.raises(IndexError):
            _fresh().del_row(idx)

    @pytest.mark.parametrize('bad', ['0', None, 1.5, True])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError):
            _fresh().del_row(bad)


class TestDelColStillValidated:
    def test_negative(self):
        with pytest.raises(IndexError):
            _fresh().del_col(-1)

    def test_unknown_name(self):
        with pytest.raises(KeyError):
            _fresh().del_col('nope')

    def test_valid(self):
        t = _fresh()
        t.del_col('name')
        assert t._data == [[1], [2]]
        assert t._columns == ['id']