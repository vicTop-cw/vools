# -*- coding: utf-8 -*-
"""回归测试：Table.to_num 静默把不可解析值变成 None（BUG-500）。

既有默认行为：``to_num`` 对无法解析的值一律 ``row[col] = None``——

    to_num([['abc']])    # → [[None]]   原值被**销毁**，调用方既拿不到原值、
                         #             也收不到任何信号（数据质量事故的典型来源）

本轮新增 ``strict=True``（默认 False，行为完全不变）：遇到不可解析的非空字符串
立即抛 ValueError（带 0-based 行号与原值）；空串/纯空白视为"缺失值"、
与 ``to_date`` 的 strict 口径一致，不算错误。
"""

import pytest

from vools.data.table import Table


class TestStrictModeRaises:
    @pytest.mark.parametrize("bad", ["abc", "1.2.3", "1e", "0x1f"])
    def test_unparsable_string(self, bad):
        with pytest.raises(ValueError) as ei:
            Table([[bad]], columns=["v"]).to_num("v", strict=True)
        assert "第 0 行" in str(ei.value)
        assert bad in str(ei.value)

    def test_row_number_reported(self):
        t = Table([["1"], ["2"], ["oops"]], columns=["v"])
        with pytest.raises(ValueError) as ei:
            t.to_num("v", strict=True)
        assert "第 2 行" in str(ei.value)

    def test_non_numeric_type(self):
        with pytest.raises(ValueError) as ei:
            Table([[[1, 2]]], columns=["v"]).to_num("v", strict=True)
        assert "[1, 2]" in str(ei.value)

    def test_empty_string_is_missing_not_error(self):
        t = Table([[""], ["  "], [None]], columns=["v"])
        t.to_num("v", strict=True)
        assert t._data == [[None], [None], [None]]

    def test_all_valid_passes(self):
        t = Table([["1,234"], ["1.5"], [7]], columns=["v"])
        t.to_num("v", strict=True)
        assert t._data == [[1234], [1.5], [7]]


class TestDefaultBehaviourUnchanged:
    def test_unparsable_becomes_none(self):
        assert Table([["abc"]], columns=["v"]).to_num("v")._data == [[None]]

    def test_matrix(self):
        t = Table([["1,234"], ["1.5"], ["abc"], [""], [None], [True]], columns=["v"])
        t.to_num("v")
        assert t._data == [[1234], [1.5], [None], [None], [None], [True]]

    def test_by_index(self):
        t = Table([["42"]], columns=["v"]).to_num(0)
        assert t._data == [[42]]

    def test_out_of_range_index_still_loud(self):
        with pytest.raises(IndexError):
            Table([["42"]], columns=["v"]).to_num(5)

    def test_strict_is_keyword_only(self):
        import inspect

        params = inspect.signature(Table.to_num).parameters
        assert params["strict"].kind is inspect.Parameter.KEYWORD_ONLY


class TestOtherConvertersUnchanged:
    def test_to_str(self):
        t = Table([[1], [1.5], [None], [True]], columns=["v"])
        t.to_str("v")
        assert t._data == [["1"], ["1.5"], [None], ["True"]]

    def test_to_date_strict_still_works(self):
        import datetime

        t = Table([["20260115"]], columns=["v"])
        t.to_date("v", strict=True)
        assert t._data[0][0] == datetime.datetime(2026, 1, 15)

        with pytest.raises(ValueError):
            Table([["nope"]], columns=["v"]).to_date("v", strict=True)
