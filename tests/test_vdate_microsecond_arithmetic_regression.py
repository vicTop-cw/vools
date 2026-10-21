"""
回归测试：VDate.__add__/__sub__ 微秒保留（BUG-244）。

VDate 继承自 datetime.datetime，含微秒信息。原 __add__/__sub__ 构造
datetime(self.year, ..., self.second) 丢 self.microsecond → 微秒恒丢。
修复后保留 self.microsecond。
"""

import pytest
from datetime import datetime, timedelta
from vools.datetime import VDate


class TestVDateArithmeticMicrosecondPreservation:
    """BUG-244: VDate 算术保留微秒"""

    def test_add_int_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 123456))
        result = v + 1
        assert result.microsecond == 123456
        assert result.day == 2

    def test_add_timedelta_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 123456))
        result = v + timedelta(days=1)
        assert result.microsecond == 123456

    def test_add_timedelta_hours_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 500000))
        result = v + timedelta(hours=1)
        assert result.microsecond == 500000
        assert result.hour == 13

    def test_add_timedelta_seconds_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 999999))
        result = v + timedelta(seconds=30)
        assert result.microsecond == 999999
        assert result.second == 30

    def test_sub_int_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 123456))
        result = v - 1
        assert result.microsecond == 123456
        assert result.day == 31

    def test_sub_timedelta_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 123456))
        result = v - timedelta(days=1)
        assert result.microsecond == 123456

    def test_sub_timedelta_hours_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 500000))
        result = v - timedelta(hours=1)
        assert result.microsecond == 500000
        assert result.hour == 11

    def test_add_float_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 123456))
        result = v + 1.5
        assert result.microsecond == 123456

    def test_sub_float_preserves_microsecond(self):
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 123456))
        result = v - 1.5
        assert result.microsecond == 123456

    def test_sub_vdate_returns_float(self):
        """VDate - VDate 返回 float 天数差，使用 approx 应对微秒误差"""
        v1 = VDate(datetime(2024, 1, 15, 12, 0, 0, 100000))
        v2 = VDate(datetime(2024, 1, 1, 12, 0, 0, 200000))
        diff = v1 - v2
        # 含微秒差异时存在 <1s 浮点误差，用 approx 容差 1e-3 天
        assert diff == pytest.approx(14.0, abs=1e-3)

    def test_zero_microsecond_stays_zero(self):
        """微秒为 0 时保持为 0"""
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 0))
        result = v + 1
        assert result.microsecond == 0

    def test_fmt_preserved_with_microsecond(self):
        """fmt 与微秒都保留"""
        v = VDate(datetime(2024, 1, 1, 12, 0, 0, 123456), fmt='%Y-%m-%d %H:%M:%S.%f')
        result = v + timedelta(days=1)
        assert result.microsecond == 123456
        assert result.fmt == '%Y-%m-%d %H:%M:%S.%f'
        assert str(result) == '2024-01-02 12:00:00.123456'
