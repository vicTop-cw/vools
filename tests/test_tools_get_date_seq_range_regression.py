# -*- coding: utf-8 -*-
"""回归测试：get_date_seq 的周/月区间端日（BUG-335）。

`_generate_date_range` 返回 `dates[::-1]`（**最旧在前**），而 `get_date_seq`
的 week/month 分支曾写成：

    for i, d in enumerate(dss):
        start_date = d - timedelta(days=6)      # 周；月为 d.replace(day=1)
        end_date = d if i > 0 else run_date     # ← i==0 是最旧那一项

于是「最旧周期」的结束日被错设为基准日 `run_ds`，产出跨多周期的超长区间，
最新周期还可能给出**未来**结束日：

    run_ds='2026-01-15', nums=3, duo=True
    week  -> ['0112-0118', '0105-0111', '1229-0115']   # '1229-0115' 跨 3 周
    month -> ['0101-0131', '1201-1231', '1101-0115']   # '1101-0115' 应为 11-30

修复：只把**包含 run_date 的那个周期**截到 run_date，其余周期用自然周期末
（周：周日；月：月末）。day 分支不受影响（日周期 start==end）。
"""

import pytest

from vools.utils.tools import get_date_seq


class TestWeekSequences:
    def test_chronological_order(self):
        seq = get_date_seq(nums=3, date_type='week', run_ds='2026-01-15',
                           reverse=False)
        # 当前周（01-12..01-18）截到基准日 01-15；历史周用自然周期末
        assert seq == ['1229-0104', '0105-0111', '0112-0115']

    def test_reversed_order(self):
        seq = get_date_seq(nums=3, date_type='week', run_ds='2026-01-15')
        assert seq == ['0112-0115', '0105-0111', '1229-0104']

    def test_no_future_end_dates(self):
        # 修复前最新一项结束日是 01-18（基准日之后）
        seq = get_date_seq(nums=3, date_type='week', run_ds='2026-01-15',
                           duo=False, reverse=False)
        assert seq == ['0104', '0111', '0115']

    def test_sunday_run_date(self):
        seq = get_date_seq(nums=2, date_type='week', run_ds='2026-01-18',
                           reverse=False)
        assert seq == ['0105-0111', '0112-0118']

    def test_no_span_over_multiple_weeks(self):
        seq = get_date_seq(nums=4, date_type='week', run_ds='2026-01-15',
                           reverse=False)
        assert len(seq) == 4
        assert all(part.count('-') == 1 for part in seq)


class TestMonthSequences:
    def test_chronological_order(self):
        seq = get_date_seq(nums=3, date_type='month', run_ds='2026-01-15',
                           reverse=False)
        assert seq == ['1101-1130', '1201-1231', '0101-0115']

    def test_no_duo(self):
        seq = get_date_seq(nums=3, date_type='month', run_ds='2026-01-15',
                           duo=False, reverse=False)
        assert seq == ['1130', '1231', '0115']

    def test_year_boundary(self):
        seq = get_date_seq(nums=2, date_type='month', run_ds='2026-12-10',
                           reverse=False)
        assert seq == ['1101-1130', '1201-1210']

    def test_month_end_run_date(self):
        seq = get_date_seq(nums=2, date_type='month', run_ds='2026-01-31',
                           reverse=False)
        assert seq == ['1201-1231', '0101-0131']


class TestDayUnchanged:
    def test_day(self):
        seq = get_date_seq(nums=3, date_type='day', run_ds='2026-01-15',
                           reverse=False)
        assert seq == ['0113-0113', '0114-0114', '0115-0115']

    def test_day_no_duo(self):
        seq = get_date_seq(nums=3, date_type='day', run_ds='2026-01-15',
                           duo=False, reverse=False)
        assert seq == ['0113', '0114', '0115']

    def test_nums_zero(self):
        assert get_date_seq(nums=0, date_type='day', run_ds='2026-01-15') == []


class TestEdgeCases:
    @pytest.mark.parametrize('date_type', ['week', 'month'])
    def test_nums_one(self, date_type):
        seq = get_date_seq(nums=1, date_type=date_type, run_ds='2026-01-15',
                           reverse=False)
        assert len(seq) == 1
        assert seq[0].endswith('0115')      # 唯一周期即当前周期，截到基准日

    def test_invalid_run_ds_raises(self):
        with pytest.raises(ValueError):
            get_date_seq(nums=2, date_type='day', run_ds='not-a-date')