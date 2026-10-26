# -*- coding: utf-8 -*-
"""回归测试：vools.utils.tools 的参数校验缺口（BUG-513）。

修复前（全部裸错或在参数错时给出无关报错）：

    trim(None)                 # AttributeError: 'NoneType' object has no attribute 'strip'
    trim(123)                  # AttributeError: 'int' object has no attribute 'strip'
    trim("a", 123)             # 同上（chars 不可用）
    split(None, ",")           # AttributeError: 'NoneType' object has no attribute 'split'
    shift(123)                 # TypeError: 'int' object is not iterable
    shift([1, 2], "x")         # TypeError: '>' not supported between 'str' and 'int'
    get_char(123)              # AttributeError: 'int' object has no attribute 'count'
    get_date_seq(nums=-1)      # 静默返回 []（调用方以为"没有日期"）

修复后一律带参数名的 TypeError/ValueError。
"""

import pytest

import vools.utils.tools as t


class TestTrimValidation:
    @pytest.mark.parametrize("bad", [None, 123, [1]])
    def test_string(self, bad):
        with pytest.raises(TypeError) as ei:
            t.trim(bad)
        assert "string" in str(ei.value)

    def test_chars(self):
        with pytest.raises(TypeError) as ei:
            t.trim("a", 123)
        assert "chars" in str(ei.value)

    def test_valid(self):
        assert t.trim("  a  ") == "a"
        assert t.trim("xxa", "x") == "a"


class TestSplitValidation:
    @pytest.mark.parametrize("bad", [None, 123])
    def test_string(self, bad):
        with pytest.raises(TypeError) as ei:
            t.split(bad, ",")
        assert "string" in str(ei.value)

    def test_separator_error_still_clear(self):
        with pytest.raises(TypeError) as ei:
            t.split("abc", None)
        assert "separator" in str(ei.value)

    def test_valid(self):
        assert t.split("a,b", ",") == ["a", "b"]


class TestShiftValidation:
    @pytest.mark.parametrize("bad", [123, None])
    def test_iters(self, bad):
        with pytest.raises(TypeError) as ei:
            t.shift(bad)
        assert "iters" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", 1.5, True])
    def test_num(self, bad):
        with pytest.raises(TypeError) as ei:
            t.shift([1, 2], bad)
        assert "num" in str(ei.value)

    def test_valid_shift(self):
        assert t.shift([1, 2, 3]) == [None, 1, 2]
        assert t.shift([1, 2, 3], -1) == [2, 3, None]

    def test_cycle(self):
        assert t.shift([1, 2, 3], 1, cycle=True) == [3, 1, 2]


class TestGetCharValidation:
    @pytest.mark.parametrize("bad", [None, 123])
    def test_string(self, bad):
        with pytest.raises(TypeError) as ei:
            t.get_char(bad)
        assert "string" in str(ei.value)

    def test_valid(self):
        assert t.get_char("abc") == "★"
        assert t.get_char("abc★") != "★"


class TestGetDateSeqValidation:
    def test_negative(self):
        with pytest.raises(ValueError) as ei:
            t.get_date_seq(nums=-1)
        assert "nums" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", 1.5, True])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            t.get_date_seq(nums=bad)
        assert "nums" in str(ei.value)

    def test_zero_returns_empty(self):
        assert t.get_date_seq(nums=0) == []

    def test_positive(self):
        assert len(t.get_date_seq(nums=2)) == 2


class TestExcelColumnUnchanged:
    @pytest.mark.parametrize("letter,number", [("A", 1), ("Z", 26), ("AA", 27), ("AB", 28)])
    def test_roundtrip(self, letter, number):
        assert t.excel_column_to_number(letter) == number
        assert t.excel_number_to_column(number) == letter

    def test_invalid(self):
        with pytest.raises(ValueError):
            t.excel_column_to_number("")
        with pytest.raises(ValueError):
            t.excel_number_to_column(0)
