# -*- coding: utf-8 -*-
"""测试 vools.core.datetime_compat — datetime_fromisoformat 等。"""

import datetime
import sys
import pytest

__all__ = ["TestModernBranch", "TestImport"]


class TestModernBranch:
    """Python 3.7+ 分支。"""

    def test_datetime_full(self):
        from vools.core.datetime_compat import datetime_fromisoformat
        d = datetime_fromisoformat("2024-01-15T10:30:00")
        assert d == datetime.datetime(2024, 1, 15, 10, 30, 0)

    def test_datetime_with_micro(self):
        from vools.core.datetime_compat import datetime_fromisoformat
        d = datetime_fromisoformat("2024-01-15T10:30:00.123456")
        assert d.microsecond == 123456

    def test_datetime_date_only(self):
        from vools.core.datetime_compat import datetime_fromisoformat
        d = datetime_fromisoformat("2024-01-15")
        assert d == datetime.datetime(2024, 1, 15)

    def test_datetime_invalid(self):
        from vools.core.datetime_compat import datetime_fromisoformat
        with pytest.raises(ValueError):
            datetime_fromisoformat("bogus")

    def test_date_basic(self):
        from vools.core.datetime_compat import date_fromisoformat
        d = date_fromisoformat("2024-01-15")
        assert d == datetime.date(2024, 1, 15)

    def test_date_invalid(self):
        from vools.core.datetime_compat import date_fromisoformat
        with pytest.raises(ValueError):
            date_fromisoformat("bogus")

    def test_time_basic(self):
        from vools.core.datetime_compat import time_fromisoformat
        t = time_fromisoformat("10:30:00")
        assert t == datetime.time(10, 30, 0)

    def test_time_with_micro(self):
        from vools.core.datetime_compat import time_fromisoformat
        t = time_fromisoformat("10:30:00.5")
        assert t.microsecond == 500000

    def test_time_invalid(self):
        from vools.core.datetime_compat import time_fromisoformat
        with pytest.raises(ValueError):
            time_fromisoformat("bogus")

    def test_has_flag_true(self):
        import vools.core.datetime_compat as mod
        assert mod._HAS_FROMISOFORMAT is True


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.core.datetime_compat import __all__
        assert "datetime_fromisoformat" in __all__
        assert "date_fromisoformat" in __all__
        assert "time_fromisoformat" in __all__
