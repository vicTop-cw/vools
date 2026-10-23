# -*- coding: utf-8 -*-
"""回归测试：``VThreadPoolExecutor.submit_priority`` 真正按优先级调度（BUG-396）。

原实现**完全忽略** ``priority``：

    def submit_priority(self, priority, fn, *args, **kwargs):
        if self._shutdown: ...
        future = self._executor.submit(fn, *args, **kwargs)   # priority 未使用
        ...

模块里的 ``_PriorityTask``（含 ``__lt__`` 按优先级比较）也从未被使用。
而 docstring 承诺「优先级，数值越小优先级越高」。实测 1 线程池 + 先占位再
提交 4 个优先级任务时，执行顺序恒等于**提交顺序**：``[20, 1, 10, 5]``。

修复：任务入内部 ``PriorityQueue``，独立调度线程**先等空闲工作位、再取当前
最高优先级任务**提交给底层线程池；普通 ``submit`` 以非阻塞方式共享工作位
配额（避免 submit 阻塞导致工作线程内再 submit 的死锁）；shutdown 时先按
优先级排空，避免 future 永挂。

语义边界：线程空闲时任务立即执行、不承诺先后顺序；进程池不支持优先级（已在
其 docstring 中注明）。
"""

import time

import pytest

from vools.vconcurrent.futures import VThreadPoolExecutor


class TestPriorityOrdering:
    def test_ordering_under_contention(self):
        """先占住唯一工作线程，再提交乱序优先级任务 → 应按优先级执行。"""
        order = []
        p = VThreadPoolExecutor(max_workers=1)
        try:
            p.submit(lambda: time.sleep(0.3))          # 占位
            priorities = [20, 1, 10, 5]
            futures = [
                p.submit_priority(pr, (lambda n=pr: order.append(n)))
                for pr in priorities
            ]
            for f in futures:
                f.result(timeout=10)
        finally:
            p.shutdown()
        # 修复前恒为提交顺序 [20, 1, 10, 5]
        assert order == [1, 5, 10, 20]

    def test_equal_priority_fifo(self):
        order = []
        p = VThreadPoolExecutor(max_workers=1)
        try:
            p.submit(lambda: time.sleep(0.2))
            futures = [
                p.submit_priority(0, (lambda n=n: order.append(n)))
                for n in range(3)
            ]
            for f in futures:
                f.result(timeout=10)
        finally:
            p.shutdown()
        assert order == [0, 1, 2]


class TestResultAndExceptionTransfer:
    def test_return_value(self):
        p = VThreadPoolExecutor(max_workers=2)
        try:
            assert p.submit_priority(1, lambda a, b: a + b, 2, 3).result(timeout=10) == 5
        finally:
            p.shutdown()

    def test_exception_propagates(self):
        def boom():
            raise ValueError('bad')

        p = VThreadPoolExecutor(max_workers=2)
        try:
            f = p.submit_priority(1, boom)
            with pytest.raises(ValueError):
                f.result(timeout=10)
        finally:
            p.shutdown()

    def test_mixes_with_normal_submit(self):
        p = VThreadPoolExecutor(max_workers=2)
        try:
            assert p.submit(lambda: 'normal').result(timeout=10) == 'normal'
            assert p.submit_priority(1, lambda: 'prio').result(timeout=10) == 'prio'
        finally:
            p.shutdown()


class TestLifecycle:
    def test_submit_after_shutdown_rejected(self):
        p = VThreadPoolExecutor(max_workers=1)
        p.shutdown()
        with pytest.raises(RuntimeError):
            p.submit_priority(1, lambda: 1)

    def test_shutdown_drains_priority_queue(self):
        """shutdown 时排队中的优先级任务也要完成（future 不得永挂）。"""
        p = VThreadPoolExecutor(max_workers=1)
        p.submit(lambda: time.sleep(0.2))
        futures = [p.submit_priority(i, (lambda n=i: n)) for i in range(3)]
        p.shutdown(wait=True)
        assert [f.result(timeout=10) for f in futures] == [0, 1, 2]

    def test_graceful_shutdown_counts(self):
        p = VThreadPoolExecutor(max_workers=2)
        futures = [p.submit_priority(i, (lambda n=i: n)) for i in range(3)]
        assert p.shutdown_graceful(wait=True, timeout=10) is True
        assert [f.result(timeout=10) for f in futures] == [0, 1, 2]

    def test_counts_track(self):
        p = VThreadPoolExecutor(max_workers=2)
        try:
            fs = [p.submit_priority(i, (lambda n=i: n)) for i in range(2)]
            for f in fs:
                f.result(timeout=10)
            assert p.total_submitted == 2
            assert p.completed_count == 2
            assert p.pending_count == 0
        finally:
            p.shutdown()


class TestProcessPoolDocumented:
    def test_process_pool_priority_documented_as_noop(self):
        from vools.vconcurrent.futures import VProcessPoolExecutor

        doc = VProcessPoolExecutor.submit_priority.__doc__ or ''
        assert '不生效' in doc or '不支持' in doc