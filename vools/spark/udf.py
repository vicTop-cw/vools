"""
vools.spark.udf — Spark UDF 注册中心

分类组织三类内置 UDF：
  - 日期 UDF：vDate / days_gap / weeks_gap / months_gap /
              get_recently_days / get_recently_weeks / get_recently_months /
              get_dates / get_week / get_month
  - JSON UDF：extract_json_keys（提取 JSON 顶层 key 列表）
  - 数组 UDF：array_sum（LongType 元素求和）

用法：
    from vools.spark.udf import register_all_udfs
    register_all_udfs(spark)
"""

from __future__ import absolute_import

__all__ = [
    # 日期 UDF
    "vDate_udf",
    "days_gap_udf",
    "weeks_gap_udf",
    "months_gap_udf",
    "get_recently_days_udf",
    "get_recently_weeks_udf",
    "get_recently_months_udf",
    "get_dates_udf",
    "get_week_udf",
    "get_month_udf",
    # JSON UDF
    "extract_json_keys_udf",
    # 数组 UDF
    "array_sum_udf",
    # 统一入口
    "register_all_udfs",
]

import json as _json

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StringType,
    IntegerType,
    ArrayType,
    LongType,
)


# ============================================================================
# 一、日期 UDF（纯 Python 实现，不依赖 vools 核心库）
# ============================================================================

def _vDate_native(dt, fmt=None, diff_days=0):
    """vDate 纯 Python 实现。"""
    from datetime import datetime, timedelta
    import re

    if isinstance(diff_days, str) or isinstance(fmt, (float, int)):
        diff_days, fmt = fmt, diff_days
        if not isinstance(fmt, (str, type(None))):
            fmt = None

    if fmt is None:
        if isinstance(dt, (int, float)):
            fmt = '%Y-%m-%d %H:%M:%S'
        elif isinstance(dt, str):
            fmt = '%Y-%m-%d' if '-' in dt else '%Y%m%d'
            if ":" in dt:
                fmt = f"{fmt} %H:%M:%S"
        else:
            fmt = '%Y-%m-%d %H:%M:%S'

    if '%' not in fmt:
        fmt = (fmt.replace('yyyy', '%Y').replace('MM', '%m')
               .replace('dd', '%d').replace('mm', '%M').replace('HH', '%H')
               .replace('YYYY', '%Y').replace('SS', '%S')
               .replace('ss', '%S').replace('yy', '%y'))

    if dt is None:
        result = datetime.now()
        if diff_days != 0:
            result += timedelta(days=diff_days)
        return result.strftime(fmt)

    if isinstance(dt, (int, float)):
        result = datetime.fromtimestamp(dt)
    elif isinstance(dt, str):
        if len(dt) == 8 and dt.isdigit():
            result = datetime(int(dt[:4]), int(dt[4:6]), int(dt[6:]))
        elif re.search(r'^\d{4}-\d{2}-\d{2}$', dt):
            d = dt.replace('-', '')
            result = datetime(int(d[:4]), int(d[4:6]), int(d[6:]))
        else:
            result = datetime.strptime(dt, fmt)
    elif isinstance(dt, datetime):
        result = dt
    else:
        return None

    if diff_days != 0:
        result += timedelta(days=diff_days)
    return result.strftime(fmt)


def _get_week_native(dt, num=0, weekday=1):
    """get_week 纯 Python 实现。"""
    from datetime import datetime, timedelta
    if dt is None:
        return None
    if num is None:
        num = 0
    if not (1 <= weekday <= 7):
        return None
    dt = str(dt)[:10].strip()
    if len(dt) not in (8, 10):
        return None
    fmt = '%Y-%m-%d' if len(dt) == 10 else '%Y%m%d'
    try:
        d = datetime.strptime(dt, fmt)
    except ValueError:
        return None
    w0 = d - timedelta(days=(int(d.strftime('%u')) - weekday))
    if num != 0:
        w0 -= timedelta(days=num * 7)
    return w0.strftime(fmt)


def _get_month_native(dt, num=0, is_lastday=False):
    """get_month 纯 Python 实现。"""
    from datetime import datetime
    import calendar
    if dt is None or num is None:
        return None
    dt = str(dt)[:10].strip()
    try:
        fmt = '%Y-%m-%d' if '-' in dt else '%Y%m%d'
        d = datetime.strptime(dt, fmt)
    except ValueError:
        return None

    year = d.year
    month = d.month
    total_months = year * 12 + month - 1 - num
    target_year = total_months // 12
    target_month = total_months % 12 + 1

    if is_lastday:
        last_day_num = calendar.monthrange(target_year, target_month)[1]
        result = datetime(target_year, target_month, last_day_num)
    else:
        result = datetime(target_year, target_month, 1)
    return result.strftime(fmt)


