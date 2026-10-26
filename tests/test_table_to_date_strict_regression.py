# -*- coding: utf-8 -*-
"""回归测试：Table.to_date 静默跳过不可解析值（BUG-499）。

``to_date`` 的既有契约是"解析不了的字符串保持原样"（见
``tests/test_data_unique_and_todate_regression.py::test_unparsable_kept``），
但调用方**无从得知发生了跳过**——整列转换后可能混着字符串与 datetime，
下游按日期处理时才炸。

本轮新增 ``strict=True`` 开关（向后兼容，默认 False 行为完全不变）：
遇到不可解析的非空字符串立即抛 ValueError，带行号与候选格式。
"""

import datetime

import pytest

from vools.data.table import Table


class TestStrictModeRaises:
    def test_unparsable_string_raises(self):
        t = Table([["2026-01-15"], ["not-a-date"]], columns=["d"])
        with pytest.raises(ValueError) as ei:
            t.to_date("d", strict=True)
        msg = str(ei.value)
        assert "not-a-date" in msg
        assert "第 1 行" in msg        # 行号（0-based）
        assert "%Y%m%d" in msg         # 候选格式提示

    def test_first_bad_row_reported(self):
        t = Table([["bad1"], ["bad2"]], columns=["d"])
        with pytest.raises(ValueError) as ei:
            t.to_date("d", strict=True)
        assert "bad1" in str(ei.value)
        assert "第 0 行" in str(ei.value)

    def test_empty_cells_not_treated_as_error(self):
        t = Table([["2026-01-15"], [""], [None]], columns=["d"])
        t.to_date("d", strict=True)          # 不应抛
        assert isinstance(t._data[0][0], datetime.datetime)
        assert t._data[1][0] == ""
        assert t._data[2][0] is None

    def test_non_string_values_kept(self):
        t = Table([[20260115], [None]], columns=["d"])
        t.to_date("d", strict=True)
        assert t._data == [[20260115], [None]]

    def test_all_valid_passes(self):
        t = Table([["20260115"], ["2026-02-20"]], columns=["d"])
        t.to_date("d", strict=True)
        assert t._data[0][0] == datetime.datetime(2026, 1, 15)
        assert t._data[1][0] == datetime.datetime(2026, 2, 20)


class TestDefaultBehaviourUnchanged:
    def test_unparsable_kept(self):
        t = Table([["not-a-date"]], columns=["d"])
        t.to_date("d")
        assert t._data[0][0] == "not-a-date"

    @pytest.mark.parametrize("value,expected", [
        ("20260115", datetime.datetime(2026, 1, 15)),
        ("2026-01-15", datetime.datetime(2026, 1, 15)),
        ("2026/01/15", datetime.datetime(2026, 1, 15)),
        ("2026.01.15", datetime.datetime(2026, 1, 15)),
        ("2026-01-15 10:30:00", datetime.datetime(2026, 1, 15, 10, 30)),
        ("20260115103000", datetime.datetime(2026, 1, 15, 10, 30)),
    ])
    def test_format_matrix(self, value, expected):
        t = Table([[value]], columns=["d"]).to_date("d")
        assert t._data[0][0] == expected

    def test_by_index(self):
        t = Table([["20260115"]], columns=["d"]).to_date(0)
        assert isinstance(t._data[0][0], datetime.datetime)

    def test_out_of_range_index_still_loud(self):
        with pytest.raises(IndexError):
            Table([["20260115"]], columns=["d"]).to_date(1)

    def test_strict_is_keyword_only(self):
        """strict 为关键字专用参数，避免与列索引位置参数混淆。"""
        import inspect

        params = inspect.signature(Table.to_date).parameters
        assert params["strict"].kind is inspect.Parameter.KEYWORD_ONLY
