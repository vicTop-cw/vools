"""
回归测试：vDate() / VDate() 解析含毫秒/微秒的字符串（BUG-245）。

'2024-01-01 12:30:45.123456' 和 '20240101 12:30:45.123' 应正确解析，
原实现正则不带 ``(?:\.\d+)?`` 小数秒 → 落到 else 走 strptime 报 unconverted。
"""

import pytest
from datetime import datetime
from vools.datetime import vDate, VDate


class TestVDateStringMicrosecond:
    """BUG-245: vDate() 解析毫秒/微秒字符串"""

    def test_standard_datetime_microseconds(self):
        result = vDate('2024-01-01 12:30:45.123456')
        assert result == '2024-01-01 12:30:45'

    def test_standard_datetime_milliseconds(self):
        result = vDate('2024-01-01 12:30:45.123')
        assert result == '2024-01-01 12:30:45'

    def test_compact_datetime_microseconds(self):
        result = vDate('20240101 12:30:45.123456')
        assert result == '20240101 12:30:45'

    def test_compact_datetime_milliseconds(self):
        result = vDate('20240101 12:30:45.123')
        assert result == '20240101 12:30:45'

    def test_no_fractional_seconds_unchanged(self):
        """无小数秒的格式不变"""
        assert vDate('2024-01-01 12:30:45') == '2024-01-01 12:30:45'
        assert vDate('20240101 12:30:45') == '20240101 12:30:45'

    def test_fractional_with_fmt_output(self):
        """指定带 %f 的 fmt 输出保留微秒"""
        result = vDate('2024-01-01 12:30:45.123456', fmt='%Y-%m-%d %H:%M:%S.%f')
        # vDate 走解析分支时只取整数秒，小数秒被截断
        assert result == '2024-01-01 12:30:45.123456'

    def test_zero_fractional(self):
        """.0 小数秒不崩溃"""
        result = vDate('2024-01-01 12:30:45.0')
        assert result == '2024-01-01 12:30:45'


class TestVDateClassMicrosecond:
    """BUG-245: VDate() 解析毫秒/微秒字符串"""

    def test_vdate_standard_microseconds(self):
        v = VDate('2024-01-01 12:30:45.123456')
        assert v.year == 2024 and v.month == 1 and v.day == 1
        assert v.hour == 12 and v.minute == 30 and v.second == 45
        assert v.microsecond == 123456

    def test_vdate_standard_milliseconds(self):
        v = VDate('2024-01-01 12:30:45.123')
        assert v.microsecond == 123000

    def test_vdate_compact_microseconds(self):
        v = VDate('20240101 12:30:45.123456')
        assert v.microsecond == 123456

    def test_vdate_compact_milliseconds(self):
        v = VDate('20240101 12:30:45.123')
        assert v.microsecond == 123000

    def test_vdate_no_fractional(self):
        v = VDate('2024-01-01 12:30:45')
        assert v.microsecond == 0

    def test_vdate_str_representation_with_microsecond(self):
        v = VDate('2024-01-01 12:30:45.123456', fmt='%Y-%m-%d %H:%M:%S.%f')
        assert str(v) == '2024-01-01 12:30:45.123456'

    def test_vdate_fractional_edge_cases(self):
        """边界：1位/6位小数"""
        v1 = VDate('2024-01-01 12:00:00.1')
        assert v1.microsecond == 100000
        v6 = VDate('2024-01-01 12:00:00.123456')
        assert v6.microsecond == 123456
        v3 = VDate('2024-01-01 12:00:00.999')
        assert v3.microsecond == 999000
