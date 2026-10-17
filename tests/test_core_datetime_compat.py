# -*- coding: utf-8 -*-
"""测试 vools.core.datetime_compat（3.13 走标准库分支）。"""

import pytest
from datetime import datetime, date, time
from vools.core.datetime_compat import (
    datetime_fromisoformat, date_fromisoformat, time_fromisoformat,
    _HAS_FROMISOFORMAT
)

__all__ = ["TestDatetime", "TestDate", "TestTime", "TestFlag", "TestImport"]


class TestDatetime:
    """datetime_fromisoformat 测试。"""

    def test_basic(self):
        assert datetime_fromisoformat("2024-01-02T13:45:30") == datetime(2024, 1, 2, 13, 45, 30)

    def test_space(self):
        assert datetime_fromisoformat("2024-01-02 13:45:30") == datetime(2024, 1, 2, 13, 45, 30)

    def test_fractional(self):
        assert datetime_fromisoformat("2024-01-02T13:45:30.123456") == datetime(2024, 1, 2, 13, 45, 30, 123456)

    def test_datetime_input(self):
        # 3.7+ 标准库分支不接受 datetime 对象
        dt = datetime(2024, 1, 2)
        with pytest.raises(TypeError):
            datetime_fromisoformat(dt)


class TestDate:
    """date_fromisoformat 测试。"""

    def test_basic(self):
        assert date_fromisoformat("2024-01-02") == date(2024, 1, 2)

    def test_date_input(self):
        d = date(2024, 1, 2)
        with pytest.raises(TypeError):
            date_fromisoformat(d)


class TestTime:
    """time_fromisoformat 测试。"""

    def test_basic(self):
        assert time_fromisoformat("13:45:30") == time(13, 45, 30)

    def test_time_input(self):
        t = time(13, 45)
        with pytest.raises(TypeError):
            time_fromisoformat(t)


class TestFlag:
    """版本标志测试。"""

    def test_flag(self):
        assert _HAS_FROMISOFORMAT is True


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.core.datetime_compat import __all__
        assert "datetime_fromisoformat" in __all__
        assert "date_fromisoformat" in __all__
        assert "time_fromisoformat" in __all__
