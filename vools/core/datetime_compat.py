"""
datetime 兼容层 — 统一处理 Python 不同版本的 datetime 接口

在高版本 Python 使用标准库 datetime 的原生接口，
在低版本（<3.7）提供兼容实现。

提供的兼容接口：
- datetime_fromisoformat(date_string)  → datetime.fromisoformat
- date_fromisoformat(date_string)      → date.fromisoformat
- time_fromisoformat(time_string)      → time.fromisoformat
"""

__all__ = [
    'datetime_fromisoformat',
    'date_fromisoformat',
    'time_fromisoformat',
]

import sys
import datetime

_HAS_FROMISOFORMAT = sys.version_info >= (3, 7)


if _HAS_FROMISOFORMAT:
    # ── 标准库 datetime（3.7+） ──

    def datetime_fromisoformat(date_string):
        """Python 3.7+ 的 datetime.fromisoformat"""
        return datetime.datetime.fromisoformat(date_string)

    def date_fromisoformat(date_string):
        """Python 3.7+ 的 date.fromisoformat"""
        return datetime.date.fromisoformat(date_string)

    def time_fromisoformat(time_string):
        """Python 3.7+ 的 time.fromisoformat"""
        return datetime.time.fromisoformat(time_string)

else:
    # ── Python 3.6 兼容实现 ──
    # 使用 strptime 解析常见的 ISO 格式

    import re

    _DATETIME_RE = re.compile(
        r'^(\d{4})-(\d{1,2})-(\d{1,2})'
        r'[T ](\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.(\d{1,6}))?)?'
        r'(Z|[+-]\d{2}:?\d{2})?$'
    )

    _DATE_RE = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})$')

    _TIME_RE = re.compile(
        r'^(\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.(\d{1,6}))?)?'
        r'(Z|[+-]\d{2}:?\d{2})?$'
    )

    def _parse_tzinfo(tz_part):
        """把 ISO 时区后缀解析为 tzinfo（BUG-242）。

        原实现虽在正则里允许 ``Z``/``±HH:MM`` 后缀，却从不构造 tzinfo ——
        带时区输入被静默当成本地 naive 时间：同一 UTC 时刻的两个值相减会
        得到 8 小时差（stdlib py3.7+ fromisoformat 保留时区、差值为 0）。
        """
        if not tz_part:
            return None
        if tz_part == 'Z':
            return datetime.timezone.utc
        sign = 1 if tz_part[0] == '+' else -1
        hh = int(tz_part[1:3])
        mm = int(tz_part[-2:])
        return datetime.timezone(sign * datetime.timedelta(hours=hh, minutes=mm))

    def datetime_fromisoformat(date_string):
        """
        兼容版 datetime.fromisoformat（Python 3.6）。

        支持常见的 ISO 8601 格式：
        - YYYY-MM-DDTHH:MM:SS
        - YYYY-MM-DD HH:MM:SS
        - 带微秒、不带秒等变体
        - 带时区后缀（``Z`` / ``±HH:MM``，BUG-242：返回 aware datetime）

        Args:
            date_string: ISO 格式的日期时间字符串。

        Returns:
            datetime.datetime 对象。

        Raises:
            ValueError: 如果字符串格式不支持。
        """
        if isinstance(date_string, datetime.datetime):
            return date_string

        s = str(date_string).strip()

        # 先尝试用 strptime 解析常见格式
        formats = [
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M',
        ]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(s, fmt)
            except ValueError:
                continue

        # 尝试用正则解析（含时区后缀，BUG-242）
        m = _DATETIME_RE.match(s)
        if m:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hour, minute = int(m.group(4)), int(m.group(5))
            second = int(m.group(6)) if m.group(6) else 0
            microsecond = 0
            if m.group(7):
                micro_str = m.group(7).ljust(6, '0')
                microsecond = int(micro_str)
            return datetime.datetime(
                year, month, day, hour, minute, second, microsecond,
                tzinfo=_parse_tzinfo(m.group(8)),
            )

        raise ValueError(
            'Invalid isoformat string: %r' % date_string
        )

    def date_fromisoformat(date_string):
        """
        兼容版 date.fromisoformat（Python 3.6）。

        Args:
            date_string: ISO 格式的日期字符串。

        Returns:
            datetime.date 对象。
        """
        if isinstance(date_string, datetime.date):
            return date_string

        s = str(date_string).strip()

        try:
            return datetime.datetime.strptime(s, '%Y-%m-%d').date()
        except ValueError:
            pass

        m = _DATE_RE.match(s)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        raise ValueError(
            'Invalid isoformat string: %r' % date_string
        )

    def time_fromisoformat(time_string):
        """
        兼容版 time.fromisoformat（Python 3.6）。

        支持常见时间格式与可选时区后缀（BUG-242：``10:30:00+08:00`` 返回
        aware time，与 stdlib py3.7+ 一致；原实现直接 ValueError）。

        Args:
            time_string: ISO 格式的时间字符串。

        Returns:
            datetime.time 对象。
        """
        if isinstance(time_string, datetime.time):
            return time_string

        s = str(time_string).strip()

        formats = [
            '%H:%M:%S.%f',
            '%H:%M:%S',
            '%H:%M',
        ]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(s, fmt).time()
            except ValueError:
                continue

        m = _TIME_RE.match(s)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            second = int(m.group(3)) if m.group(3) else 0
            microsecond = 0
            if m.group(4):
                micro_str = m.group(4).ljust(6, '0')
                microsecond = int(micro_str)
            return datetime.time(hour, minute, second, microsecond,
                                 tzinfo=_parse_tzinfo(m.group(5)))

        raise ValueError(
            'Invalid isoformat string: %r' % time_string
        )
