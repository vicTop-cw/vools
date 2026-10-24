# -*- coding: utf-8 -*-
"""回归测试：utils.tools 静默 None + 关键工具契约（BUG-455）。

修复前两个函数对不支持的类型**静默返回 None**：

    split('a,b', 123)                 # -> None（调用方稍后 for 循环才炸）
    union_ordered_collection({1, 2})  # -> None（set/str/None 全都静默 None）

修复后抛带参数名的 TypeError。同时锁定 regexp_*（SQL 语义）、excel 列号往返、
trim/shift/get_index_cols 的正确契约。
"""

import pytest

from vools.utils.tools import (
    excel_column_to_number,
    excel_number_to_column,
    get_char,
    get_index_cols,
    regexp_count,
    regexp_findall,
    regexp_instr,
    regexp_like,
    regexp_replace,
    regexp_split,
    regexp_substr,
    shift,
    split,
    trim,
    union_ordered_collection,
)


class TestSplitValidation:
    @pytest.mark.parametrize("bad", [123, None, 1.5, object()])
    def test_bad_separator(self, bad):
        with pytest.raises(TypeError) as ei:
            split("a,b", bad)
        assert "separator" in str(ei.value)

    def test_str_separator(self):
        assert split("a,b,c", ",") == ["a", "b", "c"]

    @pytest.mark.parametrize("seps", [[",", ";"], (",", ";"), {",", ";"}])
    def test_multi_separators(self, seps):
        assert split("a,b;c", seps) == ["a", "b", "c"]


class TestUnionOrderedCollection:
    @pytest.mark.parametrize("bad", [{1, 2}, "abc", None, {"a": 1}, 123])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            union_ordered_collection(bad)
        assert "union_ordered_collection" in str(ei.value)

    def test_list(self):
        assert union_ordered_collection([1, 2, 2, 3, 1]) == [1, 2, 3]

    def test_tuple(self):
        assert union_ordered_collection((1, 2, 1)) == (1, 2)


class TestRegexpSqlSemantics:
    def test_count(self):
        assert regexp_count(r"\d+", "a1b22c333") == 3

    def test_findall(self):
        assert regexp_findall(r"\d+", "a1b22") == ["1", "22"]

    def test_instr_is_1_based(self):
        assert regexp_instr(r"\d", "a1b22") == 1

    def test_like_full_match(self):
        assert regexp_like("abc", "abc") is True
        assert regexp_like("abc", "abcd") is False   # complete_matching

    def test_replace(self):
        assert regexp_replace(r"\d", "a1b2", "#") == "a#b#"

    def test_substr(self):
        assert regexp_substr(r"\d+", "ab123cd") == "123"

    def test_split(self):
        assert regexp_split(",", "a,b,c") == ["a", "b", "c"]


class TestExcelColumns:
    @pytest.mark.parametrize("col,num", [("A", 1), ("Z", 26), ("AA", 27), ("AB", 28)])
    def test_to_number(self, col, num):
        assert excel_column_to_number(col) == num

    @pytest.mark.parametrize("num,col", [(1, "A"), (26, "Z"), (27, "AA"), (28, "AB")])
    def test_to_column(self, num, col):
        assert excel_number_to_column(num) == col

    @pytest.mark.parametrize("col", ["A", "Z", "AA", "AB", "ZZ", "AAA"])
    def test_roundtrip(self, col):
        assert excel_number_to_column(excel_column_to_number(col)) == col


class TestMiscContracts:
    def test_trim(self):
        assert trim("  ab  ") == "ab"
        assert trim("xxabxx", "x") == "ab"

    def test_shift(self):
        assert list(shift([1, 2, 3], 1)) == [None, 1, 2]
        assert list(shift([1, 2, 3], 1, fill_value=0)) == [0, 1, 2]

    def test_get_index_cols_1_based(self):
        assert get_index_cols(["a", "b", "c"], 1) == ["a"]
        assert get_index_cols(["a", "b", "c"], "b") == ["b"]
        with pytest.raises(ValueError):
            get_index_cols(["a", "b", "c"], 0)

    def test_get_char(self):
        assert get_char("abc", "★") == "★"
        assert get_char("ab★c", "★") not in "ab★c"