def _days_gap_native(dt1, dt2):
    """days_gap 纯 Python 实现。"""
    from datetime import datetime
    if dt1 is None or dt2 is None:
        return None
    dt1 = str(dt1)[:10].strip()
    dt2 = str(dt2)[:10].strip()
    try:
        d1 = datetime.strptime(dt1, '%Y-%m-%d') if '-' in dt1 else datetime.strptime(dt1, '%Y%m%d')
        d2 = datetime.strptime(dt2, '%Y-%m-%d') if '-' in dt2 else datetime.strptime(dt2, '%Y%m%d')
        return (d1 - d2).days
    except (ValueError, TypeError):
        return None


def _weeks_gap_native(dt1, dt2):
    """weeks_gap 纯 Python 实现。"""
    from datetime import datetime, timedelta
    if dt1 is None or dt2 is None:
        return None
    dt1 = str(dt1)[:10].strip()
    dt2 = str(dt2)[:10].strip()
    try:
        d1 = datetime.strptime(dt1, '%Y-%m-%d') if '-' in dt1 else datetime.strptime(dt1, '%Y%m%d')
        d2 = datetime.strptime(dt2, '%Y-%m-%d') if '-' in dt2 else datetime.strptime(dt2, '%Y%m%d')
        monday1 = d1 - timedelta(days=d1.weekday())
        monday2 = d2 - timedelta(days=d2.weekday())
        return (monday1 - monday2).days // 7
    except (ValueError, TypeError):
        return None


def _months_gap_native(dt1, dt2):
    """months_gap 纯 Python 实现。"""
    from datetime import datetime
    if dt1 is None or dt2 is None:
        return None
    dt1 = str(dt1)[:10].strip()
    dt2 = str(dt2)[:10].strip()
    try:
        d1 = datetime.strptime(dt1, '%Y-%m-%d') if '-' in dt1 else datetime.strptime(dt1, '%Y%m%d')
        d2 = datetime.strptime(dt2, '%Y-%m-%d') if '-' in dt2 else datetime.strptime(dt2, '%Y%m%d')
        return (d1.year - d2.year) * 12 + (d1.month - d2.month)
    except (ValueError, TypeError):
        return None


def _get_recently_days_native(dt, num=13):
    """get_recently_days 纯 Python 实现。"""
    from datetime import datetime, timedelta
    if dt is None or num is None:
        return []
    fmt = "%Y%m%d" if len(str(dt)) == 8 else "%Y-%m-%d"
    try:
        d = datetime.strptime(str(dt), fmt)
    except ValueError:
        return []
    if num == 0:
        return [str(dt)]
    result = [str(dt)]
    abs_num = abs(num)
    for i in range(1, abs_num + 1):
        offset = i if num < 0 else -i
        result.append((d + timedelta(days=offset)).strftime(fmt))
    return result


def _get_recently_weeks_native(dt, num=13):
    """get_recently_weeks 纯 Python 实现。"""
    from datetime import datetime, timedelta
    if dt is None or num is None:
        return []
    fmt = "%Y%m%d" if len(str(dt)) == 8 else "%Y-%m-%d"
    try:
        d = datetime.strptime(str(dt), fmt)
    except ValueError:
        return []
    if num == 0:
        return [str(dt)]
    result = [str(dt)]
    abs_num = abs(num)
    weekday = d.weekday()
    for i in range(1, abs_num + 1):
        if num > 0:
            offset = -7 * i + (6 - weekday)
        else:
            offset = 7 * i - weekday
        result.append((d + timedelta(days=offset)).strftime(fmt))
    return result


def _get_recently_months_native(dt, num=11):
    """get_recently_months 纯 Python 实现。"""
    from datetime import datetime, timedelta
    if dt is None or num is None:
        return []
    fmt = "%Y%m%d" if len(str(dt)) == 8 else "%Y-%m-%d"
    try:
        d = datetime.strptime(str(dt), fmt)
    except ValueError:
        return []
    if num == 0:
        return [str(dt)]
    result = [str(dt)]
    abs_num = abs(num)
    year, month = d.year, d.month
    for i in range(1, abs_num + 1):
        if num > 0:
            tm = month - i
            ty = year + (tm - 1) // 12
            tm = (tm - 1) % 12 + 1
        else:
            tm = month + i
            ty = year + (tm - 1) // 12
            tm = (tm - 1) % 12 + 1
        if tm == 12:
            next_m = datetime(ty + 1, 1, 1)
        else:
            next_m = datetime(ty, tm + 1, 1)
        last_day = next_m - timedelta(days=1)
        result.append(last_day.strftime(fmt))
    return result


