# -*- coding: utf-8 -*-
"""回归测试：days_gap/months_gap/weeks_gap 的非法日期静默 None（BUG-480）。

修复前三个函数用 ``except Exception: return None`` 包住解析与计算：

    days_gap("nope", "2024-01-01")      # -> None   （docstring 承诺返回 int）
    months_gap("2024-13-01", "2024-01-01")  # -> None
    weeks_gap("x", "2024-01-01")        # -> None

调用方随后 ``gap > 7`` 才炸，或 ``if gap and gap > 7`` 直接**静默跳过**。
修复后非法日期抛带原始串的 ValueError；**输入 None 仍返回 None**（既有约定），
合法日期（yyyy-MM-dd 与 yyyyMMdd）结果不变。
"""

import pytest

from vools.datetime.utils import days_gap, months_gap, weeks_gap


class TestInvalidDatesAreLoud:
    @pytest.mark.parametrize("bad", ["nope", "2024-13-01", "2024/01/01", "13", ""])
    def test_days_gap(self, bad):
        with pytest.raises((ValueError, TypeError)) as ei:
            days_gap(bad, "2024-01-01")
        assert "日期" in str(ei.value)

    @pytest.mark.parametrize("bad", ["nope", "2024-13-01"])
    def test_months_gap(self, bad):
        with pytest.raises((ValueError, TypeError)):
            months_gap(bad, "2024-01-01")

    @pytest.mark.parametrize("bad", ["x", "2024-99-99"])
    def test_weeks_gap(self, bad):
        with pytest.raises((ValueError, TypeError)):
            weeks_gap(bad, "2024-01-01")

    def test_second_arg_also_validated(self):
        with pytest.raises(Exception):
            days_gap("2024-01-01", "nope")


class TestNoneSemanticsUnchanged:
    @pytest.mark.parametrize("func", [days_gap, months_gap, weeks_gap])
    def test_none_input_returns_none(self, func):
        assert func(None, "2024-01-01") is None
        assert func("2024-01-01", None) is None


class TestValidDatesUnchanged:
    def test_days_gap_both_formats(self):
        assert days_gap("2024-01-01", "2024-01-10") == -9
        assert days_gap("20240101", "20240110") == -9
        assert days_gap("2024-01-10", "2024-01-01") == 9

    def test_months_gap(self):
        assert months_gap("2024-01-01", "2024-03-01") == -2
        assert months_gap("2024-03-01", "2024-01-01") == 2

    def test_weeks_gap(self):
        assert weeks_gap("2024-01-01", "2024-01-22") == -3

    def test_datetime_string_with_time_suffix(self):
        """取前 10 个字符（日期部分），带时间后缀也照常解析。"""
        assert days_gap("2024-01-01 12:34:56", "2024-01-02") == -1
