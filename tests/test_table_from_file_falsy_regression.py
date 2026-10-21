# -*- coding: utf-8 -*-
"""回归测试：Table.from_file 的 rows/cols 假值陷阱（BUG-268）。

原实现用真值判断，显式 0/空列表被当成「未提供」：
- `rows=0`（文档：最大行数）falsy → 不 break → **读整个文件**（应 0 行）；
- `cols=[]`（文档：要读取的列索引）行循环已按空选择取空列，但表头过滤处
  仍是 `if columns and cols:` → 表头保留全部列 → 得到 3 列名 + 空数据行的
  **畸形表**（修复后为 0 列选择 = 0 列）。

修复：rows/cols 全部 `is None / is not None` 判断（含表头过滤处）。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def csv_path(tmp_path):
    p = tmp_path / 'data.csv'
    p.write_text('a,b,c\n1,2,3\n4,5,6\n', encoding='utf-8')
    return str(p)


class TestRowsFalsyTrap:
    def test_rows_zero_reads_nothing(self, csv_path):
        # 修复前：rows=0 读全文件
        assert Table.from_file(csv_path, rows=0).rows() == 0

    def test_rows_positive_truncates(self, csv_path):
        assert Table.from_file(csv_path, rows=2).rows() == 2

    def test_rows_none_reads_all(self, csv_path):
        assert Table.from_file(csv_path).rows() == 3


class TestColsFalsyTrap:
    def test_cols_empty_selection_is_empty(self, csv_path):
        # 修复前：3 个列名 + 空数据行的畸形表
        t = Table.from_file(csv_path, cols=[])
        assert len(t.columns()) == 0
        assert all(len(row) == 0 for row in t._data)

    def test_cols_none_all_columns(self, csv_path):
        t = Table.from_file(csv_path, cols=None)
        assert t.columns() == ['a', 'b', 'c']

    def test_cols_specific(self, csv_path):
        t = Table.from_file(csv_path, cols=[0, 2])
        assert t.columns() == ['a', 'c']
        # 注意：from_file 的表头行也作为数据第 0 行保留（既有语义）
        assert t._data[0] == ['a', 'c']
        assert t._data[1] == ['1', '3']