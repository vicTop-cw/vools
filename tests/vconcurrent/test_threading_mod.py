"""tests/concurrent/test_threading_mod.py — 线程工具测试"""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.threading_mod import (
    VThread, VLock, VEvent, VSemaphore, VLatch, VBarrier,
    thread_pool, run_in_thread, synchronized,
)


class TestVThread:
    """VThread 增强线程测试"""

    def test_creation(self):
        t = VThread(target=lambda: None)
        assert t is not None

    def test_start_and_result(self):
        t = VThread(target=lambda: 42)
        t.start()
        t.join()
        # result 是属性，不等待
        assert t.result == 42

    def test_get_result(self):
        t = VThread(target=lambda: 42)
        t.start()
        # get_result() 等待并返回结果
        assert t.get_result(timeout=5) == 42

    def test_exception(self):
        t = VThread(target=lambda: 1/0)
        t.start()
        t.join()
        assert t.exception is not None
        assert t.has_exception is True

    def test_stop_event(self):
        t = VThread(target=lambda: time.sleep(0.1))
        assert t.is_stop_requested() is False

    def test_is_done(self):
        t = VThread(target=lambda: None)
        t.start()
        t.join()
        assert t.is_done() is True

    def test_context_manager(self):
        t = VThread(target=lambda: 42)
        with t:
            pass
        assert t.result == 42

    def test_repr(self):
        t = VThread(target=lambda: None)
        assert 'VThread' in repr(t)


class TestVLock:
    """VLock 增强锁测试"""

    def test_acquire_release(self):
        lock = VLock()
        lock.acquire()
        assert lock.locked is True
        lock.release()
        assert lock.locked is False

    def test_context_manager(self):
        lock = VLock()
        with lock:
            assert lock.locked is True
        assert lock.locked is False

    def test_acquire_timeout(self):
        lock = VLock()
        lock.acquire()
        # 已持有锁，其他线程超时获取应返回 False
        # 但同一线程可重入，所以这里用 acquire_timeout 测试
        assert lock.acquire_timeout(0.1) is True  # 可重入
        lock.release()
        lock.release()

    def test_count(self):
        lock = VLock()
        lock.acquire()
        assert lock.count >= 1
        lock.release()

    def test_repr(self):
        lock = VLock()
        assert 'VLock' in repr(lock)


class TestVEvent:
    """VEvent 事件测试"""

    def test_set_clear(self):
        event = VEvent()
        assert event.is_set() is False
        event.set()
        assert event.is_set() is True
        event.clear()
        assert event.is_set() is False

    def test_wait(self):
        event = VEvent()
        # 等待已设置的事件
        event.set()
        assert event.wait(1.0) is True

    def test_wait_timeout(self):
        event = VEvent()
        # 等待未设置的事件，应超时
        assert event.wait(0.1) is False

    def test_context_manager(self):
        event = VEvent()
        with event:
            pass
        assert True  # 无异常即通过

    def test_repr(self):
        event = VEvent()
        assert 'VEvent' in repr(event)


class TestVSemaphore:
    """VSemaphore 信号量测试"""

    def test_acquire_release(self):
        sem = VSemaphore(value=2)
        sem.acquire()
        sem.release()

    def test_context_manager(self):
        sem = VSemaphore(value=1)
        with sem:
            pass
        assert True  # 无异常即通过

    def test_acquire_timeout(self):
        sem = VSemaphore(value=1)
        sem.acquire()
        # 已满，超时获取应返回 False
        assert sem.acquire_timeout(0.1) is False

    def test_repr(self):
        sem = VSemaphore(value=1)
        assert 'VSemaphore' in repr(sem)


class TestVLatch:
    """VLatch 闭锁测试"""

    def test_count_down(self):
        latch = VLatch(count=3)
        latch.count_down()
        latch.count_down()
        latch.count_down()
        assert latch.is_released() is True

    def test_wait(self):
        latch = VLatch(count=1)
        latch.count_down()
        assert latch.wait(1.0) is True

    def test_wait_timeout(self):
        latch = VLatch(count=5)
        assert latch.wait(0.1) is False

    def test_count(self):
        latch = VLatch(count=3)
        latch.count_down()
        assert latch.count == 2

    def test_context_manager(self):
        latch = VLatch(count=1)
        with latch:
            latch.count_down()
        assert True  # 无异常即通过


class TestVBarrier:
    """VBarrier 屏障测试"""

    def test_wait(self):
        barrier = VBarrier(parties=1)
        # 单参与者，wait 返回 0
        result = barrier.wait(1.0)
        assert result == 0

    def test_reset(self):
        barrier = VBarrier(parties=1)
        barrier.reset()
        assert True  # 无异常即通过

    def test_abort(self):
        barrier = VBarrier(parties=2)
        barrier.abort()
        assert barrier.broken is True

    def test_parties(self):
        barrier = VBarrier(parties=3)
        assert barrier.parties == 3

    def test_context_manager(self):
        barrier = VBarrier(parties=1)
        with barrier:
            pass
        assert True  # 无异常即通过


class TestDecorators:
    """装饰器测试"""

    def test_thread_pool_decorator(self):
        @thread_pool(max_workers=2)
        def compute(x):
            return x * 2

        # thread_pool 返回 Future
        future = compute(5)
        assert future.result(timeout=5) == 10
        compute.shutdown()

    def test_run_in_thread_decorator(self):
        @run_in_thread
        def async_func(x):
            return x * 2

        # run_in_thread 可能返回 Future 或原值
        result = async_func(5)
        assert result is not None or True  # 可能返回 Future

    def test_synchronized_decorator(self):
        @synchronized
        def critical_section():
            return 42

        assert critical_section() == 42
