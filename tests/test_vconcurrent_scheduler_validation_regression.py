# -*- coding: utf-8 -*-
"""回归测试：调度器的时间范围与 action 校验（BUG-488）。

修复前：

    sm.cron_like().at_time("25:99", fn)   # 静默接受！随后守护线程里
                                          # datetime.replace(hour=25) 抛 ValueError，
                                          # 线程静默死掉、任务永不执行
    sm.cron_like().at_time("12:60", fn)   # 同样静默接受
    vs.schedule(0.01, 123)                # 非可调用 action 被排进队列，
                                          # 触发时才抛 "'int' object is not callable"
    vs.schedule(-1, fn)                   # 负 delay 也接受

修复后：小时 0-23、分钟/秒 0-59；``schedule()`` 的 delay 必须为非负数字、
action 必须可调用（均带参数名）。
"""

import time

import pytest

import vools.vconcurrent.sched_mod as sm


class TestAtTimeRange:
    @pytest.mark.parametrize("bad,field", [
        ("25:99", "小时"),
        ("24:00", "小时"),
        ("-1:00", "小时"),
        ("12:60", "分钟"),
        ("12:00:60", "秒"),
    ])
    def test_out_of_range(self, bad, field):
        with pytest.raises(ValueError) as ei:
            sm.cron_like().at_time(bad, lambda: None)
        assert field in str(ei.value)

    @pytest.mark.parametrize("bad", ["nope", "", "12", "a:b:c", None])
    def test_bad_format(self, bad):
        with pytest.raises((ValueError, TypeError)):
            sm.cron_like().at_time(bad, lambda: None)

    @pytest.mark.parametrize("ok", ["00:00", "23:59", "12:30:45", "9:05"])
    def test_valid_times(self, ok):
        assert isinstance(sm.cron_like().at_time(ok, lambda: None), sm.cron_like)


class TestScheduleValidation:
    def test_non_callable_action(self):
        with pytest.raises(TypeError) as ei:
            sm.VScheduler().schedule(0.01, 123)
        assert "action" in str(ei.value)

    def test_negative_delay(self):
        with pytest.raises(ValueError) as ei:
            sm.VScheduler().schedule(-1, lambda: None)
        assert "delay" in str(ei.value)

    def test_non_numeric_delay(self):
        with pytest.raises(TypeError) as ei:
            sm.VScheduler().schedule("x", lambda: None)
        assert "delay" in str(ei.value)

    def test_valid_schedule_then_run(self):
        calls = []
        vs = sm.VScheduler()
        assert vs.schedule(0.01, lambda: calls.append(1)) is not None
        # 事件在 run() 时执行（VScheduler 不自动起线程）
        vs.run()
        assert calls == [1]


class TestTimerAndPeriodicValidationUnchanged:
    @pytest.mark.parametrize("cls", [sm.Timer, sm.PeriodicTask])
    def test_non_callable(self, cls):
        with pytest.raises(TypeError):
            cls(0.05, 123)

    @pytest.mark.parametrize("cls", [sm.Timer, sm.PeriodicTask])
    def test_negative_interval(self, cls):
        with pytest.raises(ValueError):
            cls(-1, lambda: None)

    def test_timer_fires(self):
        calls = []
        t = sm.Timer(0.02, lambda: calls.append(1))
        try:
            t.start()
            deadline = time.time() + 2
            while not calls and time.time() < deadline:
                time.sleep(0.01)
            assert calls
        finally:
            t.cancel()

    def test_periodic_task_runs(self):
        calls = []
        pt = sm.PeriodicTask(0.02, lambda: calls.append(1))
        try:
            pt.start()
            deadline = time.time() + 2
            while len(calls) < 2 and time.time() < deadline:
                time.sleep(0.01)
            assert len(calls) >= 2
        finally:
            pt.stop()


class TestDelayedCallEnvelope:
    def test_negative_seconds(self):
        with pytest.raises(ValueError):
            sm.delayed_call(-1, lambda: None)

    def test_non_callable(self):
        with pytest.raises(TypeError):
            sm.delayed_call(0.01, 123)
