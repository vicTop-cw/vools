# -*- coding: utf-8 -*-
"""回归测试：VDate.getDateRange 的非法 freq 不再挂死/静默重复（BUG-368）。

`_generate_date_range` 内部三个分支都用 `if freq == 'D' / 'W' / 'M'` 推进日期，
**没有任何兜底**。于是 freq 非法时：

- `periods` 分支：current 从不推进 → 静默返回 periods 个**重复日期**
  （`getDateRange(start='2026-01-01', periods=3, freq='X')` → 三个相同日期）；
- `start + end` 分支：`while current <= end_date` **无限循环**，进程挂死
  （实测 8s 超时未返回）；
- 小写 `'d'/'w'/'m'` 同样触发（比较区分大小写）。

修复：进入分支前规范化并校验 freq（大小写不敏感，仅 D/W/M），非法即 ValueError。
`getDateRangeEx` 复用同一助手，一并修复。
"""

import pytest

from vools.datetime.vdate_class import VDate


@pytest.fixture()
def d():
    return VDate('2026-01-15')


class TestValidFreq:
    @pytest.mark.parametrize('freq', ['D', 'd'])
    def test_daily(self, d, freq):
        assert d.getDateRange(start='2026-01-01', periods=3, freq=freq) == [
            '2026-01-01', '2026-01-02', '2026-01-03']

    @pytest.mark.parametrize('freq', ['W', 'w'])
    def test_weekly(self, d, freq):
        assert d.getDateRange(start='2026-01-01', periods=2, freq=freq) == [
            '2026-01-01', '2026-01-08']

    @pytest.mark.parametrize('freq', ['M', 'm'])
    def test_monthly(self, d, freq):
        assert d.getDateRange(start='2026-01-01', periods=2, freq=freq) == [
            '2026-01-01', '2026-02-01']

    def test_start_end_inclusive(self, d):
        assert d.getDateRange(start='2026-01-15', end='2026-01-17') == [
            '2026-01-15', '2026-01-16', '2026-01-17']

    def test_weekly_with_end(self, d):
        assert d.getDateRange(start='2026-01-01', end='2026-01-15', freq='W') == [
            '2026-01-01', '2026-01-08', '2026-01-15']


class TestInvalidFreqRejected:
    @pytest.mark.parametrize('freq', ['X', 'Q', 'days', '', '月'])
    def test_periods_branch(self, d, freq):
        # 修复前：静默返回重复日期
        with pytest.raises(ValueError) as ei:
            d.getDateRange(start='2026-01-01', periods=3, freq=freq)
        assert 'freq' in str(ei.value)

    @pytest.mark.parametrize('freq', ['X', 'Q'])
    def test_start_end_branch_no_hang(self, d, freq):
        # 修复前：无限循环（进程挂死）
        with pytest.raises(ValueError):
            d.getDateRange(start='2026-01-01', end='2026-01-05', freq=freq)

    def test_none_freq(self, d):
        with pytest.raises(ValueError):
            d.getDateRange(start='2026-01-01', periods=2, freq=None)

    def test_range_ex_also_validated(self, d):
        with pytest.raises(ValueError):
            d.getDateRangeEx(start='2026-01-01', periods=2, freq='Q')


class TestOtherVDateOpsUnchanged:
    def test_add_months_clamp(self):
        assert str(VDate('2026-01-31').add_months(1)) == '2026-02-28'

    def test_add_years_leap(self):
        assert str(VDate('2024-02-29').add_years(1)) == '2025-02-28'

    def test_get_week_month(self):
        d = VDate('2026-01-15')
        assert d.get_week() == '2026-01-12'
        assert d.get_month() == '2026-01-01'
        assert d.get_month(last_day=True) == '2026-01-31'

    def test_simplify(self):
        ranges = VDate('2026-01-15').simplify(['20260101', '20260102', '20260105'])
        assert [(r.start, r.end, r.cnt) for r in ranges] == [
            ('2026-01-01', '2026-01-02', 2), ('2026-01-05', '2026-01-05', 1)]