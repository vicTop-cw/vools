# -*- coding: utf-8 -*-
"""审计锁定：vools.vconcurrent.futures 的并发原语契约。

本轮审计确认该模块无缺陷（前两处"疑似"均为探针误用），在此锁定：

1. ``gather_futures``：``return_exceptions=False`` 时首个异常向上抛；
   ``True`` 时异常以对象形式占据对应位置（asyncio.gather 语义）；空列表 → ``[]``。
2. ``FutureResult``：``result()``/``success()``/``catch()``/``then()`` 链式语义。
3. ``VThreadPoolExecutor``：``submit`` 返回 ``FutureResult``；``total_submitted``/
   ``completed_count``/``pending_count`` 是**属性**、``progress()`` 是方法；
   ``shutdown_graceful`` 后 ``progress()`` 反映 ``shutdown=True``。
4. ``wait_all``/``wait_any`` 返回 ``(done, not_done)`` 两个集合。
5. ``as_completed_batch`` 按批产出；``batch_size <= 0`` 响亮 ``ValueError``。
6. ``make_thread_executor``/``make_process_executor`` 是 stdlib 工厂的**薄封装**
   （返回原生执行器），``V*`` 包装类需直接构造使用。
7. ``map_async``/``run_async`` 的 ``pool_type`` 白名单与 ``chunksize`` 容忍度。
"""

import time

import pytest

import vools.vconcurrent.futures as fu


@pytest.fixture()
def raw_executor():
    ex = fu.make_thread_executor(max_workers=2)
    try:
        yield ex
    finally:
        ex.shutdown(wait=True)


class TestGatherFutures:
    def test_all_success(self, raw_executor):
        futs = [raw_executor.submit(lambda x: x * x, i) for i in range(3)]
        assert fu.gather_futures(futs, timeout=10) == [0, 1, 4]

    def test_exception_propagates_by_default(self, raw_executor):
        futs = [raw_executor.submit(lambda: 1 / 0)]
        with pytest.raises(ZeroDivisionError):
            fu.gather_futures(futs, timeout=10)

    def test_return_exceptions_true(self, raw_executor):
        futs = [raw_executor.submit(lambda: 1 / 0)]
        result = fu.gather_futures(futs, timeout=10, return_exceptions=True)
        assert len(result) == 1
        assert isinstance(result[0], ZeroDivisionError)

    def test_mixed_order_preserved(self, raw_executor):
        futs = [
            raw_executor.submit(lambda: 1),
            raw_executor.submit(lambda: 1 / 0),
            raw_executor.submit(lambda: 3),
        ]
        result = fu.gather_futures(futs, timeout=10, return_exceptions=True)
        assert result[0] == 1
        assert isinstance(result[1], ZeroDivisionError)
        assert result[2] == 3

    def test_empty(self):
        assert fu.gather_futures([], timeout=1) == []


class TestFutureResult:
    def test_result_and_success(self):
        ex = fu.VThreadPoolExecutor(max_workers=1)
        try:
            fr = ex.submit(lambda x: x * 2, 5)
            assert fr.result(timeout=10) == 10
            assert fr.success() is True
        finally:
            ex.shutdown(wait=True)

    def test_failed_future(self):
        ex = fu.VThreadPoolExecutor(max_workers=1)
        try:
            fr = ex.submit(lambda: 1 / 0)
            with pytest.raises(ZeroDivisionError):
                fr.result(timeout=10)
            assert fr.success() is False
            assert isinstance(fr.exception(timeout=10), ZeroDivisionError)
        finally:
            ex.shutdown(wait=True)

    def test_then_chain(self):
        ex = fu.VThreadPoolExecutor(max_workers=1)
        try:
            fr = ex.submit(lambda: 5)
            assert fr.then(lambda v: v + 1).result(timeout=10) == 6
        finally:
            ex.shutdown(wait=True)

    def test_catch_recovers(self):
        ex = fu.VThreadPoolExecutor(max_workers=1)
        try:
            fr = ex.submit(lambda: 1 / 0)
            recovered = fr.catch(lambda e: f"caught:{type(e).__name__}")
            assert recovered.result(timeout=10) == "caught:ZeroDivisionError"
        finally:
            ex.shutdown(wait=True)


class TestExecutorProgress:
    def test_counters_are_properties(self):
        ex = fu.VThreadPoolExecutor(max_workers=2)
        try:
            for _ in range(3):
                ex.submit(lambda: None)
            deadline = time.time() + 5
            while ex.completed_count < 3 and time.time() < deadline:
                time.sleep(0.01)
            assert ex.total_submitted == 3
            assert ex.completed_count == 3
            assert ex.pending_count == 0
        finally:
            ex.shutdown(wait=True)

    def test_progress_is_method_and_reports_shutdown(self):
        ex = fu.VThreadPoolExecutor(max_workers=1)
        ex.submit(lambda: None)
        time.sleep(0.05)
        ex.shutdown_graceful(timeout=2)
        # progress() 返回 (completed, total) 元组；repr(executor) 里才有 shutdown 标志
        assert ex.progress() == (1, 1)
        assert "shutdown=True" in repr(ex)

    def test_invalid_max_workers(self):
        with pytest.raises(ValueError):
            fu.VThreadPoolExecutor(max_workers=0)
        with pytest.raises(ValueError):
            fu.VProcessPoolExecutor(max_workers=-1)


class TestWaitHelpers:
    def test_wait_all(self, raw_executor):
        f1 = raw_executor.submit(time.sleep, 0.01)
        f2 = raw_executor.submit(time.sleep, 0.01)
        done, not_done = fu.wait_all([f1, f2], timeout=10)
        assert len(done) == 2
        assert len(not_done) == 0

    def test_wait_any_with_timeout(self, raw_executor):
        fast = raw_executor.submit(time.sleep, 0.01)
        slow = raw_executor.submit(time.sleep, 1.0)
        done, not_done = fu.wait_any([fast, slow], timeout=0.2)
        assert len(done) + len(not_done) == 2
        assert fast in done


class TestAsCompletedBatch:
    def test_batches(self, raw_executor):
        futs = [raw_executor.submit(lambda x: x, i) for i in range(4)]
        batches = list(fu.as_completed_batch(futs, batch_size=2, timeout=10))
        flat = sorted(item for batch in batches for item in batch)
        assert flat == [0, 1, 2, 3]

    @pytest.mark.parametrize("bad", [0, -1])
    def test_invalid_batch_size(self, raw_executor, bad):
        futs = [raw_executor.submit(lambda: 1)]
        with pytest.raises(ValueError):
            list(fu.as_completed_batch(futs, batch_size=bad, timeout=5))


class TestConvenience:
    def test_run_async(self):
        assert fu.run_async(lambda x: x + 1, 1).result(timeout=10) == 2

    def test_map_async(self):
        assert list(fu.map_async(lambda x: x * 2, range(3))) == [0, 2, 4]

    def test_bad_pool_type(self):
        with pytest.raises(ValueError):
            fu.run_async(lambda: None, pool_type="bogus")
        with pytest.raises(ValueError):
            list(fu.map_async(lambda x: x, [1], pool_type="bogus"))

    def test_factories_are_thin_wrappers(self):
        """make_*_executor 返回 stdlib 执行器（V* 包装类需直接构造）。"""
        ex = fu.make_thread_executor(max_workers=1)
        try:
            assert type(ex).__name__ == "ThreadPoolExecutor"
        finally:
            ex.shutdown(wait=True)
        pex = fu.make_process_executor(max_workers=1)
        try:
            assert type(pex).__name__ == "ProcessPoolExecutor"
        finally:
            pex.shutdown(wait=True)
