# -*- coding: utf-8 -*-
"""回归测试：Table.from_file 的参数校验（BUG-501）。

修复前：

    from_file(p, rows=-1)     # 静默返回空表
    from_file(p, rows='x')    # 抛裸 "'>=' not supported between instances of 'int' and 'str'"
    from_file(p, cols=99)     # 抛裸 "'int' object is not iterable"
    from_file(p, cols=['x'])  # 到切片处才炸（错误看不出是哪个参数）
    from_file(p, types=[..])  # **静默忽略**！文档写"暂未实现"，调用方以为做了类型转换

修复后：rows 必须为非负 int 或 None；cols 必须为 int 索引的可迭代对象；
types 非 None 时显式 NotImplementedError（不再静默无效）。

注意：``cols`` 中**越界但合法**的 int 索引仍按 BUG-354 的既有契约补空串，
本轮不改变该行为。
"""

import os
import tempfile

import pytest

from vools.data.table import Table


@pytest.fixture()
def csv_path():
    tmp = tempfile.mkdtemp(prefix="vt501_")
    path = os.path.join(tmp, "a.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("name,age\nAlice,30\nBob,25\n")
    return path


class TestRowsValidation:
    def test_negative(self, csv_path):
        with pytest.raises(ValueError) as ei:
            Table.from_file(csv_path, rows=-1)
        assert "rows" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", None])
    def test_wrong_type(self, csv_path, bad):
        if bad is None:
            Table.from_file(csv_path, rows=None)      # None 合法
            return
        with pytest.raises(TypeError) as ei:
            Table.from_file(csv_path, rows=bad)
        assert "rows" in str(ei.value)

    def test_bool_rejected(self, csv_path):
        with pytest.raises(TypeError):
            Table.from_file(csv_path, rows=True)

    def test_valid_rows(self, csv_path):
        assert Table.from_file(csv_path, rows=2)._data == [["Alice", "30"]]


class TestColsValidation:
    @pytest.mark.parametrize("bad", [99, "ab", None])
    def test_non_iterable(self, csv_path, bad):
        if bad is None:
            assert Table.from_file(csv_path, cols=None)._data
            return
        with pytest.raises(TypeError) as ei:
            Table.from_file(csv_path, cols=bad)
        assert "cols" in str(ei.value)

    def test_non_int_element(self, csv_path):
        with pytest.raises(TypeError) as ei:
            Table.from_file(csv_path, cols=["x"])
        assert "cols" in str(ei.value)

    def test_valid_list_and_tuple(self, csv_path):
        assert Table.from_file(csv_path, cols=[0])._data == [["Alice"], ["Bob"]]
        assert Table.from_file(csv_path, cols=(1,))._data == [["30"], ["25"]]

    def test_out_of_range_index_padded_empty(self, csv_path):
        """BUG-354 契约：合法的越界 int 索引补空串（本轮不变）。"""
        assert Table.from_file(csv_path, cols=[99])._data == [[""], [""]]


class TestTypesNotSilentlyIgnored:
    def test_types_raises_not_implemented(self, csv_path):
        with pytest.raises(NotImplementedError) as ei:
            Table.from_file(csv_path, types=["str", "int"])
        assert "types" in str(ei.value)

    def test_types_none_allowed(self, csv_path):
        assert Table.from_file(csv_path, types=None)._data == [
            ["Alice", "30"], ["Bob", "25"]]


class TestValidPathsUnchanged:
    def test_plain_read(self, csv_path):
        assert Table.from_file(csv_path)._data == [["Alice", "30"], ["Bob", "25"]]

    def test_bom_stripped(self):
        tmp = tempfile.mkdtemp(prefix="vt501b_")
        path = os.path.join(tmp, "bom.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write("id,v\n1,a\n")
        t = Table.from_file(path)
        assert t._data == [["1", "a"]]

    def test_roundtrip_to_file(self, csv_path):
        tmp = tempfile.mkdtemp(prefix="vt501c_")
        out = os.path.join(tmp, "out.csv")
        t = Table([["x", 1]], columns=["k", "v"])
        assert t.to_file(out) is True
        assert Table.from_file(out)._data == [["x", "1"]]

    def test_missing_file_loud(self):
        with pytest.raises(FileNotFoundError):
            Table.from_file("definitely-not-here-xyz.csv")