def _get_dates_native(dt, num=13, tp="d"):
    """get_dates 纯 Python 实现。"""
    from datetime import datetime, timedelta
    if dt is None or num is None:
        return []
    tp = tp[0].lower() if tp else 'd'
    fmt = "%Y%m%d" if len(str(dt)) == 8 else "%Y-%m-%d"
    try:
        d = datetime.strptime(str(dt), fmt)
    except ValueError:
        return []
    if num == 0:
        return [str(dt)]
    result = [str(dt)]
    abs_num = abs(num)

    if tp == 'd':
        for i in range(1, abs_num + 1):
            offset = i if num < 0 else -i
            result.append((d + timedelta(days=offset)).strftime(fmt))
    elif tp == 'w':
        weekday = d.weekday()
        for i in range(1, abs_num + 1):
            if num > 0:
                offset = -7 * i + (6 - weekday)
            else:
                offset = 7 * i - weekday
            result.append((d + timedelta(days=offset)).strftime(fmt))
    elif tp == 'm':
        year, month = d.year, d.month
        for i in range(1, abs_num + 1):
            if num > 0:
                tm = month - i
                ty = year + (tm - 1) // 12
                tm = (tm - 1) % 12 + 1
            else:
                tm = month + i
                ty = year + (tm - 1) // 12
                tm = (tm - 1) % 12 + 1
            if tm == 12:
                next_m = datetime(ty + 1, 1, 1)
            else:
                next_m = datetime(ty, tm + 1, 1)
            last_day = next_m - timedelta(days=1)
            result.append(last_day.strftime(fmt))
    return result


# Spark UDF 封装
vDate_udf = F.udf(_vDate_native, StringType())
days_gap_udf = F.udf(_days_gap_native, IntegerType())
weeks_gap_udf = F.udf(_weeks_gap_native, IntegerType())
months_gap_udf = F.udf(_months_gap_native, IntegerType())
get_recently_days_udf = F.udf(_get_recently_days_native, ArrayType(StringType()))
get_recently_weeks_udf = F.udf(_get_recently_weeks_native, ArrayType(StringType()))
get_recently_months_udf = F.udf(_get_recently_months_native, ArrayType(StringType()))
get_dates_udf = F.udf(_get_dates_native, ArrayType(StringType()))
get_week_udf = F.udf(_get_week_native, StringType())
get_month_udf = F.udf(_get_month_native, StringType())


# ============================================================================
# 二、JSON UDF
# ============================================================================

def _extract_json_keys_native(json_str):
    """从 JSON 字符串提取顶层 key 列表。"""
    if json_str is None:
        return None
    try:
        obj = _json.loads(json_str)
        if isinstance(obj, dict):
            return list(obj.keys())
        return []
    except (_json.JSONDecodeError, TypeError):
        return None


extract_json_keys_udf = F.udf(_extract_json_keys_native, ArrayType(StringType()))


# ============================================================================
# 三、数组 UDF
# ============================================================================

def _array_sum_native(arr):
    """LongType 数组元素求和。"""
    if arr is None:
        return None
    try:
        return sum(int(x) for x in arr if x is not None)
    except (TypeError, ValueError):
        return None


array_sum_udf = F.udf(_array_sum_native, LongType())


# ============================================================================
# 四、统一注册入口
# ============================================================================

_UDF_REGISTRY = {
    # 日期 UDF
    "vDate": vDate_udf,
    "days_gap": days_gap_udf,
    "weeks_gap": weeks_gap_udf,
    "months_gap": months_gap_udf,
    "get_recently_days": get_recently_days_udf,
    "get_recently_weeks": get_recently_weeks_udf,
    "get_recently_months": get_recently_months_udf,
    "get_dates": get_dates_udf,
    "get_week": get_week_udf,
    "get_month": get_month_udf,
    # JSON UDF
    "extract_json_keys": extract_json_keys_udf,
    # 数组 UDF
    "array_sum": array_sum_udf,
}


def register_all_udfs(spark):
    """一次性注册所有内置 UDF 到 SparkSession。

    参数:
        spark: pyspark.sql.SparkSession 实例
    """
    for name, udf_func in _UDF_REGISTRY.items():
        spark.udf.register(name, udf_func)