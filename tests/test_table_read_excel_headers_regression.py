# -*- coding: utf-8 -*-
"""回归测试：Table.read_excel 的非字符串表头列检测（BUG-345）。

`vools.xl` 是可选依赖（未安装时 `read_excel` 抛清晰的 ImportError），
本测试用**注入的 fake `vools.xl` 模块**覆盖真实的 reading 逻辑：
Book 上下文管理器 + Sheet（first_row/first_col/last_row/last_col、
cell_type、read_str、read_matrix）。

BUG：表头列检测只接受 `cell_type == 2`（STRING），
    表头为数字/日期（如年份列 2024、2025）时 `last_col` 不推进 →
    **末列被静默丢弃**：

        [trial], [2024, 2025], [1, 2], [3, 4]
        修复前 -> cols=1, columns=['2024'], data=[[1], [3]]
        修复后 -> cols=2, columns=['2024', '2025'], data=[[1, 2], [3, 4]]

修复：非空（cell_type != 0）的表头单元格都算有效列；字符串仍按文本判空，
保留「尾部空白列裁剪」的行为。
"""

import os
import sys
import types

import pytest

from vools.data.table import Table

_CT_EMPTY, _CT_NUMBER, _CT_STRING = 0, 1, 2


class _FakeSheet:
    def __init__(self, matrix):
        self._m = matrix
        self.first_row = 0
        self.last_row = len(matrix) - 1
        self.first_col = 0
        self.last_col = (max((len(r) for r in matrix), default=0) - 1) if matrix else -1

    def cell_type(self, r, c):
        if r < 0 or c < 0 or r >= len(self._m) or c >= len(self._m[r]):
            return _CT_EMPTY
        v = self._m[r][c]
        if v is None:
            return _CT_EMPTY
        if isinstance(v, str):
            return _CT_STRING
        if isinstance(v, bool):
            return 3
        if isinstance(v, (int, float)):
            return _CT_NUMBER
        return 3

    def read_str(self, r, c):
        try:
            return str(self._m[r][c])
        except Exception:
            return ''

    def read_matrix(self, rows, cols, r0, c0):
        return [
            [self._m[r][c] if c < len(self._m[r]) else None for c in range(c0, c0 + cols)]
            for r in range(r0, min(r0 + rows, len(self._m)))
        ]


class _FakeBook:
    error_message = 'fake error'
    matrix = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def load(self, filename):
        return True

    def get_sheet(self, index):
        return _FakeSheet(type(self).matrix)


@pytest.fixture()
def excel_env(tmp_path, monkeypatch):
    """注入 fake vools.xl，返回「设置表格矩阵并读取」的辅助函数。"""
    mod = types.ModuleType('vools.xl')
    mod.Book = _FakeBook
    monkeypatch.setitem(sys.modules, 'vools.xl', mod)

    path = tmp_path / 'dummy.xlsx'
    path.write_bytes(b'fake')

    def read(matrix, **kwargs):
        _FakeBook.matrix = matrix
        return Table.read_excel(str(path), **kwargs)

    return read


TRIAL = ['trial banner']       # vools.xl 约定：第 0 行是 trial 横幅


class TestStringHeaders:
    def test_basic(self, excel_env):
        t = excel_env([TRIAL, ['id', 'name'], [1, 'a'], [2, 'b']])
        assert t._columns == ['id', 'name']
        assert t._data == [[1, 'a'], [2, 'b']]

    def test_trailing_blank_column_trimmed(self, excel_env):
        t = excel_env([TRIAL, ['id', 'name', ''], [1, 'a', None]])
        assert t._columns == ['id', 'name']
        assert t._data == [[1, 'a']]

    def test_header_only(self, excel_env):
        t = excel_env([TRIAL, ['id', 'name']])
        assert t._columns == ['id', 'name']
        assert t._data == []


class TestNumericHeaders:
    """BUG-345 核心：非字符串表头不能丢列。"""

    def test_all_numeric_headers(self, excel_env):
        t = excel_env([TRIAL, [2024, 2025], [1, 2], [3, 4]])
        # 修复前：columns=['2024']，data=[[1],[3]]（末列被丢弃）
        assert t._columns == ['2024', '2025']
        assert t._data == [[1, 2], [3, 4]]

    def test_trailing_numeric_header_kept(self, excel_env):
        t = excel_env([TRIAL, ['store', 'code', 2024], ['s1', 'c1', 100]])
        assert len(t._columns) == 3
        assert t._data == [['s1', 'c1', 100]]

    def test_mixed_headers(self, excel_env):
        t = excel_env([TRIAL, ['id', 2024, 'name'], [1, 2, 'a']])
        assert t._columns == ['id', '2024', 'name']
        assert t._data == [[1, 2, 'a']]

    def test_boolean_header(self, excel_env):
        t = excel_env([TRIAL, ['flag_a', True], [1, 2]])
        assert len(t._columns) == 2
        assert t._data == [[1, 2]]


class TestOtherModes:
    def test_header_false(self, excel_env):
        t = excel_env([TRIAL, ['id', 'name'], [1, 'a']], header=False)
        assert t._data[0] == ['id', 'name']
        assert len(t._columns) == 2

    def test_empty_sheet(self, excel_env):
        t = excel_env([])
        assert t._rows if hasattr(t, '_rows') else True
        assert t._data == []

    def test_missing_file(self, tmp_path, monkeypatch):
        mod = types.ModuleType('vools.xl')
        mod.Book = _FakeBook
        monkeypatch.setitem(sys.modules, 'vools.xl', mod)
        with pytest.raises(FileNotFoundError):
            Table.read_excel(str(tmp_path / 'nope.xlsx'))