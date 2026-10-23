# -*- coding: utf-8 -*-
"""回归测试：Table.from_file 的 CSV 解析健壮性（BUG-354）。

三个实测缺陷：

1. **UTF-8 BOM 污染首列名**：Excel 导出的 CSV 常带 BOM，按 `utf-8` 读会把
   `\\ufeff` 留在首列名里（`'\\ufeffid'`），随后 `col('id')`/SQL/merge 全部对不上。
   修复：utf-8 系编码统一用 `utf-8-sig` 读取，并防御性去掉首列名的 BOM。
2. **列数与表头不一致的行**：`['1','2']`（表头 3 列）会让 `row(0)` 静默少一列、
   `get_cell(0,'c')` 抛 `TypeError: '<' not supported between 'str' and 'int'`。
   修复：缺列补 `''`；**多出的列显式 ValueError**（避免数据无声丢失）。
3. **`cols` 负索引行为不一致**：`cols=[-1]` 能取到末列，而越界负索引 `[-9]`
   直接 IndexError（正索引越界却是空串）。修复：正负索引统一「缺列返回空串」。
"""

import os

import pytest

from vools.data.table import Table


def _write(tmp_path, content, encoding='utf-8', name='data.csv'):
    p = tmp_path / name
    p.write_text(content, encoding=encoding)
    return str(p)


class TestBomHandling:
    def test_utf8_bom_header_is_clean(self, tmp_path):
        p = _write(tmp_path, 'id,name\n1,a\n', encoding='utf-8-sig')
        t = Table.from_file(p)
        assert t._columns == ['id', 'name']
        assert t.column('id') == ['1']

    def test_utf8_bom_in_data_cell(self, tmp_path):
        p = _write(tmp_path, 'id,name\n1,a\n', encoding='utf-8-sig')
        t = Table.from_file(p)
        assert t._data == [['1', 'a']]

    def test_plain_utf8_still_works(self, tmp_path):
        p = _write(tmp_path, 'id,name\n1,a\n')
        assert Table.from_file(p)._columns == ['id', 'name']


class TestRaggedRows:
    def test_short_row_padded(self, tmp_path):
        p = _write(tmp_path, 'a,b,c\n1,2\n')
        t = Table.from_file(p)
        assert t._data == [['1', '2', '']]
        # 关键：每个访问器都自洽
        assert t.row(0) == {'a': '1', 'b': '2', 'c': ''}
        assert t.column('c') == ['']

    def test_extra_fields_raise(self, tmp_path):
        p = _write(tmp_path, 'a,b\n1,2,3\n')
        with pytest.raises(ValueError) as ei:
            Table.from_file(p)
        msg = str(ei.value)
        assert '3' in msg and '2' in msg  # 字段数 / 表头列数

    def test_rectangular_unchanged(self, tmp_path):
        p = _write(tmp_path, 'a,b\n1,2\n3,4\n')
        t = Table.from_file(p)
        assert t._data == [['1', '2'], ['3', '4']]


class TestColsSelection:
    def test_positive(self, tmp_path):
        p = _write(tmp_path, 'a,b,c\n1,2,3\n')
        t = Table.from_file(p, cols=[0, 2])
        assert (t._columns, t._data) == (['a', 'c'], [['1', '3']])

    def test_negative_index(self, tmp_path):
        p = _write(tmp_path, 'a,b,c\n1,2,3\n')
        t = Table.from_file(p, cols=[-1])
        assert (t._columns, t._data) == (['c'], [['3']])

    def test_negative_out_of_range_returns_empty(self, tmp_path):
        # 修复前：IndexError list index out of range
        p = _write(tmp_path, 'a,b,c\n1,2,3\n')
        t = Table.from_file(p, cols=[-9])
        assert t._data == [['']]

    def test_positive_out_of_range_returns_empty(self, tmp_path):
        p = _write(tmp_path, 'a,b,c\n1,2,3\n')
        t = Table.from_file(p, cols=[0, 9])
        assert (t._columns, t._data) == (['a', 'col_9'], [['1', '']])


class TestLimitsAndEdges:
    def test_rows_limit_counts_header(self, tmp_path):
        p = _write(tmp_path, 'a,b\n1,2\n3,4\n5,6\n')
        assert Table.from_file(p, rows=2)._data == [['1', '2']]

    def test_header_only(self, tmp_path):
        p = _write(tmp_path, 'a,b\n')
        t = Table.from_file(p)
        assert (t._columns, t._data) == (['a', 'b'], [])

    def test_empty_file(self, tmp_path):
        p = _write(tmp_path, '')
        t = Table.from_file(p)
        assert t._data == []

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            Table.from_file('/no/such/file/xyz.csv')

    def test_tab_and_semicolon_delimiters(self, tmp_path):
        p = _write(tmp_path, 'a\tb\n1\t2\n', name='t.tsv')
        assert Table.from_file(p, delimiter='\t')._columns == ['a', 'b']
        p2 = _write(tmp_path, 'a;b\n1;2\n', name='t2.csv')
        assert Table.from_file(p2, delimiter=';')._data == [['1', '2']]

    def test_quoted_field_with_delimiter(self, tmp_path):
        p = _write(tmp_path, 'a,b\n"x,y",2\n')
        assert Table.from_file(p)._data == [['x,y', '2']]

    def test_gbk_encoding(self, tmp_path):
        p = tmp_path / 'gbk.csv'
        p.write_text('编号,名称\n1,中文\n', encoding='gbk')
        t = Table.from_file(str(p), encoding='gbk')
        assert t._columns == ['编号', '名称']