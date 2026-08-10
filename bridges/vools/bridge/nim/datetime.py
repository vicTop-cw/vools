"""
vools.bridge.nim.datetime - Nim 日期时间函数桥接
"""

from datetime import date

from ._loader import get_nim_lib

_nim_lib = get_nim_lib('vools_datetime')


# Python 回退实现
def _py_is_leap_year(year):
    return int((year % 4 == 0 and year % 100 != 0) or (year % 400 == 0))


def _py_days_in_month(year, month):
    return [0, 31, 29 if _py_is_leap_year(year) else 28, 31, 30, 31,
            30, 31, 31, 30, 31, 30, 31][month]


def _py_days_in_year(year):
    return 366 if _py_is_leap_year(year) else 365


def _py_day_of_week(year, month, day):
    return date(year, month, day).weekday()


def _py_week_of_year(year, month, day):
    return date(year, month, day).isocalendar()[1]


def _py_days_between(y1, m1, d1, y2, m2, d2):
    d1 = date(y1, m1, d1)
    d2 = date(y2, m2, d2)
    return (d2 - d1).days


def _py_ymd_to_ts(year, month, day):
    from time import mktime
    return int(mktime(date(year, month, day).timetuple()))


def _py_ts_to_ymd(ts):
    from time import gmtime
    t = gmtime(ts)
    return f"{t.tm_year},{t.tm_mon},{t.tm_mday}"


def _py_ts_to_ymdhms(ts):
    from time import gmtime
    t = gmtime(ts)
    return f"{t.tm_year},{t.tm_mon},{t.tm_mday},{t.tm_hour},{t.tm_min},{t.tm_sec}"


def _py_range_days(year, month, day, count):
    d = date(year, month, day)
    result = []
    from datetime import timedelta
    for i in range(count):
        result.append(f"{d.year},{d.month},{d.day}")
        d += timedelta(days=1)
    return ','.join(result)


def _py_range_days_between(y1, m1, d1, y2, m2, d2):
    d1 = date(y1, m1, d1)
    d2 = date(y2, m2, d2)
    result = []
    from datetime import timedelta
    while d1 <= d2:
        result.append(f"{d1.year},{d1.month},{d1.day}")
        d1 += timedelta(days=1)
    return ','.join(result)


def _py_range_months(year, month, count):
    result = []
    y, m = year, month
    for _ in range(count):
        result.append(f"{y},{m},1")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return ','.join(result)


def _py_validate_date(year, month, day):
    try:
        date(year, month, day)
        return 1
    except ValueError:
        return 0


def _py_add_days(year, month, day, days):
    d = date(year, month, day)
    from datetime import timedelta
    d += timedelta(days=days)
    return f"{d.year},{d.month},{d.day}"


def _py_add_months(year, month, day, months):
    y, m = year, month + months
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    try:
        d = date(y, m, day)
    except ValueError:
        d = date(y, m, _py_days_in_month(y, m))
    return f"{d.year},{d.month},{d.day}"


# Nim 实现
def _nim_is_leap_year(year):
    return _nim_lib.dt_is_leap_year(year)


def _nim_days_in_month(year, month):
    return _nim_lib.dt_days_in_month(year, month)


def _nim_days_in_year(year):
    return _nim_lib.dt_days_in_year(year)


def _nim_day_of_week(year, month, day):
    return _nim_lib.dt_day_of_week(year, month, day)


def _nim_week_of_year(year, month, day):
    return _nim_lib.dt_week_of_year(year, month, day)


def _nim_days_between(y1, m1, d1, y2, m2, d2):
    return _nim_lib.dt_days_between(y1, m1, d1, y2, m2, d2)


def _nim_ymd_to_ts(year, month, day):
    return _nim_lib.dt_ymd_to_ts(year, month, day)


def _nim_ts_to_ymd(ts):
    return _nim_lib.dt_ts_to_ymd(ts).decode('utf-8')


def _nim_ts_to_ymdhms(ts):
    return _nim_lib.dt_ts_to_ymdhms(ts).decode('utf-8')


def _nim_range_days(year, month, day, count):
    return _nim_lib.dt_range_days(year, month, day, count).decode('utf-8')


def _nim_range_days_between(y1, m1, d1, y2, m2, d2):
    return _nim_lib.dt_range_days_between(y1, m1, d1, y2, m2, d2).decode('utf-8')


def _nim_range_months(year, month, count):
    return _nim_lib.dt_range_months(year, month, count).decode('utf-8')


def _nim_validate_date(year, month, day):
    return _nim_lib.dt_validate_date(year, month, day)


def _nim_add_days(year, month, day, days):
    return _nim_lib.dt_add_days(year, month, day, days).decode('utf-8')


def _nim_add_months(year, month, day, months):
    return _nim_lib.dt_add_months(year, month, day, months).decode('utf-8')


# 公开 API
_USE_NIM = _nim_lib is not None

dt_is_leap_year = _nim_is_leap_year if _USE_NIM else _py_is_leap_year
dt_days_in_month = _nim_days_in_month if _USE_NIM else _py_days_in_month
dt_days_in_year = _nim_days_in_year if _USE_NIM else _py_days_in_year
dt_day_of_week = _nim_day_of_week if _USE_NIM else _py_day_of_week
dt_week_of_year = _nim_week_of_year if _USE_NIM else _py_week_of_year
dt_days_between = _nim_days_between if _USE_NIM else _py_days_between
dt_ymd_to_ts = _nim_ymd_to_ts if _USE_NIM else _py_ymd_to_ts
dt_ts_to_ymd = _nim_ts_to_ymd if _USE_NIM else _py_ts_to_ymd
dt_ts_to_ymdhms = _nim_ts_to_ymdhms if _USE_NIM else _py_ts_to_ymdhms
dt_range_days = _nim_range_days if _USE_NIM else _py_range_days
dt_range_days_between = _nim_range_days_between if _USE_NIM else _py_range_days_between
dt_range_months = _nim_range_months if _USE_NIM else _py_range_months
dt_validate_date = _nim_validate_date if _USE_NIM else _py_validate_date
dt_add_days = _nim_add_days if _USE_NIM else _py_add_days
dt_add_months = _nim_add_months if _USE_NIM else _py_add_months
