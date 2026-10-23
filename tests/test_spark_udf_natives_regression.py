# -*- coding: utf-8 -*-
"""回归测试：Spark 日期 UDF 的纯 Python 实现（含 datetime.date 输入，BUG-346）。

`vools.spark.udf` 顶层 `import pyspark`（环境未安装 pyspark 时无法导入），
本测试注入 fake `pyspark`（仅满足 udf/类型构造），从而直接测试纯 Python 实现。

BUG-346：`_vDate_native` 只接受 `datetime`，而 **Spark date 列给的是
`datetime.date`** —— 原实现落入 `else: return None`，整列静默变 null：

    _vDate_native(date(2026,1,15), '%Y%m%d')   # 修复前 -> None
                                              # 修复后 -> '20260115'

其余原生函数（week/month/gap/recently/dates/json/array）在本测试中固化语义。
"""

import datetime
import sys
import types

import pytest


@pytest.fixture(scope='module', autouse=True)
def _fake_pyspark():
    """注入最小 fake pyspark，使 vools.spark.udf 可导入。"""
    if 'pyspark' in sys.modules:
        yield
        return

    def udf(fn=None, ret=None):
        if callable(fn):
            return fn
        return lambda f: f

    funcs = types.ModuleType('pyspark.sql.functions')
    funcs.udf = udf
    types_mod = types.ModuleType('pyspark.sql.types')
    for name in ('StringType', 'IntegerType', 'ArrayType', 'LongType'):
        setattr(types_mod, name, lambda *a, **k: name)
    psql = types.ModuleType('pyspark.sql')
    psql.functions = funcs
    psql.types = types_mod
    ps = types.ModuleType('pyspark')
    ps.sql = psql
    sys.modules.update({
        'pyspark': ps,
        'pyspark.sql': psql,
        'pyspark.sql.functions': funcs,
        'pyspark.sql.types': types_mod,
    })
    yield


D = datetime.date(2026, 1, 15)
DT = datetime.datetime(2026, 1, 15, 13, 45, 30)


class TestVDateNative:
    def test_date_input(self):
        from vools.spark.udf import _vDate_native

        # 修复前：None（整列 null）
        assert _vDate_native(D, '%Y%m%d') == '20260115'
        assert _vDate_native(D, '%Y-%m-%d') == '2026-01-15'

    def test_date_with_diff_days(self):
        from vools.spark.udf import _vDate_native

        assert _vDate_native(D, '%Y%m%d', 5) == '20260120'
        assert _vDate_native(D, '%Y%m%d', -1) == '20260114'

    def test_datetime_input(self):
        from vools.spark.udf import _vDate_native

        assert _vDate_native(DT, '%Y-%m-%d %H:%M:%S') == '2026-01-15 13:45:30'

    def test_string_inputs(self):
        from vools.spark.udf import _vDate_native

        assert _vDate_native('20260115', '%Y%m%d') == '20260115'
        assert _vDate_native('2026-01-15', '%Y-%m-%d') == '2026-01-15'

    def test_java_style_format(self):
        from vools.spark.udf import _vDate_native

        assert _vDate_native(D, 'yyyyMMdd') == '20260115'

    def test_none_returns_today(self):
        from vools.spark.udf import _vDate_native

        today = datetime.date.today().strftime('%Y-%m-%d')
        assert _vDate_native(None, '%Y-%m-%d') == today

    def test_unsupported_returns_none(self):
        from vools.spark.udf import _vDate_native

        assert _vDate_native(object(), '%Y%m%d') is None


class TestWeekMonthNative:
    def test_week(self):
        from vools.spark.udf import _get_week_native

        assert _get_week_native(D) == '2026-01-12'      # 该周周一
        assert _get_week_native(D, 1) == '2026-01-05'   # 往前一周

    def test_month(self):
        from vools.spark.udf import _get_month_native

        assert _get_month_native(D) == '2026-01-01'              # 当月首日
        assert _get_month_native(D, is_lastday=True) == '2026-01-31'
        assert _get_month_native(datetime.date(2026, 12, 15), 1) == '2026-11-01'

    def test_invalid_input_returns_none(self):
        from vools.spark.udf import _get_week_native, _get_month_native

        assert _get_week_native(None) is None
        assert _get_month_native(None) is None
        assert _get_week_native('bad') is None


class TestGapsNative:
    def test_days_gap(self):
        from vools.spark.udf import _days_gap_native

        assert _days_gap_native(D, datetime.date(2026, 1, 10)) == 5
        assert _days_gap_native(datetime.date(2026, 1, 10), D) == -5
        assert _days_gap_native(D, D) == 0

    def test_weeks_gap(self):
        from vools.spark.udf import _weeks_gap_native

        assert _weeks_gap_native(D, datetime.date(2026, 1, 1)) == 2

    def test_months_gap(self):
        from vools.spark.udf import _months_gap_native

        assert _months_gap_native(datetime.date(2026, 3, 15),
                                  datetime.date(2026, 1, 15)) == 2


class TestSeriesNative:
    def test_recently_days(self):
        from vools.spark.udf import _get_recently_days_native

        # num = 额外期数（总数 = num + 1，含输入日）
        days = _get_recently_days_native(D, 3)
        assert days == ['2026-01-15', '2026-01-14', '2026-01-13', '2026-01-12']
        assert _get_recently_days_native(D, 0) == ['2026-01-15']

    def test_recently_months_month_ends(self):
        from vools.spark.udf import _get_recently_months_native

        months = _get_recently_months_native(D, 3)
        assert months == ['2026-01-15', '2025-12-31', '2025-11-30', '2025-10-31']

    def test_get_dates(self):
        from vools.spark.udf import _get_dates_native

        assert _get_dates_native(D, 2, 'd') == [
            '2026-01-15', '2026-01-14', '2026-01-13']
        assert _get_dates_native(D, 1, 'w') == ['2026-01-15', '2026-01-11']


class TestJsonArrayNative:
    def test_extract_json_keys(self):
        from vools.spark.udf import _extract_json_keys_native

        assert _extract_json_keys_native('{"a":1,"b":2}') == ['a', 'b']
        assert _extract_json_keys_native('not json') is None

    def test_array_sum(self):
        from vools.spark.udf import _array_sum_native

        assert _array_sum_native([1, 2, 3]) == 6
        assert _array_sum_native([1, None, 3]) == 4
        assert _array_sum_native(None) is None
        assert _array_sum_native([]) == 0