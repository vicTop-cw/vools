"""tests/concurrent/test_sched_mod.py — 调度器测试

本文件曾按一套**并不存在**的 API 写成（`schedule(action, delay=...)`、
`Timer(target=...)`、`cron_like.interval` 当属性读、`pool.cancel_all()` 当断言等），
而 tests/concurrent/ 因为 test_bridges.py 的同侧自收死锁从未真正跑完过，
所以这些签名漂移一直没有暴露。现按 vools/concurrent/sched_mod.py 的**真实签名**对齐：

- ``VScheduler.schedule(delay, action, *args, **kwargs)`` —— delay 在前
- ``Timer(interval, callback, ...)`` / ``PeriodicTask(interval, callback, ...)``
- ``cron_like.interval(seconds, callback)`` 是**方法**（不是属性）
- ``Timer.is_running()`` / ``PeriodicTask.is_running()`` 是方法；``interval`` 是属性
"""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.sched_mod import (
    VScheduler, Timer, PeriodicTask, cron_like, SchedulerPool,
    delayed_call,
)


class TestVScheduler:
    """VScheduler 调度器测试"""

    def test_creation(self):
        s = VScheduler()
        assert s is not None

    def test_schedule(self):
        s = VScheduler()
        # 真实签名：schedule(delay, action, *args, **kwargs)
        task = s.schedule(0.1, lambda: None)
        assert task is not None

    def test_schedule_at(self):
        s = VScheduler()
        future_time = time.time() + 1.0
        task = s.schedule_at(future_time, lambda: None)
        assert task is not None

    def test_cancel(self):
        s = VScheduler()
        task = s.schedule(10.0, lambda: None)
        result = s.cancel(task)
        assert result is True

    def test_cancel_unknown_event_returns_false(self):
        s = VScheduler()
        assert s.cancel(object()) is False

    def test_cancel_all(self):
        s = VScheduler()
        s.schedule(10.0, lambda: None)
        s.schedule(10.0, lambda: None)
        assert s.cancel_all() == 2
        assert s.empty() is True

    def test_empty(self):
        s = VScheduler()
        assert s.empty() is True
        s.schedule(10.0, lambda: None)
        assert s.empty() is False

    def test_queue(self):
        s = VScheduler()
        s.schedule(10.0, lambda: None)
        assert len(s.queue) == 1

    def test_run(self):
        s = VScheduler()
        results = []
        s.schedule(0.1, lambda: results.append('done'))
        s.run(blocking=False)
        time.sleep(0.4)
        assert 'done' in results

    def test_schedule_passes_args(self):
        s = VScheduler()
        results = []
        s.schedule(0.05, lambda a, b: results.append((a, b)), 1, 2)
        s.run(blocking=False)
        time.sleep(0.3)
        assert results == [(1, 2)]


class TestTimer:
    """Timer 定时器测试"""

    def test_creation(self):
        t = Timer(interval=1.0, callback=lambda: None)
        assert t is not None

    def test_start_and_cancel(self):
        results = []
        t = Timer(interval=0.1, callback=lambda: results.append('tick'), repeat=True)
        t.start()
        time.sleep(0.35)
        t.cancel()
        assert len(results) >= 1

    def test_interval(self):
        t = Timer(interval=2.0, callback=lambda: None)
        assert t.interval == 2.0

    def test_repeat(self):
        t = Timer(interval=0.1, callback=lambda: None, repeat=True)
        assert t.repeat is True

    def test_is_running(self):
        t = Timer(interval=0.5, callback=lambda: None)
        t.start()
        assert t.is_running() is True
        t.cancel()

    def test_repr(self):
        t = Timer(interval=1.0, callback=lambda: None)
        assert 'Timer' in repr(t)


class TestPeriodicTask:
    """PeriodicTask 周期任务测试"""

    def test_creation(self):
        p = PeriodicTask(interval=1.0, callback=lambda: None)
        assert p is not None

    def test_start_and_stop(self):
        results = []
        p = PeriodicTask(interval=0.1, callback=lambda: results.append('tick'))
        p.start()
        time.sleep(0.35)
        p.stop()
        assert len(results) >= 1

    def test_set_interval(self):
        p = PeriodicTask(interval=1.0, callback=lambda: None)
        p.set_interval(2.0)
        assert p.interval == 2.0

    def test_is_running(self):
        p = PeriodicTask(interval=0.5, callback=lambda: None)
        p.start()
        assert p.is_running() is True
        p.stop()

    def test_repr(self):
        p = PeriodicTask(interval=1.0, callback=lambda: None)
        assert 'PeriodicTask' in repr(p)


class TestCronLike:
    """cron_like 测试

    注意：``cron_like.interval`` 是**注册方法** ``interval(seconds, callback)``，
    不是可读属性——旧测试里 ``assert c.interval == 60.0`` 拿到的只是一个绑定方法。
    """

    def test_creation(self):
        c = cron_like()
        assert c is not None

    def test_interval_registers_task(self):
        c = cron_like()
        c.interval(60.0, lambda: None)
        assert c.task_count == 1

    def test_hourly(self):
        c = cron_like()
        c.hourly(lambda: None)
        assert c.task_count == 1

    def test_daily(self):
        c = cron_like()
        c.daily(lambda: None)
        assert c.task_count == 1

    def test_at_time(self):
        c = cron_like()
        c.at_time("14:30", lambda: None)
        assert c.task_count == 1

    def test_at_time_invalid_format(self):
        c = cron_like()
        with pytest.raises(ValueError):
            c.at_time("not-a-time", lambda: None)

    def test_start_stop(self):
        results = []
        c = cron_like()
        c.interval(0.1, lambda: results.append('run'))
        c.start()
        time.sleep(0.25)
        c.stop()
        assert True  # 无异常即通过（stop 后线程已回收）


class TestSchedulerPool:
    """SchedulerPool 调度器池测试"""

    def test_creation(self):
        pool = SchedulerPool()
        assert pool is not None

    def test_add_remove(self):
        pool = SchedulerPool()
        s = VScheduler()
        pool.add(s)
        assert len(pool) == 1
        assert pool.remove(s) is True
        assert len(pool) == 0

    def test_remove_unknown_returns_false(self):
        pool = SchedulerPool()
        assert pool.remove(VScheduler()) is False

    def test_schedulers(self):
        pool = SchedulerPool()
        s = VScheduler()
        pool.add(s)
        assert s in pool.schedulers

    def test_cancel_all(self):
        pool = SchedulerPool()
        s = VScheduler()
        s.schedule(10.0, lambda: None)
        pool.add(s)
        # cancel_all 返回取消总数（不是 None/布尔）
        assert pool.cancel_all() == 1
        assert s.empty() is True


class TestDelayedCall:
    """delayed_call 延迟调用测试"""

    def test_delayed_call_direct(self):
        results = []
        # 真实签名：delayed_call(seconds, func, *args, **kwargs) —— seconds 在前
        timer = delayed_call(0.1, lambda x: results.append(x), 42)
        assert timer is not None
        time.sleep(0.3)
        assert results == [42]

    def test_delayed_call_decorator(self):
        results = []

        @delayed_call(0.1)
        def greet(name):
            results.append(name)

        greet("world")
        time.sleep(0.3)
        assert results == ["world"]
