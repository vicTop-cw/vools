# -*- coding: utf-8 -*-
"""actus/tests/test_cost_month_boundary.py — cost 月度边界（此前整个域无测试）。

审计 #9：`ls tests | grep cost` = 0，`month=` 在测试里 grep = 0。月度边界完全未测：
跨月账本切换、`get_cost_summary(month=...)`、`record_cost` 归月、月度预算重置。
这些一旦写错，用户会看到"本月花了 $0"（实际花在别的文件）或预算永不重置。

时间控制：monkeypatch `cost.datetime`（record_cost/summary 的"当前月"来源），
不 sleep、不改产品代码。
"""

import json
import os
import sys
from datetime import datetime as _real_datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import cost  # noqa: E402


class _FakeDateTime(object):
    """`cost.datetime` 的替身：`now()` 返回可控时刻（其余属性透传）。"""

    current = _real_datetime(2026, 1, 31, 23, 59, 0)

    @classmethod
    def now(cls):
        return cls.current

    def __getattr__(self, name):
        return getattr(_real_datetime, name)


class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    costs = meta / "costs"
    for directory in (home, meta, costs):
        directory.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    # COSTS_DIR 在 import 时按 env 算好；显式指到本用例 tmp（不依赖 import 顺序）
    monkeypatch.setattr(cost, "COSTS_DIR", str(costs))
    clock = _FakeDateTime
    clock.current = _real_datetime(2026, 1, 31, 23, 59, 0)
    monkeypatch.setattr(cost, "datetime", clock)

    w = _World()
    w.costs = costs
    w.clock = clock
    return w


def _ledger(world, month):
    return os.path.join(str(world.costs), "%s.jsonl" % month)


def _write_ledger(world, month, rows):
    with open(_ledger(world, month), "w", encoding="utf-8") as handle:
        for entry in rows:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _entry(cost_usd, provider="anthropic", model="claude", tokens=10,
           timestamp="2026-01-31T23:59:00"):
    return {"timestamp": timestamp, "action_id": "ai.llm.complete",
            "provider": provider, "cost_usd": cost_usd, "tokens": tokens,
            "model": model}


# ===========================================================================
# ① record_cost 按"写入时刻"归月（跨月账本切换）
# ===========================================================================

def test_record_cost_lands_in_the_month_of_write_time(world):
    """退步了会怎样：`record_cost` 用固定/错误月份（或 UTC 与本地混用）—— 1 月 31 日
    23:59 的调用被记到 2 月，用户查 1 月账本永远少一笔。

    断言：Jan 31 23:59 记录 → 写 `2026-01.jsonl`（不在 02）；拨到 Feb 1 00:00 再记
    → 写 `2026-02.jsonl`；两月账本各 1 行、互不混入。
    """
    world.clock.current = _real_datetime(2026, 1, 31, 23, 59, 0)
    cost.record_cost("ai.llm.complete", "anthropic", 1.25, tokens=10, model="m1")

    assert os.path.isfile(_ledger(world, "2026-01"))
    assert not os.path.exists(_ledger(world, "2026-02"))
    with open(_ledger(world, "2026-01"), "r", encoding="utf-8") as handle:
        jan_rows = [json.loads(line) for line in handle if line.strip()]
    assert len(jan_rows) == 1 and jan_rows[0]["cost_usd"] == 1.25
    assert jan_rows[0]["timestamp"].startswith("2026-01-31T23:59")

    world.clock.current = _real_datetime(2026, 2, 1, 0, 0, 1)
    cost.record_cost("ai.llm.complete", "openai", 2.5, tokens=20, model="m2")

    assert os.path.isfile(_ledger(world, "2026-02"))
    with open(_ledger(world, "2026-02"), "r", encoding="utf-8") as handle:
        feb_rows = [json.loads(line) for line in handle if line.strip()]
    assert len(feb_rows) == 1 and feb_rows[0]["cost_usd"] == 2.5
    assert feb_rows[0]["timestamp"].startswith("2026-02-01T00:00")


# ===========================================================================
# ② get_cost_summary(month=...) 只汇总指定月份
# ===========================================================================

def test_get_cost_summary_month_filter_is_isolated(world):
    """退步了会怎样：`month=` 参数被忽略（永远汇总"当前月"）或把所有账本加在一起 ——
    月度报表/预算永远算错，且用户无法回看历史月份。

    断言：1 月账本 1.5、2 月账本 2.5 → `month='2026-01'` 只算 1.5、`month='2026-02'`
    只算 2.5；`month=None` 跟随当前时钟（2 月）只算 2.5。
    """
    _write_ledger(world, "2026-01", [_entry(1.5, tokens=10, timestamp="2026-01-15T10:00:00")])
    _write_ledger(world, "2026-02", [_entry(2.5, tokens=20, timestamp="2026-02-15T10:00:00")])
    world.clock.current = _real_datetime(2026, 2, 20, 12, 0, 0)

    jan = cost.get_cost_summary("2026-01")
    feb = cost.get_cost_summary("2026-02")
    current = cost.get_cost_summary()

    assert jan["month"] == "2026-01" and jan["total_usd"] == 1.5 and jan["calls"] == 1, jan
    assert feb["month"] == "2026-02" and feb["total_usd"] == 2.5 and feb["calls"] == 1, feb
    assert current["month"] == "2026-02" and current["total_usd"] == 2.5, current


# ===========================================================================
# ③ 月度预算按自然月重置
# ===========================================================================

def test_monthly_budget_resets_across_months(world):
    """退步了会怎样：预算按"累计总额"而不是当前月计算 —— 上月超支会让本月一开始
    就 over_budget；或月切换后 remaining/usage_pct 不重置（用户被永久锁死）。

    断言：1 月花 11（超 $10 预算），2 月只花 0.5；时钟在 2 月时 `check_budget(10)`
    → 不超支、remaining=9.5；把时钟拨回 1 月 → 超支（over_budget=True）。
    """
    _write_ledger(world, "2026-01", [_entry(11.0, timestamp="2026-01-15T10:00:00")])
    _write_ledger(world, "2026-02", [_entry(0.5, timestamp="2026-02-10T10:00:00")])

    world.clock.current = _real_datetime(2026, 2, 20, 12, 0, 0)
    feb = cost.check_budget(10.0)
    assert cost.get_cost_summary()["month"] == "2026-02"
    assert feb["spent_usd"] == 0.5 and feb["over_budget"] is False, feb
    assert feb["remaining_usd"] == 9.5 and feb["usage_pct"] == 5.0, feb

    world.clock.current = _real_datetime(2026, 1, 20, 12, 0, 0)
    jan = cost.check_budget(10.0)
    assert cost.get_cost_summary()["month"] == "2026-01"
    assert jan["spent_usd"] == 11.0 and jan["over_budget"] is True, jan
    assert jan["remaining_usd"] == 0, jan
