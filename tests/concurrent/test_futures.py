"""tests/concurrent/test_futures.py — Future/Executor 测试"""
import pytest
import sys
import os
import time
import concurrent.futures as _cf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.futures import (
    FutureResult, VThreadPoolExecutor, VProcessPoolExecutor,
    as_completed_batch, gather_futures, wait_any, wait_all, map_async,
    run_async,
)


class TestFutureResult:
    """FutureResult 测试"""

    def _make_future(self):
        """创建一个已完成的底层 Future"""
        f = _cf.Future()
        f.set_result(42)
        return f

    def test_creation(self):
        fr = FutureResult(self._make_future())
        assert fr.done() is True

    def test_result(self):
        fr = FutureResult(self._make_future())
        assert fr.result() == 42
        assert fr.success() is True

    def test_set_exception(self):
        f = _cf.Future()
        f.set_exception(ValueError("test error"))
        fr = FutureResult(f)
        assert fr.exception() is not None
        assert fr.success() is False

    def test_add_done_callback(self):
        fr = FutureResult(self._make_future())
        results = []
        fr.add_done_callback(lambda x: results.append(x.result()))
        assert results == [42]

    def test_cancel(self):
        f = _cf.Future()
        fr = FutureResult(f)
        fr.cancel()
        assert fr.cancelled() is True

    def test_running(self):
        f = _cf.Future()
        fr = FutureResult(f)
        # 新创建的 Future 默认状态
        assert isinstance(fr.running(), bool)

    def test_then(self):
        fr = FutureResult(self._make_future())
        g = fr.then(lambda x: x * 2)
        assert g.result() == 84

    def test_catch(self):
        f = _cf.Future()
        f.set_exception(ValueError("err"))
        fr = FutureResult(f)
        g = fr.catch(lambda e: "caught")
        assert g.result() == "caught"

    def test_repr(self):
        fr = FutureResult(self._make_future())
        assert 'FutureResult' in repr(fr)


class TestVThreadPoolExecutor:
    """VThreadPoolExecutor 线程池测试"""

    def test_submit(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(lambda: 42)
            assert future.result() == 42

    def test_submit_priority(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit_priority(1, lambda: 'priority')
            assert future.result() == 'priority'

    def test_map(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda x: x * 2, [1, 2, 3]))
            assert results == [2, 4, 6]

    def test_pending_count(self):
        with VThreadPoolExecutor(max_workers=1) as executor:
            # 提交一个长时间任务和一个短任务
            executor.submit(lambda: time.sleep(0.5))
            executor.submit(lambda: time.sleep(0.5))
            # pending 应该 >= 1（第一个在运行，第二个等待）
            assert executor.pending_count >= 1

    def test_completed_count(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(lambda: 1)
            executor.submit(lambda: 2)
            time.sleep(0.2)
            assert executor.completed_count >= 2

    def test_total_submitted(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(lambda: 1)
            executor.submit(lambda: 2)
            assert executor.total_submitted == 2

    def test_progress(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(lambda: 1)
            completed, total = executor.progress()
            assert isinstance(completed, int)
            assert isinstance(total, int)

    def test_executor_property(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            internal = executor.executor
            assert isinstance(internal, _cf.ThreadPoolExecutor)


class TestVProcessPoolExecutor:
    """VProcessPoolExecutor 进程池测试"""

    def test_submit(self):
        with VProcessPoolExecutor(max_workers=2) as executor:
            future = executor.submit(pow, 2, 10)
            assert future.result() == 1024

    def test_submit_priority(self):
        with VProcessPoolExecutor(max_workers=2) as executor:
            future = executor.submit_priority(1, pow, 3, 3)
            assert future.result() == 27

    def test_map(self):
        with VProcessPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(pow, [1, 2, 3], [2, 3, 4]))
            assert results == [1, 8, 81]


class TestUtilityFunctions:
    """工具函数测试"""

    def test_gather_futures(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(lambda: 1)
            f2 = executor.submit(lambda: 2)
            results = gather_futures([f1, f2])
            assert results == [1, 2]

    def test_wait_any(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(lambda: time.sleep(0.5))
            f2 = executor.submit(lambda: 'fast')
            done, not_done = wait_any([f2])
            assert 'fast' in [f.result() for f in done]

    def test_wait_all(self):
        with VThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(lambda: 1)
            f2 = executor.submit(lambda: 2)
            done = wait_all([f1, f2])
            assert len(done) == 2

    def test_map_async(self):
        results = list(map_async(lambda x: x * 2, [1, 2, 3], max_workers=2))
        assert results == [2, 4, 6]

    def test_run_async(self):
        loop = run_async(lambda: 42)
        assert loop is not None
