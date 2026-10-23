# -*- coding: utf-8 -*-
"""回归测试：VDate.getDateRange 的月度锚定与参数组合（BUG-388/389）。

【BUG-388】`_generate_date_range` 的 'M' 分支用**本次已夹取的日期**再推进一个月，
日期会漂移：

    VDate(...).getDateRange(start='2026-01-31', periods=4, freq='M')
    # 修复前：['2026-01-31', '2026-02-28', '2026-03-28', '2026-04-28']
    #                                        ^^^ 应为 03-31（从起始日锚定）
    # 修复后：['2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30']

修复：按「起始日锚定 + 每月末夹取」生成（三个分支统一）。

【BUG-389】`getDateRange(start=..., end=..., periods=...)` 三者同给时，最终
else 分支只按 start+end 生成、**静默忽略 periods**。修复：显式 ValueError。

D/W 频率的既有行为不变。
"""

import pytest

from vools.datetime.vdate_class import VDate


@pytest.fixture()
def d():
    return VDate('2026-01-01')


class TestMonthAnchoring:
    def test_start_periods(self, d):
        # 修复前：['2026-01-31', '2026-02-28', '2026-03-28', '2026-04-28']
        assert d.getDateRange(start='2026-01-31', periods=4, freq='M') == [
            '2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30']

    def test_start_end(self, d):
        assert d.getDateRange(start='2026-01-31', end='2026-04-30', freq='M') == [
            '2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30']

    def test_end_periods(self, d):
        assert d.getDateRange(end='2026-03-31', periods=3, freq='M') == [
            '2026-01-31', '2026-02-28', '2026-03-31']

    def test_leap_year(self):
        out = VDate('2024-01-01').getDateRange(start='2024-01-31', periods=3, freq='M')
        assert out == ['2024-01-31', '2024-02-29', '2024-03-31']

    def test_lowercase_freq(self, d):
        assert len(d.getDateRange(start='2026-01-31', periods=2, freq='m')) == 2


class TestThreeArgsRejected:
    def test_three_given(self, d):
        # 修复前：静默忽略 periods，返回 5 天
        with pytest.raises(ValueError) as ei:
            d.getDateRange(start='2026-01-01', end='2026-01-05', periods=3)
        assert 'periods' in str(ei.value)

    def test_two_given_still_ok(self, d):
        assert d.getDateRange(start='2026-01-01', periods=2) == ['2026-01-01', '2026-01-02']
        assert d.getDateRange(start='2026-01-01', end='2026-01-02') == [
            '2026-01-01', '2026-01-02']
        assert d.getDateRange(end='2026-01-02', periods=2) == ['2026-01-01', '2026-01-02']


class TestOtherFreqUnchanged:
    def test_day(self, d):
        assert d.getDateRange(start='2026-01-01', periods=3) == [
            '2026-01-01', '2026-01-02', '2026-01-03']

    def test_week(self, d):
        assert d.getDateRange(start='2026-01-01', periods=3, freq='W') == [
            '2026-01-01', '2026-01-08', '2026-01-15']

    def test_day_end_periods(self, d):
        assert d.getDateRange(end='2026-01-05', periods=3) == [
            '2026-01-03', '2026-01-04', '2026-01-05']

    def test_invalid_freq(self, d):
        with pytest.raises(ValueError) as ei:
            d.getDateRange(start='2026-01-01', periods=2, freq='X')
        assert "freq 只支持" in str(ei.value)

    def test_neither_end_nor_periods(self, d):
        with pytest.raises(ValueError):
            d.getDateRange(start='2026-01-01')

class TestGetDateRangeEx:
    """BUG-390：getDateRangeEx 三者同给时同样静默忽略 periods。"""

    def test_three_given_rejected(self):
        d = VDate('2026-01-15')
        with pytest.raises(ValueError) as ei:
            d.getDateRangeEx(start='2026-01-01', end='2026-01-05', periods=2)
        assert 'periods' in str(ei.value)

    def test_order_swapped(self):
        d = VDate('2026-01-15')
        # 文档承诺「自动调整 start/end 顺序，返回从早到晚」
        assert d.getDateRangeEx(start='2026-01-05', end='2026-01-01') == [
            '2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05']

    def test_two_given_ok(self):
        d = VDate('2026-01-15')
        assert d.getDateRangeEx(start='2026-01-01', periods=2) == [
            '2026-01-01', '2026-01-02']
        assert d.getDateRangeEx(end='2026-01-05', periods=2) == [
            '2026-01-04', '2026-01-05']

    def test_month_anchor_applies(self):
        d = VDate('2026-01-15')
        assert d.getDateRangeEx(start='2026-01-31', periods=3, freq='M') == [
            '2026-01-31', '2026-02-28', '2026-03-31']

    def test_none_rejected(self):
        d = VDate('2026-01-15')
        with pytest.raises(ValueError):
            d.getDateRangeEx()
