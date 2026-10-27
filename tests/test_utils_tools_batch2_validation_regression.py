# -*- coding: utf-8 -*-
"""回归测试：utils.tools 第二批入参零校验（BUG-526）。

修复前（全部裸错，看不出是哪个参数）：

    get_py_fmt(None)              # TypeError: argument of type 'NoneType' is not iterable
    offset_date(None, 1)          # 同上
    offset_date("20240101", "x")  # TypeError: unsupported type for timedelta days component: str
    check_no_overlap(None)        # TypeError: object of type 'NoneType' has no len()
    check_no_overlap([1, 2])      # TypeError: argument of type 'int' is not iterable
    get_index_cols(None)          # TypeError: object of type 'NoneType' has no len()

修复后统一 TypeError（带参数名与实参）；合法路径（含文档承诺的
`datetime.date` / `datetime.datetime` 基准日期）保持不变。
"""

import datetime

import pytest

import vools.utils.tools as t


class TestGetPyFmtValidation:
    @pytest.mark.parametrize("bad", [None, 123, ["y"]])
    def test_non_str(self, bad):
        with pytest.raises(TypeError) as ei:
            t.get_py_fmt(bad)
        assert "fmt" in str(ei.value)

    @pytest.mark.parametrize("fmt,expected", [
        ("yyyyMMdd", "%Y%m%d"),
        ("yyyy-MM-dd HH:mm:ss", "%Y-%m-%d %H:%M:%S"),
    ])
    def test_conversion_unchanged(self, fmt, expected):
        assert t.get_py_fmt(fmt) == expected


class TestOffsetDateValidation:
    @pytest.mark.parametrize("bad", [None, 123, [1]])
    def test_bad_run_date(self, bad):
        with pytest.raises(TypeError) as ei:
            t.offset_date(bad, 1)
        assert "run_date" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", None, [1]])
    def test_bad_offset_days(self, bad):
        with pytest.raises(TypeError) as ei:
            t.offset_date("20240101", bad)
        assert "offset_days" in str(ei.value)


class TestOffsetDateBehaviourUnchanged:
    def test_yyyymmdd(self):
        assert t.offset_date("20240101", 1) == "20240102"

    def test_dashed(self):
        assert t.offset_date("2024-01-01", 1, std=True) == "2024-01-02"

    def test_date_object(self):
        """文档承诺支持 datetime.date。"""
        assert t.offset_date(datetime.date(2024, 1, 1), 1) == "20240102"

    def test_datetime_object(self):
        assert t.offset_date(datetime.datetime(2024, 1, 1, 10, 30), 1) == "20240102"

    def test_negative_offset(self):
        assert t.offset_date("20240102", -1) == "20240101"


class TestCheckNoOverlapValidation:
    @pytest.mark.parametrize("bad", [None, 123, "abc"])
    def test_non_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            t.check_no_overlap(bad)
        assert "strings" in str(ei.value)

    def test_non_str_element(self):
        with pytest.raises(TypeError) as ei:
            t.check_no_overlap([1, 2])
        assert "元素" in str(ei.value)

    def test_behaviour_unchanged(self):
        assert t.check_no_overlap(["ab", "abc"]) is False
        assert t.check_no_overlap(["ab", "cd"]) is True
        assert t.check_no_overlap([]) is True


class TestGetIndexColsValidation:
    @pytest.mark.parametrize("bad", [None, 123, "ab"])
    def test_non_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            t.get_index_cols(bad)
        assert "cols" in str(ei.value)

    def test_behaviour_unchanged(self):
        # ix 是**逐个 1-based 索引**，不是"取前 N 个"
        assert t.get_index_cols(["a", "b"], 1) == ["a"]
        assert t.get_index_cols(["a", "b"], 2) == ["b"]
        assert t.get_index_cols(["a", "b"], 1, 2) == ["a", "b"]

    def test_zero_index_rejected(self):
        with pytest.raises(ValueError) as ei:
            t.get_index_cols(["a", "b"], 0)
        assert "start from 1" in str(ei.value)
