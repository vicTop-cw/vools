# -*- coding: utf-8 -*-
"""回归测试：VDate 的原生 datetime API 可用性与可哈希（BUG-386/387）。

【BUG-386】`VDate.__new__(cls, dt=None, fmt=None)` 只接受 2 个参数，但
`datetime` 的 C 实现（`now()` / `today()` / `fromtimestamp()` / `replace()` /
`astimezone()` / `combine()` / `fromisoformat()` / `fromordinal()` /
`fromisocalendar()`）内部用**组件签名**重新构造实例：

    cls(year, month, day, hour, minute, second, microsecond[, tzinfo[, fold]])

实测全部失败：

    VDate.now()             # TypeError: VDate.__new__() takes from 1 to 3 positional arguments but 9 were given
    VDate(2026, 1, 31)      # 同上（4 个参数）
    VDate('2026-01-31').replace(day=15)   # RecursionError / AttributeError('DateProcessor' has no 'fmt')

递归来源：`__getattr__` 在 `_date_processor` 缺失时又去 `getattr(self._date_processor, name)`，
自我触发；而 C 方法构造的实例 `__dict__` 为空（C 层不调用 `__init__`），`fmt` 也缺失。

修复：
1. `__new__` / `__init__` 识别组件签名并正确建实例（无时间分量时用日期格式）；
2. `__getattr__`：下划线属性缺失直接 AttributeError（不再回退递归）；`fmt` 惰性
   按时间分量推导默认值；`_date_processor` 惰性重建。

【BUG-387】VDate 定义了 `__eq__`（按 (y, m, d) 比较）后 Python 自动把 `__hash__`
置 None → VDate 不可哈希，无法作为 dict 键 / set 元素（原生 date/datetime 可哈希）。
修复：按与 `__eq__` 一致的粒度实现 `__hash__`。
"""

import datetime as _dt

import pytest

from vools.datetime.vdate_class import VDate


class TestComponentConstruction:
    def test_ymd(self):
        d = VDate(2026, 1, 31)
        assert str(d) == '2026-01-31'
        assert (d.year, d.month, d.day) == (2026, 1, 31)

    def test_with_time(self):
        d = VDate(2026, 1, 31, 10, 20)
        assert str(d) == '2026-01-31 10:20:00'
        assert (d.hour, d.minute) == (10, 20)


class TestNativeDatetimeApis:
    def test_replace(self):
        d = VDate('2026-01-31')
        assert str(d.replace(day=15)) == '2026-01-15'
        assert str(d.replace(year=2027)) == '2027-01-31'

    def test_now_today(self):
        for factory in (VDate.now, VDate.today):
            d = factory()
            assert isinstance(d, VDate)
            assert d.year >= 2024

    def test_fromtimestamp(self):
        d = VDate.fromtimestamp(0)
        assert isinstance(d, VDate)
        assert d.year == 1970

    def test_fromisoformat(self):
        assert str(VDate.fromisoformat('2026-01-31')) == '2026-01-31'

    def test_fromordinal(self):
        assert str(VDate.fromordinal(739647)) == '2026-01-31'

    def test_fromisocalendar(self):
        d = VDate.fromisocalendar(2026, 4, 5)
        assert (d.year, d.month, d.day) == (2026, 1, 23)

    def test_combine(self):
        d = VDate.combine(VDate('2026-01-31'),
                          VDate('2026-01-31 10:20:30').time())
        assert str(d) == '2026-01-31 10:20:30'

    def test_astimezone(self):
        d = VDate('2026-01-31').astimezone()
        assert isinstance(d, VDate)


class TestHashable:
    def test_hash(self):
        d = VDate('2026-01-31')
        assert isinstance(hash(d), int)

    def test_set_dedup(self):
        assert len({VDate('2026-01-31'), VDate('2026-01-31'),
                    VDate('2026-02-01')}) == 2

    def test_dict_key(self):
        assert {VDate('2026-01-31'): 'a'}[VDate('2026-01-31')] == 'a'

    def test_hash_consistent_with_eq(self):
        a, b = VDate('2026-01-31'), VDate('2026-01-31 18:00:00')
        assert a == b
        assert hash(a) == hash(b)


class TestExistingBehaviourUnchanged:
    def test_parse_string(self):
        assert str(VDate('2026-01-31')) == '2026-01-31'
        assert str(VDate('20260131')) == '20260131'   # 保持既有 fmt 推断

    def test_timestamp_input(self):
        assert VDate(1705286400).year == 2024

    def test_arithmetic(self):
        d = VDate('2026-01-31')
        assert str(d.add_days(1)) == '2026-02-01'
        assert str(d.add_months(1)) == '2026-02-28'   # 月末夹取
        assert str(d.sub_days(1)) == '2026-01-30'

    def test_formatting(self):
        d = VDate('2026-01-31')
        assert d.toString() == '2026-01-31'
        assert d.strftime('%Y%m%d') == '20260131'

    def test_date_returns_native_date(self):
        d = VDate('2026-01-31')
        out = d.date()
        assert isinstance(out, _dt.date) and not isinstance(out, VDate)

    def test_comparison(self):
        assert VDate('2026-01-01') < VDate('2026-02-01')
        assert VDate('2026-01-01') == '2026-01-01'

    def test_get_week_and_range(self):
        d = VDate('2026-01-01')
        assert d.get_week() == '2025-12-29'
        assert len(d.getDateRange(start='2026-01-01', periods=3)) == 3