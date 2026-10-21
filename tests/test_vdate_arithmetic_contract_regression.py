# -*- coding: utf-8 -*-
"""回归测试：VDate 算术运算符契约（BUG-241）。

① `__sub__` 的类型注解/docstring 承诺支持 `timedelta`（"timedelta 减法返回
新的 VDate 实例"），但实现缺该分支 → 落到 else 抛
`TypeError: 只能对整数和日期执行减法操作`；`__add__` 却支持 timedelta（不对称）。

② `__add__`/`__sub__` 用 datetime 构造结果 → `__init__` 对 datetime 输入默认
推断 `fmt='%Y-%m-%d %H:%M:%S'`，同一日期因构造路径不同 `str()` 不一致
（'2024-02-01' vs '2024-02-01 00:00:00'），而 `==` 为 True。

修复：`__sub__` 补 timedelta 分支；两运算符统一 `fmt=self.fmt` 沿用源实例格式。
`add_days`/`add_months`/`add_years` 原本就传字符串（fmt 推断 date-only）不受影响。
"""

from datetime import timedelta

import pytest

from vools.datetime.vdate_class import VDate


class TestSubTimedelta:
    """BUG-241 ①：__sub__ 支持 timedelta（与 __add__ 对称）。"""

    def test_sub_timedelta_returns_vdate(self):
        d = VDate('2024-01-31')
        r = d - timedelta(days=1)
        assert isinstance(r, VDate)
        assert str(r) == '2024-01-30'

    def test_sub_timedelta_weeks(self):
        assert str(VDate('2024-01-31') - timedelta(weeks=2)) == '2024-01-17'

    def test_add_timedelta_symmetry(self):
        d = VDate('2024-01-31')
        assert str(d + timedelta(days=1)) == str(d.add_days(1)) == '2024-02-01'

    def test_sub_int_still_works(self):
        assert str(VDate('2024-01-31') - 1) == '2024-01-30'

    def test_sub_date_diff_still_float(self):
        diff = VDate('2024-01-31') - VDate('2024-01-01')
        assert diff == 30.0


class TestStrNormalization:
    """BUG-241 ②：同日期不同构造路径 str 一致。"""

    def test_add_int_str_matches_constructed(self):
        a = VDate('2024-02-01')
        b = VDate('2024-01-31') + 1
        assert str(a) == str(b) == '2024-02-01'
        assert a == b

    def test_add_timedelta_str(self):
        b = VDate('2024-01-31') + timedelta(days=1)
        assert str(b) == '2024-02-01'

    def test_sub_int_str(self):
        assert str(VDate('2024-02-01') - 1) == '2024-01-31'

    def test_sub_timedelta_str(self):
        assert str(VDate('2024-02-01') - timedelta(days=1)) == '2024-01-31'

    def test_custom_compact_fmt_propagated(self):
        d = VDate('20240131', fmt='%Y%m%d')
        assert str(d + 1) == '20240201'

    def test_datetime_source_keeps_its_format(self):
        d = VDate('2024-01-31 12:00:00')
        assert str(d + 1) == '2024-02-01 12:00:00'


class TestAddHelpersUnchanged:
    """既有 add_* 辅助方法不受影响（防修复过度）。"""

    def test_add_days(self):
        assert str(VDate('2024-01-31').add_days(1)) == '2024-02-01'

    def test_add_months_month_end(self):
        assert str(VDate('2024-01-31').add_months(1)) == '2024-02-29'

    def test_sub_months(self):
        assert str(VDate('2024-03-31').sub_months(2)) == '2024-01-31'

    def test_add_years_leap(self):
        assert str(VDate('2024-02-29').add_years(1)) == '2025-02-28'