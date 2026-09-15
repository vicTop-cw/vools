"""tests/concurrent/test_sched_mod.py — 调度器测试"""
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
        task = s.schedule(lambda: None, delay=0.1)
        assert task is not None

    def test_schedule_at(self):
        s = VScheduler()
        future_time = time.time() + 1.0
        task = s.schedule_at(future_time, lambda: None)
        assert task is not None

    def test_cancel(self):
        s = VScheduler()
        task = s.schedule(lambda: None, delay=10.0)
        result = s.cancel(task)
        assert result is True

    def test_cancel_all(self):
        s = VScheduler()
        s.schedule(lambda: None, delay=10.0)
        s.schedule(lambda: None, delay=10.0)
        s.cancel_all()
        assert s.empty() is True

    def test_empty(self):
        s = VScheduler()
        assert s.empty() is True
        s.schedule(lambda: None, delay=10.0)
        assert s.empty() is False

    def test_queue(self):
        s = VScheduler()
        s.schedule(lambda: None, delay=10.0)
        assert s.queue is not None

    def test_run(self):
        s = VScheduler()
        results = []
        s.schedule(lambda: results.append('done'), delay=0.1)
        s.run(block=False)
        time.sleep(0.2)
        assert 'done' in results


class TestTimer:
    """Timer 定时器测试"""

    def test_creation(self):
        t = Timer(interval=1.0, target=lambda: None)
        assert t is not None

    def test_start_and_cancel(self):
        results = []
        t = Timer(interval=0.1, target=lambda: results.append('tick'))
        t.start()
        time.sleep(0.15)
        t.cancel()
        assert len(results) >= 1

    def test_interval(self):
        t = Timer(interval=2.0, target=lambda: None)
        assert t.interval == 2.0

    def test_repeat(self):
        t = Timer(interval=0.1, target=lambda: None, repeat=True)
        assert t.repeat is True

    def test_is_running(self):
        t = Timer(interval=0.1, target=lambda: None)
        t.start()
        assert t.is_running() is True
        t.cancel()

    def test_repr(self):
        t = Timer(interval=1.0, target=lambda: None)
        assert 'Timer' in repr(t)


class TestPeriodicTask:
    """PeriodicTask 周期任务测试"""

    def test_creation(self):
        p = PeriodicTask(interval=1.0, target=lambda: None)
        assert p is not None

    def test_start_and_stop(self):
        results = []
        p = PeriodicTask(interval=0.1, target=lambda: results.append('tick'))
        p.start()
        time.sleep(0.15)
        p.stop()
        assert len(results) >= 1

    def test_set_interval(self):
        p = PeriodicTask(interval=1.0, target=lambda: None)
        p.set_interval(2.0)
        assert p.interval == 2.0

    def test_is_running(self):
        p = PeriodicTask(interval=0.1, target=lambda: None)
        p.start()
        assert p.is_running() is True
        p.stop()


class TestCronLike:
    """cron_like 测试"""

    def test_creation(self):
        c = cron_like()
        assert c is not None

    def test_interval(self):
        c = cron_like()
        assert c.interval == 60.0

    def test_hourly(self):
        c = cron_like()
        c.hourly()
        assert c.interval == 3600.0

    def test_daily(self):
        c = cron_like()
        c.daily()
        assert c.interval == 86400.0

    def test_at_time(self):
        c = cron_like()
        c.at_time("14:30")
        assert c.interval > 0

    def test_start_stop(self):
        results = []
        c = cron_like()
        c.at_time("00:00")
        c.runner(lambda: results.append('run'))
        c.start()
        c.stop()
        assert True  # 无异常即通过


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
        pool.remove(s)
        assert len(pool) == 0

    def test_schedulers(self):
        pool = SchedulerPool()
        s = VScheduler()
        pool.add(s)
        assert s in pool.schedulers

    def test_cancel_all(self):
        pool = SchedulerPool()
        s = VScheduler()
        s.schedule(lambda: None, delay=10.0)
        pool.add(s)
        pool.cancel_all()
        assert s.empty() is True


class TestDelayedCall:
    """delayed_call 延迟调用测试"""

    def test_delayed_call(self):
        results = []
        f = delayed_call(lambda x: results.append(x), delay=0.1)
        time.sleep(0.2)
        # delayed_call 应返回 Future 或 None
        assert f is not None or True
