# -*- coding: utf-8 -*-
"""回归测试：ResultSet 的 columns/fetchmany 参数校验（BUG-464）。

修复前 ``ResultSet.__init__`` 直接 ``list(columns)``：

    ResultSet('abc')   # -> columns=['a', 'b', 'c']  ← 字符串被逐字符拆成列名（静默错值）
    ResultSet(None)    # -> TypeError: 'NoneType' object is not iterable（看不出参数）
    ResultSet(123)     # -> TypeError: 'int' object is not iterable

``fetchmany('x')`` 则在 ``size <= 0`` 处抛
``'<=' not supported between instances of 'str' and 'int'``（天书）。

修复后 columns 必须是 list/tuple 的非空字符串列名；size 必须是 int 或 None。
空列名列表仍然合法（DDL/DML 的 ResultSet 就是空 columns）。
"""

import pytest

from vools.sql.core.result import ResultSet


class TestColumnsValidation:
    @pytest.mark.parametrize("bad", ["abc", None, 123, 1.5])
    def test_non_sequence_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            ResultSet(bad)
        assert "columns" in str(ei.value)

    def test_string_not_char_split(self):
        """修复前 'abc' 会变成 ['a','b','c']（静默错值）。"""
        with pytest.raises(TypeError):
            ResultSet("abc")

    @pytest.mark.parametrize("bad_cols", [["", "b"], ["a", None], [1, 2], ["a", "  "]])
    def test_column_names_must_be_non_empty_str(self, bad_cols):
        with pytest.raises(ValueError) as ei:
            ResultSet(bad_cols)
        assert "列名" in str(ei.value)

    def test_empty_columns_allowed(self):
        assert ResultSet([]).columns == []

    def test_tuple_columns_allowed(self):
        assert ResultSet(("a", "b")).columns == ["a", "b"]


class TestFetchmanyValidation:
    @pytest.fixture()
    def rs(self):
        return ResultSet(["id", "name"], [[1, "a"], [2, "b"], [3, "c"]])

    @pytest.mark.parametrize("bad", ["x", True, [1], 1.5])
    def test_non_int_size_rejected(self, rs, bad):
        with pytest.raises(TypeError) as ei:
            rs.fetchmany(bad)
        assert "size" in str(ei.value)

    def test_cursor_semantics_unchanged(self, rs):
        assert len(rs.fetchmany(2)) == 2
        assert len(rs.fetchmany(2)) == 1        # 只剩 1 行
        assert rs.fetchmany(9) == []            # 已耗尽

    def test_none_means_one(self, rs):
        assert len(rs.fetchmany(None)) == 1

    @pytest.mark.parametrize("size", [0, -1])
    def test_non_positive_returns_empty(self, rs, size):
        assert rs.fetchmany(size) == []

    def test_reset_cursor(self, rs):
        rs.fetchmany(2)
        rs.reset_cursor()
        assert len(rs.fetchmany(2)) == 2


class TestUnchangedSemantics:
    def test_to_list(self):
        assert ResultSet(["a"], [[1], [2]]).to_list() == [{"a": 1}, {"a": 2}]

    def test_first_and_scalar(self):
        rs = ResultSet(["a"], [[7], [8]])
        assert rs.first().as_dict() == {"a": 7}
        assert rs.scalar() == 7

    def test_row_length_mismatch_still_loud(self):
        with pytest.raises(ValueError):
            ResultSet(["a"], [[1, 2]])
