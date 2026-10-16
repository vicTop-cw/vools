# -*- coding: utf-8 -*-
"""tests/datetime/test_vdate_time_preserved.py — vDate/VDate 字符串解析的两个缺陷（钉 BUG-67）

两处同源缺陷（vools/datetime/utils.py 的函数版 vDate 与 vdate_class.py 的类版 VDate
各一份，形状一模一样）：

1) ValueError 崩溃分支：命中「紧凑日期 + 空格 + 时间」分支（正则
   ^\\d{4}\\d{2}\\d{2} \\d{2}:\\d{2}:\\d{2}$，如 '20240102 13:45:30'）时，
   代码取了 tm 却【忘了先把 dt 截回日期部分】（上一分支有 `dt = dt.split(" ")[0]`，
   本分支漏了），于是 int(dt[6:]) == int('02 13:45:30') 必 ValueError ——
   命中自己正则的输入 100% 崩（2026-10-17 寻虫实测 traceback 在 utils.py:83 /
   vdate_class.py:429）。

2) 时分秒被静默清零：兜底分支写的是 `datetime(*_parse_date(dt, fmt))`，而
   _parse_date 只回 (year, month, day) —— strptime 明明按 fmt 解析出了时分秒，
   组装时却被丢掉。实测 '2024.01.02 13:45:30' + '%Y.%m.%d %H:%M:%S' 返回
   '2024.01.02 00:00:00'：不抛异常、时间是错的，比崩更难查（与 BUG-66 同族形状：
   静默出错数据）。分隔符不是 '-' 的格式（%Y.%m.%d、%Y/%m/%d、紧凑 %Y%m%d%H%M%S
   带时间的兜底等）全受影响。

修：① 该分支补 `dt = dt.split(" ")[0]`；② 兜底直接用 strptime 结果（类版把
y..microsecond 全传给 __new__），无时间段时行为不变。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.datetime.utils import vDate                    # noqa: E402
from vools.datetime.vdate_class import VDate              # noqa: E402


# ---------------------------------------------------------------------------
# 缺陷 1：命中自身正则即 ValueError
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("maker,cast", [
    (vDate, str),      # 函数版返回字符串
    (VDate, str),      # 类版返回 datetime 子类，str() 后同为 '20240102 13:45:30' 形态? 见下
])
def test_compact_space_time_does_not_crash(maker, cast):
    """'20240102 13:45:30'（紧凑日期+空格+时间）修复前必 ValueError。"""
    if maker is vDate:
        out = maker('20240102 13:45:30', fmt='%Y%m%d %H:%M:%S')
        assert out == '20240102 13:45:30'
    else:
        v = maker('20240102 13:45:30')
        # 类版返回 VDate（datetime 子类）：年月日时分秒都必须对
        assert (v.year, v.month, v.day) == (2024, 1, 2)
        assert (v.hour, v.minute, v.second) == (13, 45, 30)


def test_compact_space_time_via_class_matches_dashed_form():
    """同一时刻的两种写法（带横杠/紧凑）解析结果必须一致。"""
    a = VDate('2024-01-02 13:45:30')
    b = VDate('20240102 13:45:30')
    assert (a.year, a.month, a.day, a.hour, a.minute, a.second) == \
           (b.year, b.month, b.day, b.hour, b.minute, b.second) == \
           (2024, 1, 2, 13, 45, 30)


# ---------------------------------------------------------------------------
# 缺陷 2：非 '-' 分隔格式的时间被静默清零（兜底分支）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dt_str,fmt,expect_out", [
    ('2024.01.02 13:45:30', '%Y.%m.%d %H:%M:%S', '2024.01.02 13:45:30'),
    ('2024/01/02 13:45:30', '%Y/%m/%d %H:%M:%S', '2024/01/02 13:45:30'),
])
def test_func_fallback_preserves_time(dt_str, fmt, expect_out):
    """函数版兜底分支：修复前返回 '.... 00:00:00'（时间被清零）。"""
    assert vDate(dt_str, fmt=fmt) == expect_out


@pytest.mark.parametrize("dt_str,fmt", [
    ('2024.01.02 13:45:30', '%Y.%m.%d %H:%M:%S'),
    ('2024/01/02 13:45:30', '%Y/%m/%d %H:%M:%S'),
])
def test_class_fallback_preserves_time(dt_str, fmt):
    """类版同款兜底（vdate_class __new__ else 分支）也不得清零。"""
    v = VDate(dt_str, fmt=fmt)
    assert (v.year, v.month, v.day, v.hour, v.minute, v.second) == \
        (2024, 1, 2, 13, 45, 30)


# ---------------------------------------------------------------------------
# 行为保持：无时间段的格式与既有主流写法不受影响
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dt_str,fmt,expect_out", [
    ('2024-01-02', '%Y-%m-%d', '2024-01-02'),          # 纯日期兜底：仍 00:00:00 输出由 fmt 决定
    ('2024.01.02', '%Y.%m.%d', '2024.01.02'),
    ('2024-01-02 13:45:30', '%Y-%m-%d %H:%M:%S', '2024-01-02 13:45:30'),  # 对照组（原就正确）
    ('2024-01-02', None, '2024-01-02'),
])
def test_unchanged_cases_still_work(dt_str, fmt, expect_out):
    if fmt is None:
        assert vDate(dt_str) == expect_out
    else:
        assert vDate(dt_str, fmt=fmt) == expect_out


def test_class_date_only_forms_still_work():
    """类版纯日期路径（8 位数字 / 带横杠）行为不变。"""
    for s in ('20240102', '2024-01-02'):
        v = VDate(s)
        assert (v.year, v.month, v.day) == (2024, 1, 2)
        assert (v.hour, v.minute, v.second) == (0, 0, 0)
