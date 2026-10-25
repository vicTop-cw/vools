# -*- coding: utf-8 -*-
"""回归测试：日期列表表达式的 weekday/day 越界（BUG-482）。

修复前：

    get_date_list("run_weeks>1&0")    # 静默把 weekday 0 当周一（_get_weekday_date
    get_date_list("run_weeks>1&8")    # 的 `else 0` 分支），产出错误日期而非报错
    get_date_list("run_months>1&0")   # 一路到 datetime.date(..., 0) 抛底层
                                      # "day is out of range for month"
    get_date_list("run_months>1&32")  # 静默截断到月末（无任何提示）

修复后：weekday 必须在 1-7、day 必须在 1-31（带清晰 ValueError）；
1-31 之内仍按当月天数截断（月末语义保留）。

另：列表**总是包含基准日期 run_date**（实现一直如此，本轮补进 docstring）。
"""

import pytest

from vools.datetime.dates_format import DateProcessor


@pytest.fixture()
def p():
    proc = DateProcessor()
    proc.set_run_date("2024-03-15")     # 周五
    return proc


class TestWeekdayValidation:
    @pytest.mark.parametrize("bad", [0, 8, 9, -1])
    def test_out_of_range_weekday(self, p, bad):
        # -1 会被正则先拒（"无效的日期列表表达式格式"），0/8/9 由 weekday 校验拒
        with pytest.raises(ValueError):
            p.get_date_list(f"run_weeks>1&{bad}")

    @pytest.mark.parametrize("wd", [1, 2, 3, 4, 5, 6, 7])
    def test_valid_weekdays(self, p, wd):
        result = p.get_date_list(f"run_weeks>1&{wd}")
        assert result          # 非空且以单引号包裹

    def test_no_silent_monday_fallback(self, p):
        """修复前 &0 与 &8 都会产出同一个周一日期。"""
        with pytest.raises(ValueError):
            p.get_date_list("run_weeks>1&0")
        with pytest.raises(ValueError):
            p.get_date_list("run_weeks>1&8")


class TestMonthDayValidation:
    @pytest.mark.parametrize("bad", [0, 32, 99])
    def test_out_of_range_day(self, p, bad):
        with pytest.raises(ValueError) as ei:
            p.get_date_list(f"run_months>1&{bad}")
        assert "1-31" in str(ei.value)

    def test_month_end_clamping_preserved(self):
        """1..31 之内仍按当月天数截断（既有月末语义）。"""
        p = DateProcessor()
        p.set_run_date("2024-01-31")
        # 2 月只有 29 天（闰年）→ 31 号截断为 29 号
        assert "'20240229'" in p.get_date_list("run_months>1&31")

    def test_non_leap_february_clamp(self):
        p = DateProcessor()
        p.set_run_date("2023-01-31")
        assert p.get_single_date("run_month+1&30") == "20230228"


class TestBaselineDateIncluded:
    """实现一直包含基准日期（本轮补文档，行为不变）。"""

    def test_days_list_starts_at_run_date(self, p):
        assert p.get_date_list("run_days>0") == "'20240315'"

    def test_weeks_list_contains_run_date(self, p):
        assert "'20240315'" in p.get_date_list("run_weeks>2&3")

    def test_months_list_contains_run_date(self, p):
        assert "'20240315'" in p.get_date_list("run_months>2&13")


class TestValidExpressionsUnchanged:
    def test_days_forward(self, p):
        assert p.get_date_list("run_days>2") == (
            "'20240315'，'20240316'，'20240317'")

    def test_weeks_forward(self, p):
        assert p.get_date_list("run_weeks>2&3") == (
            "'20240315'，'20240320'，'20240327'")

    def test_weeks_backward(self, p):
        assert p.get_date_list("run_weeks<2&5") == (
            "'20240301'，'20240308'，'20240315'")

    def test_single_date_expressions(self, p):
        assert p.get_single_date("run_week+1&3") == "20240320"
        assert p.get_single_date("run_month+1&13") == "20240413"
