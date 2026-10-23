# -*- coding: utf-8 -*-
"""回归测试：定时器参数校验（BUG-397）。

`Timer` / `PeriodicTask` 构造期**零校验**，以下调用全部被静默接受：

    Timer(-1, callback)            # threading.Timer 视为立即触发
    PeriodicTask(0, callback)      # 调度间隔 0 → **紧循环**（CPU 打满）
    Timer(1, 'not-callable')       # 回调在定时器线程内抛 TypeError，
                                   # 异常被 threading 吞掉 → 静默"任务从未执行"
    PeriodicTask(1, None)

修复：`interval` 必须是 > 0 的数字（bool 不算），`callback` 必须可调用；
`PeriodicTask.set_interval` 同口径校验。合法路径（单次/周期/改间隔）不变。
"""

import time

import pytest

from vools.vconcurrent.sched_mod import PeriodicTask, Timer


class TestTimerValidation:
    @pytest.mark.parametrize('interval', [0, -1, -0.5])
    def test_non_positive_interval(self, interval):
        with pytest.raises(ValueError) as ei:
            Timer(interval, print)
        assert 'interval' in str(ei.value)

    @pytest.mark.parametrize('interval', ['1', None, True, [1]])
    def test_non_numeric_interval(self, interval):
        with pytest.raises(TypeError):
            Timer(interval, print)

    @pytest.mark.parametrize('cb', ['x', None, 42])
    def test_non_callable_callback(self, cb):
        with pytest.raises(TypeError) as ei:
            Timer(1, cb)
        assert 'callback' in str(ei.value)


class TestPeriodicTaskValidation:
    @pytest.mark.parametrize('interval', [0, -1])
    def test_non_positive_interval(self, interval):
        with pytest.raises(ValueError):
            PeriodicTask(interval, print)

    @pytest.mark.parametrize('cb', [None, 'x'])
    def test_non_callable_callback(self, cb):
        with pytest.raises(TypeError):
            PeriodicTask(0.1, cb)

    @pytest.mark.parametrize('interval', [0, -1])
    def test_set_interval_validated(self, interval):
        task = PeriodicTask(0.1, print)
        with pytest.raises(ValueError):
            task.set_interval(interval)

    def test_set_interval_ok(self):
        task = PeriodicTask(0.1, print)
        task.set_interval(0.2)
        assert task.interval == 0.2


class TestValidUsageUnchanged:
    def test_timer_single_shot(self):
        hits = []
        t = Timer(0.05, lambda: hits.append(1))
        t.start()
        assert t.is_running() is True
        time.sleep(0.25)
        assert hits == [1]
        assert t.is_running() is False

    def test_timer_repeat_and_cancel(self):
        hits = []
        t = Timer(0.05, lambda: hits.append(1), repeat=True)
        t.start()
        time.sleep(0.25)
        t.cancel()
        count = len(hits)
        time.sleep(0.15)
        assert count > 1
        assert len(hits) == count

    def test_periodic_task(self):
        hits = []
        task = PeriodicTask(0.05, lambda: hits.append(1))
        task.start()
        time.sleep(0.22)
        task.stop()
        assert len(hits) > 1
        assert task.is_running() is False