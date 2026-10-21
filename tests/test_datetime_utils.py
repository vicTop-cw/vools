# -*- coding: utf-8 -*-
"""测试 vools.datetime.utils。"""

import pytest
from datetime import datetime
from vools.datetime.utils import (
    vDate, get_week, get_month, days_gap, weeks_gap, months_gap,
    get_recently_months, get_recently_weeks, get_recently_days,
    get_dates, parse_date_string, get_date_range,
    simplify_date_ranges, _add_frequency, _subtract_frequency,
    _generate_date_range, _generate_date_range_by_periods,
    _generate_date_range_by_end_periods
)

__all__ = ["TestVDate", "TestGetWeek", "TestGetMonth", "TestGaps",
           "TestGetRecentlyMonths", "TestGetRecentlyWeeks", "TestGetRecentlyDays",
           "TestGetDates", "TestParseDateString", "TestGetDateRange",
           "TestAddFrequency", "TestSubtractFrequency", "TestGenDateRange",
           "TestSimplify", "TestImport"]


class TestVDate:
    """vDate 测试。"""

    def test_none_now(self):
        result = vDate(None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_diff(self):
        result = vDate(None, diffDays=1)
        assert isinstance(result, str)

    def test_int_timestamp(self):
        result = vDate(0)
        assert result.startswith("1970-01-01")

    def test_float_timestamp(self):
        result = vDate(0.0)
        assert result.startswith("1970-01-01")

    def test_str_yyyy_mm_dd(self):
        result = vDate("2024-01-02")
        assert result == "2024-01-02"

    def test_str_yyyymmdd(self):
        result = vDate("20240102")
        assert result == "20240102"

    def test_str_yyyymmdd_hms(self):
        result = vDate("2024-01-02 13:45:30")
        assert result == "2024-01-02 13:45:30"

    def test_str_compact_hms(self):
        result = vDate("20240102 13:45:30")
        assert result == "20240102 13:45:30"

    def test_str_with_fmt(self):
        result = vDate("2024.01.02", fmt="%Y.%m.%d")
        assert result == "2024.01.02"

    def test_datetime(self):
        dt = datetime(2024, 3, 5, 12, 30, 0)
        result = vDate(dt)
        assert result == "2024-03-05 12:30:00"

    def test_diff_int(self):
        result = vDate(0, diffDays=1)
        assert result.startswith("1970-01-02")

    def test_swap_args(self):
        # diffDays 传 int，fmt 传 int → 交换
        result = vDate("2024-01-02", 1)
        assert result == "2024-01-03"

    def test_swap_str_fmt(self):
        result = vDate(None, "2024-01-02")  # fmt 是 str, diffDays 是 str
        assert isinstance(result, str)

    def test_type_error(self):
        with pytest.raises(TypeError):
            vDate(object())


class TestGetWeek:
    """get_week 测试。"""

    def test_none(self):
        assert get_week(None) is None

    def test_num_none(self):
        result = get_week("2024-01-10", None)
        assert isinstance(result, str)

    def test_10_format(self):
        result = get_week("2024-01-10")
        assert result == "2024-01-08"  # 周一

    def test_8_format(self):
        result = get_week("20240110")
        assert result == "20240108"

    def test_num_offset(self):
        # BUG-242: 正数=未来，2024-01-10 周三 + 1 周 = 2024-01-15（下周一）
        result = get_week("2024-01-10", num=1)
        assert result == "2024-01-15"

    def test_bad_weekday(self):
        with pytest.raises(ValueError):
            get_week("2024-01-10", weekday=0)

    def test_bad_weekday_high(self):
        with pytest.raises(ValueError):
            get_week("2024-01-10", weekday=8)

    def test_weekday_7(self):
        result = get_week("2024-01-10", weekday=7)
        assert isinstance(result, str)


class TestGetMonth:
    """get_month 测试。"""

    def test_none(self):
        assert get_month(None) is None

    def test_current(self):
        assert get_month("2024-01-15") == "2024-01-01"

    def test_compact(self):
        assert get_month("20240115") == "20240101"

    def test_lastday(self):
        assert get_month("2024-01-15", is_lastday=True) == "2024-01-31"

    def test_negative_num(self):
        assert get_month("2024-01-15", num=-1) == "2024-02-01"

    def test_positive_num(self):
        assert get_month("2024-01-15", num=1) == "2023-12-01"

    def test_num_none(self):
        assert get_month("2024-01-15", None) is None


class TestGaps:
    """天数/周数/月数差测试。"""

    def test_days_gap(self):
        assert days_gap("2024-01-10", "2024-01-01") == 9

    def test_days_gap_compact(self):
        assert days_gap("20240110", "20240101") == 9

    def test_days_gap_none(self):
        assert days_gap(None, "2024-01-01") is None
        assert days_gap("2024-01-01", None) is None

    def test_days_gap_bad(self):
        assert days_gap("bad", "2024-01-01") is None

    def test_weeks_gap(self):
        assert weeks_gap("2024-01-15", "2024-01-08") == 1

    def test_weeks_gap_none(self):
        assert weeks_gap(None, "2024-01-01") is None

    def test_weeks_gap_bad(self):
        assert weeks_gap("bad", "2024-01-01") is None

    def test_months_gap(self):
        assert months_gap("2024-03-01", "2024-01-01") == 2

    def test_months_gap_none(self):
        assert months_gap(None, "2024-01-01") is None

    def test_months_gap_bad(self):
        assert months_gap("bad", "2024-01-01") is None


class TestGetRecentlyMonths:
    """get_recently_months 测试。"""

    def test_none(self):
        assert get_recently_months(None) == []

    def test_num_none(self):
        assert get_recently_months("2024-01-15", None) == []

    def test_num_zero(self):
        assert get_recently_months("2024-01-15", 0) == ["2024-01-15"]

    def test_num_one(self):
        result = get_recently_months("2024-03-15", 1)
        assert len(result) == 2
        assert result[0] == "2024-03-15"
        assert result[1] == "2024-02-29"  # 2024 闰年

    def test_negative_num(self):
        result = get_recently_months("2024-01-15", -1)
        assert len(result) == 2

    def test_compact(self):
        result = get_recently_months("20240315", 1)
        assert len(result) == 2


class TestGetRecentlyWeeks:
    """get_recently_weeks 测试。"""

    def test_none(self):
        assert get_recently_weeks(None) == []

    def test_num_zero(self):
        assert get_recently_weeks("2024-01-15", 0) == ["2024-01-15"]

    def test_num_one(self):
        result = get_recently_weeks("2024-01-10", 1)
        assert len(result) == 2

    def test_negative_num(self):
        result = get_recently_weeks("2024-01-10", -1)
        assert len(result) == 2

    def test_num_none(self):
        assert get_recently_weeks("2024-01-10", None) == []


class TestGetRecentlyDays:
    """get_recently_days 测试。"""

    def test_none(self):
        assert get_recently_days(None) == []

    def test_num_zero(self):
        assert get_recently_days("2024-01-15", 0) == ["2024-01-15"]

    def test_num_one(self):
        result = get_recently_days("2024-01-15", 1)
        assert len(result) == 2
        assert result[1] == "2024-01-14"

    def test_negative_num(self):
        result = get_recently_days("2024-01-15", -1)
        assert len(result) == 2
        assert result[1] == "2024-01-16"

    def test_num_none(self):
        assert get_recently_days("2024-01-15", None) == []


class TestGetDates:
    """get_dates 测试。"""

    def test_default_d(self):
        result = get_dates("2024-01-15", 2)
        assert len(result) == 3

    def test_none(self):
        assert get_dates(None) == []

    def test_tp_w(self):
        result = get_dates("2024-01-15", 2, "w")
        assert len(result) == 3

    def test_tp_m(self):
        result = get_dates("2024-03-15", 2, "m")
        assert len(result) == 3

    def test_tp_invalid(self):
        assert get_dates("2024-01-15", 2, "x") == []

    def test_tp_empty(self):
        result = get_dates("2024-01-15", 2, "")
        assert len(result) == 3

    def test_num_zero(self):
        assert get_dates("2024-01-15", 0) == ["2024-01-15"]


class TestParseDateString:
    """parse_date_string 测试。"""

    def test_default(self):
        assert parse_date_string("2024-01-15") == datetime(2024, 1, 15)

    def test_custom_fmt(self):
        assert parse_date_string("20240115", "%Y%m%d") == datetime(2024, 1, 15)

    def test_fallback(self):
        assert parse_date_string("20240115") == datetime(2024, 1, 15)

    def test_fallback_slash(self):
        assert parse_date_string("2024/01/15") == datetime(2024, 1, 15)

    def test_empty(self):
        assert parse_date_string("") is None

    def test_bad(self):
        with pytest.raises(ValueError):
            parse_date_string("bad-date")

    def test_parse_fmt_none(self):
        assert parse_date_string("2024-01-15", None) == datetime(2024, 1, 15)


class TestGetDateRange:
    """get_date_range 测试。"""

    def test_start_end_d(self):
        result = get_date_range("2024-01-01", "2024-01-03")
        assert len(result) == 3
        assert result[0] == "2024-01-01"
        assert result[2] == "2024-01-03"

    def test_start_end_compact(self):
        result = get_date_range("20240101", "20240103", parse_fmt="%Y%m%d", fmt="%Y%m%d")
        assert len(result) == 3

    def test_bad_freq(self):
        with pytest.raises(ValueError):
            get_date_range("2024-01-01", "2024-01-03", freq="X")

    def test_none_all(self):
        with pytest.raises(ValueError):
            get_date_range()

    def test_start_only_periods(self):
        result = get_date_range("2024-01-01", periods=3)
        assert len(result) == 3

    def test_end_only_periods(self):
        result = get_date_range(end="2024-01-03", periods=3)
        assert len(result) == 3

    def test_start_end_swap(self):
        result = get_date_range("2024-01-03", "2024-01-01")
        assert len(result) == 3

    def test_start_end_periods_warning(self):
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_date_range("2024-01-01", "2024-01-02", periods=3)
            assert any("periods" in str(x.message) for x in w)

    def test_end_only_none_periods(self):
        result = get_date_range(end="2024-01-03")
        assert len(result) >= 1


class TestAddFrequency:
    """_add_frequency 测试。"""

    def test_d(self):
        assert _add_frequency(datetime(2024, 1, 1), "D") == datetime(2024, 1, 2)

    def test_w(self):
        assert _add_frequency(datetime(2024, 1, 1), "W") == datetime(2024, 1, 8)

    def test_m(self):
        assert _add_frequency(datetime(2024, 1, 15), "M") == datetime(2024, 2, 15)

    def test_m_clamp(self):
        assert _add_frequency(datetime(2024, 1, 31), "M") == datetime(2024, 2, 29)

    def test_m_december(self):
        assert _add_frequency(datetime(2024, 12, 15), "M") == datetime(2025, 1, 15)

    def test_y(self):
        assert _add_frequency(datetime(2024, 1, 15), "Y") == datetime(2025, 1, 15)

    def test_y_leap(self):
        assert _add_frequency(datetime(2024, 2, 29), "Y") == datetime(2025, 2, 28)

    def test_q(self):
        assert _add_frequency(datetime(2024, 1, 15), "Q") == datetime(2024, 4, 15)

    def test_h(self):
        assert _add_frequency(datetime(2024, 1, 15), "H") == datetime(2024, 7, 15)

    def test_else(self):
        assert _add_frequency(datetime(2024, 1, 1), "X") == datetime(2024, 1, 2)


class TestSubtractFrequency:
    """_subtract_frequency 测试。"""

    def test_d(self):
        assert _subtract_frequency(datetime(2024, 1, 2), "D") == datetime(2024, 1, 1)

    def test_w(self):
        assert _subtract_frequency(datetime(2024, 1, 8), "W") == datetime(2024, 1, 1)

    def test_m(self):
        assert _subtract_frequency(datetime(2024, 2, 15), "M") == datetime(2024, 1, 15)

    def test_m_january(self):
        assert _subtract_frequency(datetime(2024, 1, 15), "M") == datetime(2023, 12, 15)

    def test_y(self):
        assert _subtract_frequency(datetime(2024, 1, 15), "Y") == datetime(2023, 1, 15)

    def test_q(self):
        assert _subtract_frequency(datetime(2024, 4, 15), "Q") == datetime(2024, 1, 15)

    def test_h(self):
        assert _subtract_frequency(datetime(2024, 7, 15), "H") == datetime(2024, 1, 15)

    def test_else(self):
        assert _subtract_frequency(datetime(2024, 1, 2), "X") == datetime(2024, 1, 1)


class TestGenDateRange:
    """生成日期范围内部函数测试。"""

    def test_generate(self):
        result = _generate_date_range(datetime(2024, 1, 1), datetime(2024, 1, 3), "D")
        assert len(result) == 3

    def test_periods(self):
        result = _generate_date_range_by_periods(datetime(2024, 1, 1), 3, "D")
        assert len(result) == 3

    def test_periods_zero(self):
        assert _generate_date_range_by_periods(datetime(2024, 1, 1), 0, "D") == []

    def test_periods_negative(self):
        assert _generate_date_range_by_periods(datetime(2024, 1, 1), -1, "D") == []

    def test_end_periods(self):
        result = _generate_date_range_by_end_periods(datetime(2024, 1, 3), 3, "D")
        assert len(result) == 3
        assert result[-1] == datetime(2024, 1, 3)

    def test_end_periods_zero(self):
        assert _generate_date_range_by_end_periods(datetime(2024, 1, 3), 0, "D") == []


class TestSimplify:
    """simplify_date_ranges 测试。"""

    def test_empty(self):
        assert simplify_date_ranges([]) == []

    def test_bad_type(self):
        with pytest.raises(TypeError):
            simplify_date_ranges(42)

    def test_single(self):
        result = simplify_date_ranges(["2024-01-01"])
        assert len(result) == 1
        assert result[0].start == "2024-01-01"
        assert result[0].count == 1

    def test_continuous(self):
        result = simplify_date_ranges(["2024-01-01", "2024-01-02", "2024-01-03"])
        assert len(result) == 1
        assert result[0].start == "2024-01-01"
        assert result[0].end == "2024-01-03"
        assert result[0].count == 3

    def test_discontinuous(self):
        result = simplify_date_ranges(["2024-01-01", "2024-01-03"])
        assert len(result) == 2

    def test_set_input(self):
        result = simplify_date_ranges({"2024-01-01", "2024-01-02"})
        assert len(result) == 1

    def test_tuple_input(self):
        result = simplify_date_ranges(("2024-01-01", "2024-01-02"))
        assert len(result) == 1

    def test_bad_dates(self):
        result = simplify_date_ranges(["bad", "2024-01-01"])
        assert len(result) == 1

    def test_all_bad(self):
        assert simplify_date_ranges(["bad", "worse"]) == []


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.datetime.utils import __all__
        for name in ["vDate", "get_week", "get_month", "days_gap",
                     "weeks_gap", "months_gap", "get_recently_months",
                     "get_recently_weeks", "get_recently_days",
                     "get_dates", "parse_date_string", "get_date_range",
                     "simplify_date_ranges"]:
            assert name in __all__
