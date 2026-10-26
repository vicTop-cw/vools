# -*- coding: utf-8 -*-
"""回归测试：from_array / ArrayToQax 参数零校验（BUG-506）。

修复前：

    ArrayToQax(123)                 # TypeError: 'int' object is not subscriptable（裸）
    ArrayToQax({'a': 1})            # KeyError: 0（裸）
    ArrayToQax('ab')                # → [['a'], ['b']]  **字符串被当成一维字符数组**，
                                    #   静默产出两行单列表的错表
    ArrayToQax([[1, 2]], columns=['a'])
                                    # → 列名 1 个、数据 2 列：**表头与单元格永久错位**
                                    #   却静默接受
    ArrayToQax([[1, 2]], columns=123)
                                    # → TypeError: 'int' object is not iterable（裸）
    ArrayToQax([[1]], name=123)     # → _name 变成整数 123

修复后：arr 必须 list/tuple 或 None；fields_name 必须 str/list/tuple 或 None；
列名数量必须等于数据宽度；name 必须 str 或 None。
"""

import pytest

from vools.data.qax import Qax


class TestArrValidation:
    @pytest.mark.parametrize("bad", [123, "ab", {"a": 1}, {1, 2}])
    def test_non_sequence_arr(self, bad):
        with pytest.raises(TypeError) as ei:
            Qax.ArrayToQax(bad)
        assert "arr" in str(ei.value)

    def test_string_not_treated_as_char_array(self):
        """修复前 'ab' → [['a'], ['b']]（静默错表）。"""
        with pytest.raises(TypeError):
            Qax.ArrayToQax("ab")


class TestFieldsNameValidation:
    def test_wrong_type(self):
        with pytest.raises(TypeError) as ei:
            Qax.ArrayToQax([[1, 2]], columns=123)
        assert "fields_name" in str(ei.value)

    def test_width_mismatch(self):
        with pytest.raises(ValueError) as ei:
            Qax.ArrayToQax([[1, 2]], columns=["a"])
        assert "不一致" in str(ei.value)

    def test_width_match_ok(self):
        r = Qax.ArrayToQax([[1, 2]], columns=["a", "b"])
        assert r._columns == ["a", "b"]
        assert r._data == [[1, 2]]


class TestNameValidation:
    @pytest.mark.parametrize("bad", [123, 1.5])
    def test_name_type(self, bad):
        with pytest.raises(TypeError) as ei:
            Qax.ArrayToQax([[1]], name=bad)
        assert "name" in str(ei.value)

    def test_name_string_ok(self):
        assert Qax.ArrayToQax([[1]], name="T")._name == "T"


class TestValidPathsUnchanged:
    def test_two_dim_with_headers(self):
        r = Qax.ArrayToQax([["A", 1]], columns=["k", "v"])
        assert r._columns == ["k", "v"]
        assert r._data == [["A", 1]]

    def test_one_dim(self):
        assert Qax.ArrayToQax([1, 2, 3])._data == [[1], [2], [3]]

    def test_empty(self):
        assert Qax.ArrayToQax([])._data == []

    def test_none(self):
        assert Qax.ArrayToQax(None)._data == []

    def test_str_fields_name_used_as_table_name(self):
        assert Qax.ArrayToQax([[1]], "T")._name == "T"


class TestQaxAccessLayerUnchanged:
    def test_get_cell_1based(self):
        q = Qax([["A", 1], ["B", 2]], columns=["k", "v"])
        assert q.GetCell(1, 1) == "A"
        assert q.GetCell(2, 2) == 2

    def test_get_cell_out_of_range(self):
        q = Qax([["A"]], columns=["k"])
        with pytest.raises(IndexError) as ei:
            q.GetCell(0, 1)
        assert "1..1" in str(ei.value)

    def test_get_cell2(self):
        q = Qax([["A", 1]], columns=["k", "v"])
        assert q.GetCell2("v", 1) == 1

    def test_file_to_qax_missing(self):
        with pytest.raises(FileNotFoundError):
            Qax.FileToQax("no-such-file-xyz.csv")
