# -*- coding: utf-8 -*-
"""回归测试：from_file 不再把表头行当作数据行（BUG-317）。

`to_file` 写出「表头 + 数据行」，而 `from_file` 原实现把**首行同时当作
列名与数据行**（`if i == 0: columns = ...` 之后仍然 `data.append(row)`），
于是「导出 → 读回」多出一行伪数据：

    t = Table([[1,'a'],[2,'b']], columns=['id','name'])
    t.to_file(p); back = Table.from_file(p)
    # 修复前：back.rows() == 3，back._data[0] == ['id','name']
    # 修复后：back.rows() == 2，列名 = ['id','name']

修复：首行仅用于列名后 `continue`，数据只含真实数据行；`rows` 的计数语义
保持（从文件首行=表头起算，故 `rows=N` 表示「前 N 行含表头」）。
"""

import pytest

from vools.data.table import Table


def _make():
    return Table([[1, 'a,b', '有"引号"'],
                  [2, 'line1\nline2', '中文'],
                  [3, 'plain', '']],
                 columns=['id', 'txt', 'note'])


class TestRoundTrip:
    def test_rows_after_roundtrip(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.csv')
        assert t.to_file(p) is True
        back = Table.from_file(p)
        # 修复前 4 行（表头被当数据）
        assert back.rows() == 3

    def test_columns_and_first_row(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.csv')
        t.to_file(p)
        back = Table.from_file(p)
        assert list(back._columns) == ['id', 'txt', 'note']
        # 首行是真实数据（CSV 无类型信息，故为字符串）
        assert back._data[0] == ['1', 'a,b', '有"引号"']

    def test_special_chars_survive(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.csv')
        t.to_file(p)
        back = Table.from_file(p)
        assert back._data[1] == ['2', 'line1\nline2', '中文']

    def test_custom_delimiter(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.txt')
        t.to_file(p, delimiter='|')
        back = Table.from_file(p, delimiter='|')
        assert back.rows() == 3

    def test_gbk_encoding(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.csv')
        t.to_file(p, encoding='gbk')
        back = Table.from_file(p, encoding='gbk')
        assert back.rows() == 3
        assert back._data[0][2] == '有"引号"'


class TestRowsSemantics:
    def test_rows_zero(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.csv')
        t.to_file(p)
        assert Table.from_file(p, rows=0).rows() == 0

    def test_rows_counts_header_line(self, tmp_path):
        # rows=2 = 文件前 2 行（表头 + 1 数据行）→ data 1 行
        t = _make()
        p = str(tmp_path / 't.csv')
        t.to_file(p)
        assert Table.from_file(p, rows=2).rows() == 1

    def test_rows_none_reads_all(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.csv')
        t.to_file(p)
        assert Table.from_file(p, rows=None).rows() == 3


class TestColumnsFilter:
    def test_cols_filter(self, tmp_path):
        t = _make()
        p = str(tmp_path / 't.csv')
        t.to_file(p)
        sub = Table.from_file(p, cols=[0, 2])
        assert list(sub._columns) == ['id', 'note']
        assert sub._data[0] == ['1', '有"引号"']

    def test_empty_file(self, tmp_path):
        p = str(tmp_path / 'e.csv')
        open(p, 'w').close()
        t = Table.from_file(p)
        assert t.rows() == 0