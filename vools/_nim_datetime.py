"""
vools/_nim_datetime.py
Nim 加速的日期操作 - 自动回退到 Python datetime
"""
from ._nim_loader import load_nim_lib
import ctypes

_nim_lib = load_nim_lib('vools_datetime')


def _setup_funcs():
    """设置函数签名"""
    if _nim_lib is None:
        return
    # bool
    _nim_lib.dt_is_leap_year.argtypes = [ctypes.c_int]
    _nim_lib.dt_is_leap_year.restype = ctypes.c_int
    _nim_lib.dt_validate_date.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_validate_date.restype = ctypes.c_int
    # int
    _nim_lib.dt_days_in_month.argtypes = [ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_days_in_month.restype = ctypes.c_int
    _nim_lib.dt_days_in_year.argtypes = [ctypes.c_int]
    _nim_lib.dt_days_in_year.restype = ctypes.c_int
    _nim_lib.dt_day_of_week.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_day_of_week.restype = ctypes.c_int
    _nim_lib.dt_week_of_year.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_week_of_year.restype = ctypes.c_int
    _nim_lib.dt_days_between.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_days_between.restype = ctypes.c_int
    # int64
    _nim_lib.dt_ymd_to_ts.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_ymd_to_ts.restype = ctypes.c_int64
    _nim_lib.dt_ts_to_ymd.argtypes = [ctypes.c_int64]
    _nim_lib.dt_ts_to_ymd.restype = ctypes.c_char_p
    _nim_lib.dt_ts_to_ymdhms.argtypes = [ctypes.c_int64]
    _nim_lib.dt_ts_to_ymdhms.restype = ctypes.c_char_p
    # cstring
    _nim_lib.dt_range_days.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_range_days.restype = ctypes.c_char_p
    _nim_lib.dt_range_days_between.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                                ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_range_days_between.restype = ctypes.c_char_p
    _nim_lib.dt_range_months.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_range_months.restype = ctypes.c_char_p
    _nim_lib.dt_add_days.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_add_days.restype = ctypes.c_char_p
    _nim_lib.dt_add_months.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _nim_lib.dt_add_months.restype = ctypes.c_char_p


_setup_funcs()
_USE_NIM = _nim_lib is not None


# ============================================================
# Python 回退
# ============================================================
import calendar
from datetime import date, datetime, timedelta

def _py_is_leap_year(year):
    return calendar.isleap(year)

def _py_days_in_month(year, month):
    return calendar.monthrange(year, month)[1]

def _py_days_in_year(year):
    return 366 if calendar.isleap(year) else 365

def _py_timestamp_to_ymd(ts):
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')

def _py_timestamp_to_ymdhms(ts):
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def _py_ymd_to_timestamp(year, month, day):
    return int(datetime(year, month, day).timestamp())

def _py_days_between(y1, m1, d1, y2, m2, d2):
    return (date(y2, m2, d2) - date(y1, m1, d1)).days

def _py_day_of_week(year, month, day):
    return date(year, month, day).isoweekday()

def _py_week_of_year(year, month, day):
    return date(year, month, day).isocalendar()[1]

def _py_range_days(start_y, start_m, start_d, count):
    return [(date(start_y, start_m, start_d) + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(count)]

def _py_range_days_between(y1, m1, d1, y2, m2, d2):
    total = (date(y2, m2, d2) - date(y1, m1, d1)).days + 1
    if total <= 0:
        return []
    return [(date(y1, m1, d1) + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(total)]

def _py_range_months(start_y, start_m, count):
    result = []
    y, m = start_y, start_m
    for _ in range(count):
        result.append(f'{y:04d}-{m:02d}')
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result

def _py_validate_date(year, month, day):
    try:
        date(year, month, day)
        return True
    except (ValueError, TypeError):
        return False

def _py_add_days(year, month, day, delta):
    return (date(year, month, day) + timedelta(days=delta)).strftime('%Y-%m-%d')

def _py_add_months(year, month, day, delta):
    total = year * 12 + (month - 1) + delta
    new_y, new_m = divmod(total, 12)
    new_m += 1
    max_d = calendar.monthrange(new_y, new_m)[1]
    new_d = min(day, max_d)
    return f'{new_y:04d}-{new_m:02d}-{new_d:02d}'


# ============================================================
# Nim 包装
# ============================================================
def _nim_is_leap_year(year):
    return bool(_nim_lib.dt_is_leap_year(year))

def _nim_days_in_month(year, month):
    return _nim_lib.dt_days_in_month(year, month)

def _nim_days_in_year(year):
    return _nim_lib.dt_days_in_year(year)

def _nim_timestamp_to_ymd(ts):
    return _nim_lib.dt_ts_to_ymd(ts).decode('utf-8')

def _nim_timestamp_to_ymdhms(ts):
    return _nim_lib.dt_ts_to_ymdhms(ts).decode('utf-8')

def _nim_ymd_to_timestamp(year, month, day):
    return _nim_lib.dt_ymd_to_ts(year, month, day)

def _nim_days_between(y1, m1, d1, y2, m2, d2):
    return _nim_lib.dt_days_between(y1, m1, d1, y2, m2, d2)

def _nim_day_of_week(year, month, day):
    return _nim_lib.dt_day_of_week(year, month, day)

def _nim_week_of_year(year, month, day):
    return _nim_lib.dt_week_of_year(year, month, day)

def _nim_range_days(start_y, start_m, start_d, count):
    s = _nim_lib.dt_range_days(start_y, start_m, start_d, count).decode('utf-8')
    return s.split(',') if s else []

def _nim_range_days_between(y1, m1, d1, y2, m2, d2):
    s = _nim_lib.dt_range_days_between(y1, m1, d1, y2, m2, d2).decode('utf-8')
    return s.split(',') if s else []

def _nim_range_months(start_y, start_m, count):
    s = _nim_lib.dt_range_months(start_y, start_m, count).decode('utf-8')
    return s.split(',') if s else []

def _nim_validate_date(year, month, day):
    return bool(_nim_lib.dt_validate_date(year, month, day))

def _nim_add_days(year, month, day, delta):
    return _nim_lib.dt_add_days(year, month, day, delta).decode('utf-8')

def _nim_add_months(year, month, day, delta):
    return _nim_lib.dt_add_months(year, month, day, delta).decode('utf-8')


# ============================================================
# 公开 API
# ============================================================

is_leap_year = _nim_is_leap_year if _USE_NIM else _py_is_leap_year
days_in_month = _nim_days_in_month if _USE_NIM else _py_days_in_month
days_in_year = _nim_days_in_year if _USE_NIM else _py_days_in_year
timestamp_to_ymd = _nim_timestamp_to_ymd if _USE_NIM else _py_timestamp_to_ymd
timestamp_to_ymdhms = _nim_timestamp_to_ymdhms if _USE_NIM else _py_timestamp_to_ymdhms
ymd_to_timestamp = _nim_ymd_to_timestamp if _USE_NIM else _py_ymd_to_timestamp
days_between = _nim_days_between if _USE_NIM else _py_days_between
day_of_week = _nim_day_of_week if _USE_NIM else _py_day_of_week
week_of_year = _nim_week_of_year if _USE_NIM else _py_week_of_year
range_days = _nim_range_days if _USE_NIM else _py_range_days
range_days_between = _nim_range_days_between if _USE_NIM else _py_range_days_between
range_months = _nim_range_months if _USE_NIM else _py_range_months
validate_date = _nim_validate_date if _USE_NIM else _py_validate_date
add_days = _nim_add_days if _USE_NIM else _py_add_days
add_months = _nim_add_months if _USE_NIM else _py_add_months


def is_nim_datetime_available():
    return _USE_NIM
