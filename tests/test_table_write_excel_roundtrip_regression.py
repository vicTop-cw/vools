# -*- coding: utf-8 -*-
"""回归测试：Table.write_excel 与读写往返一致性（配合 BUG-345 的可测化改造）。

`vools.xl` 是可选依赖，本测试注入 fake `vools.xl`（Book/Sheet，记录
write_matrix 并可回放 read_* 接口），覆盖真实的写入与往返路径：

- 表头写在 **row 1**、数据从 row 2 开始（row 0 留作 trial 横幅，与 read_excel 约定一致）；
- 往返后列名/数据保持（字符串、数字列名、中文、None 值、空表）；
- 全空行在读取侧被过滤。
"""

import sys
import types

import pytest

from vools.data.table import Table


class _RecordSheet:
    """记录写入内容，并实现读取侧接口。"""

    first_row = 0
    first_col = 0

    def __init__(self):
        self.rows = {}

    def write_matrix(self, matrix, start_row=0, start_col=0):
        for i, row in enumerate(matrix):
            cur = self.rows.setdefault(start_row + i, {})
            for j, v in enumerate(row):
                cur[start_col + j] = v

    def matrix(self):
        if not self.rows:
            return []
        max_r = max(self.rows)
        max_c = max(max(d) for d in self.rows.values())
        return [[self.rows.get(r, {}).get(c) for c in range(max_c + 1)]
                for r in range(max_r + 1)]

    @property
    def last_row(self):
        return len(self.matrix()) - 1

    @property
    def last_col(self):
        m = self.matrix()
        return (max(len(r) for r in m) - 1) if m else -1

    def cell_type(self, r, c):
        m = self.matrix()
        if r >= len(m) or c >= len(m[r]):
            return 0
        v = m[r][c]
        if v is None:
            return 0
        if isinstance(v, str):
            return 2
        if isinstance(v, (int, float)):
            return 1
        return 3

    def read_str(self, r, c):
        m = self.matrix()
        try:
            return str(m[r][c])
        except Exception:
            return ''

    def read_matrix(self, rows, cols, r0, c0):
        m = self.matrix()
        return [[m[r][c] if r < len(m) and c < len(m[r]) else None
                 for c in range(c0, c0 + cols)]
                for r in range(r0, min(r0 + rows, len(m)))]


class _FakeBook:
    error_message = 'fake'

    def __init__(self, sheet):
        self._sheet = sheet

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add_sheet(self, name):
        return self._sheet

    def save(self, filename):
        # read_excel 有 os.path.exists 前置校验：真实落一个占位文件
        with open(filename, 'wb') as fh:
            fh.write(b'fake-xlsx')
        return True

    def load(self, filename):
        return True

    def get_sheet(self, index):
        return self._sheet


@pytest.fixture()
def excel(tmp_path, monkeypatch):
    sheet = _RecordSheet()
    mod = types.ModuleType('vools.xl')
    mod.Book = lambda *a, **k: _FakeBook(sheet)
    monkeypatch.setitem(sys.modules, 'vools.xl', mod)
    path = tmp_path / 'out.xlsx'
    return sheet, path


class TestWriteLayout:
    def test_header_at_row_1_data_from_row_2(self, excel):
        sheet, path = excel
        t = Table([[1, 'a'], [2, 'b']], columns=['id', 'name'])
        assert t.write_excel(str(path)) is True

        m = sheet.matrix()
        assert m[0] == [None, None]        # row 0 留给 trial 横幅
        assert m[1] == ['id', 'name']      # 表头
        assert m[2] == [1, 'a']            # 数据
        assert m[3] == [2, 'b']


class TestRoundTrip:
    def test_basic(self, excel):
        _, path = excel
        t = Table([[1, 'a'], [2, 'b']], columns=['id', 'name'])
        t.write_excel(str(path))
        back = Table.read_excel(str(path))
        assert back._columns == ['id', 'name']
        assert back._data == [[1, 'a'], [2, 'b']]

    def test_numeric_column_names(self, excel):
        _, path = excel
        t = Table([[1, 2], [3, 4]], columns=[2024, 2025])
        t.write_excel(str(path))
        back = Table.read_excel(str(path))
        # 数字列名读回为字符串（单元格内容类型），列与数据都不能丢
        assert back._columns == ['2024', '2025']
        assert back._data == [[1, 2], [3, 4]]

    def test_chinese_and_none(self, excel):
        _, path = excel
        t = Table([[1, None], ['中文', 'x']], columns=['id', '名称'])
        t.write_excel(str(path))
        back = Table.read_excel(str(path))
        assert back._columns == ['id', '名称']
        assert back._data == [[1, None], ['中文', 'x']]

    def test_empty_table(self, excel):
        _, path = excel
        Table([], columns=['a', 'b']).write_excel(str(path))
        back = Table.read_excel(str(path))
        assert back._columns == ['a', 'b']
        assert back._data == []

    def test_blank_rows_filtered_on_read(self, excel):
        _, path = excel
        t = Table([[1, 'a'], [None, None], [2, 'b']], columns=['id', 'name'])
        t.write_excel(str(path))
        back = Table.read_excel(str(path))
        assert back._data == [[1, 'a'], [2, 'b']]


class TestMissingDependency:
    def test_import_error_when_xl_absent(self, monkeypatch, tmp_path):
        monkeypatch.setitem(sys.modules, 'vools.xl', None)
        t = Table([[1]], columns=['a'])
        with pytest.raises(ImportError) as ei:
            t.write_excel(str(tmp_path / 'x.xlsx'))
        assert 'vools[xl]' in str(ei.value) or 'vools-xl' in str(ei.value)