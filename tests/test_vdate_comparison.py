# -*- coding: utf-8 -*-
"""回归测试：VDate 比较运算与 .date() 契约。

覆盖 BUG-199（__lt__/__eq__ 用被 @rself 包装的 .date() 做 VDate<VDate 比较，
触发 VDate.__new__ TypeError）与 BUG-200（VDate.date() 本身崩溃）。
"""

from datetime import date, datetime, timedelta

import pytest

from vools.datetime.vdate_class import VDate


class TestVDateComparison:
    """VDate 对象间比较不得崩溃，且方向正确（BUG-199）。"""

    def test_lt_vdate(self):
        a = VDate("2024-01-01")
        b = VDate("2023-06-15")
        assert (b < a) is True
        assert (a < b) is False

    def test_all_comparators_vdate(self):
        a = VDate("2024-01-01")
        b = VDate("2023-06-15")
        assert (a > b) is True
        assert (a >= b) is True
        assert (a >= VDate("2024-01-01")) is True
        assert (a <= b) is False
        assert (b <= a) is True

    def test_eq_vdate(self):
        assert (VDate("2024-01-01") == VDate("2024-01-01")) is True
        assert (VDate("2024-01-01") == VDate("2024-01-02")) is False
        assert (VDate("2024-01-01") != VDate("2024-01-02")) is True

    def test_comparators_vs_str(self):
        a = VDate("2024-01-01")
        assert (a > "2023-01-01") is True
        assert (a == "2024-01-01") is True
        assert (a < "2025-01-01") is True

    def test_comparators_vs_date_datetime(self):
        a = VDate("2024-01-01")
        assert (a > date(2023, 1, 1)) is True
        assert (a > datetime(2023, 1, 1)) is True
        assert (a == datetime(2024, 1, 1)) is True

    def test_sorted_vdate_list(self):
        items = [VDate("2024-01-01"), VDate("2023-06-15"), VDate("2025-05-05")]
        ordered = sorted(items)
        assert ordered[0].strftime("%Y-%m-%d") == "2023-06-15"
        assert ordered[1].strftime("%Y-%m-%d") == "2024-01-01"
        assert ordered[2].strftime("%Y-%m-%d") == "2025-05-05"


class TestVDateDateContract:
    """VDate.date() 必须返回原生 datetime.date，不得崩溃（BUG-200）。"""

    def test_date_returns_native_date(self):
        d = VDate("2024-01-01").date()
        assert isinstance(d, date)
        assert not isinstance(d, VDate)
        assert (d.year, d.month, d.day) == (2024, 1, 1)

    def test_rself_chain_still_works(self):
        # 排除 .date() 不影响其他 @rself 方法的链式包装
        a = VDate("2024-01-01")
        nxt = a + timedelta(days=1)
        assert isinstance(nxt, VDate)
        assert nxt.strftime("%Y-%m-%d") == "2024-01-02"