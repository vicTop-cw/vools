"""
vools/_nim_datetime.py (Deprecated)

This module is deprecated and will be removed in a future version.
Use vools.bridge.nim.datetime instead.
"""

import warnings

warnings.warn(
    "vools._nim_datetime is deprecated, use vools.bridge.nim.datetime instead",
    DeprecationWarning,
    stacklevel=2
)

from .bridge.nim.datetime import (
    dt_is_leap_year, dt_days_in_month, dt_days_in_year, dt_day_of_week,
    dt_week_of_year, dt_days_between, dt_ymd_to_ts, dt_ts_to_ymd,
    dt_ts_to_ymdhms, dt_range_days, dt_range_days_between, dt_range_months,
    dt_validate_date, dt_add_days, dt_add_months,
)

def is_nim_datetime_available():
    from .bridge.nim._loader import is_nim_available as _is_avail
    return _is_avail()
