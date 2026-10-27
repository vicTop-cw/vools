# -*- coding: utf-8 -*-
"""回归测试：sched_mod 的 schedule_at / SchedulerPool 入参校验（BUG-348）。

修复前：

    VScheduler().schedule_at("x", fn)
        # TypeError: unsupported operand type(s) for -: 'str' and 'float'
        #   （裸错，看不出是 when 参数）
    pool = SchedulerPool()
    pool.add(123)       # 静默塞进池子
    pool.cancel_all()   # AttributeError: 'int' object has no attribute 'cancel_all'
                        #   —— 错误离病因很远（污染发生在 add）
    pool.remove(None)   # 静默走「未加入」分支返回 False（入参类型完全没校验）

修复：schedule_at 校验 when 为数值；SchedulerPool.add/remove 校验入参是调度器
（VScheduler 或具备 cancel_all/stop_all/run 的对象——保留鸭子类型兼容）。
"""

import time

import pytest

from vools.vconcurrent.sched_mod import SchedulerPool, VScheduler


class TestScheduleAtValidation:
    @pytest.mark.parametrize("bad", ["x", None, [1]])
    def test_when_must_be_number(self, bad):
        with pytest.raises(TypeError) as ei:
            VScheduler().schedule_at(bad, lambda: None)
        assert "when" in str(ei.value)

    def test_valid_when(self):
        event = VScheduler().schedule_at(time.time() + 0.01, lambda: None)
        assert event is not None


class TestSchedulerPoolValidation:
    @pytest.mark.parametrize("bad", [None, 123, "x", [1]])
    def test_add_rejects_non_scheduler(self, bad):
        with pytest.raises(TypeError) as ei:
            SchedulerPool().add(bad)
        assert "scheduler" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_remove_rejects_non_scheduler(self, bad):
        with pytest.raises(TypeError) as ei:
            SchedulerPool().remove(bad)
        assert "scheduler" in str(ei.value)

    def test_pool_not_polluted_by_bad_add(self):
        pool = SchedulerPool()
        with pytest.raises(TypeError):
            pool.add(123)
        # 关键：池子未被污染，后续批量操作正常
        assert pool.cancel_all() == 0
        assert isinstance(pool.stop_all(), SchedulerPool)


class TestSchedulerPoolBehaviourUnchanged:
    def test_add_and_remove_vscheduler(self):
        pool = SchedulerPool()
        sch = VScheduler()
        assert pool.add(sch) is pool
        assert pool.remove(sch) is True
        assert pool.remove(sch) is False

    def test_duck_typed_scheduler_accepted(self):
        class FakeScheduler:
            def cancel_all(self):
                return 0

            def stop_all(self):
                return self

            def run(self, blocking=True):
                return None

        pool = SchedulerPool()
        assert pool.add(FakeScheduler()) is pool
        assert pool.cancel_all() == 0

    def test_run_all_non_blocking(self):
        pool = SchedulerPool()
        pool.add(VScheduler())
        assert pool.run_all(blocking=False) is pool


class TestVSchedulerBehaviourUnchanged:
    def test_schedule_and_cancel(self):
        sch = VScheduler()
        event = sch.schedule(60, lambda: None)
        assert sch.empty() is False
        assert sch.cancel(event) is True
        assert sch.cancel(event) is False

    def test_schedule_validates_delay_and_action(self):
        sch = VScheduler()
        with pytest.raises(ValueError):
            sch.schedule(-1, lambda: None)
        with pytest.raises(TypeError):
            sch.schedule(1, None)
