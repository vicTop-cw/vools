# -*- coding: utf-8 -*-
"""CronExpr 的边界与星期语义（第 33 轮扫 triggers.py 发现）。

两个缺陷：
  1. **星期字段整体偏移一天**（高危）：cron 标准 0=周日，而 `matches` 直接比
     `time.struct_time.tm_wday`（0=周一）。实测 `'0 12 * * 0'` 在**周一**匹配、
     周日反而不匹配 —— 所有按星期配的触发器都错一天，且完全静默。
  2. **负步进 / 倒序范围静默产出空集合**（中危）：`*/-1`、`5-3` 都得到空 set，
     `matches()` 永远 False ⇒ 触发器永不触发，零提示。
"""
import time

import pytest

from vools.actus.triggers import CronExpr


def _t(y, mo, d, h=12, mi=0):
    """构造 struct_time；tm_wday 按 Python 约定（0=周一）。"""
    wd = time.localtime(time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))).tm_wday
    return time.struct_time((y, mo, d, h, mi, 0, wd, 0, 0))


# 2026-10-25 是周日，2026-10-26 是周一
SUNDAY = _t(2026, 10, 25)
MONDAY = _t(2026, 10, 26)
SATURDAY = _t(2026, 10, 24)


# --------------------------------------------------------------------------
# 星期语义（核心回归）
# --------------------------------------------------------------------------
def test_weekday_0_is_sunday():
    """cron 的 0 = 周日（此前错配成周一）。"""
    assert CronExpr("0 12 * * 0").matches(SUNDAY) is True
    assert CronExpr("0 12 * * 0").matches(MONDAY) is False


def test_weekday_6_is_saturday():
    assert CronExpr("0 12 * * 6").matches(SATURDAY) is True
    assert CronExpr("0 12 * * 6").matches(SUNDAY) is False


def test_weekday_1_is_monday():
    assert CronExpr("0 12 * * 1").matches(MONDAY) is True
    assert CronExpr("0 12 * * 1").matches(SUNDAY) is False


def test_weekday_wildcard_matches_all():
    for t in (SUNDAY, MONDAY, SATURDAY):
        assert CronExpr("0 12 * * *").matches(t) is True


# --------------------------------------------------------------------------
# 步进边界
# --------------------------------------------------------------------------
def test_normal_step():
    assert len(CronExpr("*/15 * * * *").fields[0]) == 4      # 0,15,30,45
    assert len(CronExpr("*/1 * * * *").fields[0]) == 60


@pytest.mark.parametrize("expr", ["*/0 * * * *", "*/-1 * * * *", "*/0-30 * * * *"])
def test_step_must_be_positive(expr):
    """步进 <1 必须报错（此前 `*/-1` 静默产出空集合，永不触发）。"""
    with pytest.raises(ValueError) as exc:
        CronExpr(expr)
    assert "步进" in str(exc.value), exc.value


def test_step_not_integer():
    with pytest.raises(ValueError) as exc:
        CronExpr("*/abc * * * *")
    assert "不是整数" in str(exc.value), exc.value


# --------------------------------------------------------------------------
# 范围
# --------------------------------------------------------------------------
def test_normal_range():
    assert CronExpr("5-9 * * * *").fields[0] == {5, 6, 7, 8, 9}


@pytest.mark.parametrize("expr", ["5-3 * * * *", "10-2/1 * * * *"])
def test_reversed_range_rejected(expr):
    """倒序范围必须报错（此前静默产出空集合）。"""
    with pytest.raises(ValueError) as exc:
        CronExpr(expr)
    assert "倒序" in str(exc.value), exc.value


def test_value_out_of_range():
    with pytest.raises(ValueError) as exc:
        CronExpr("99 * * * *")
    assert "超出范围" in str(exc.value), exc.value


# --------------------------------------------------------------------------
# 结构
# --------------------------------------------------------------------------
@pytest.mark.parametrize("expr", ["* * * *", "* * * * * *", ""])
def test_field_count(expr):
    with pytest.raises(ValueError) as exc:
        CronExpr(expr)
    assert "5 字段" in str(exc.value), exc.value


def test_empty_item_rejected():
    with pytest.raises(ValueError) as exc:
        CronExpr("1,,2 * * * *")
    assert "空项" in str(exc.value), exc.value


def test_no_field_is_ever_empty():
    """任何合法表达式解析出的字段都不能是空集合（空集合 = 永不触发）。"""
    for expr in ("* * * * *", "0 0 * * *", "0,30 9-17 * * 1-5",
                 "*/5 * * * *", "0 12 1,15 * *"):
        c = CronExpr(expr)
        for i, f in enumerate(c.fields):
            assert f, "字段 %d 为空: %r" % (i, expr)
