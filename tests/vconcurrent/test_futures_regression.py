"""tests/vconcurrent/test_futures_regression.py — VThreadPoolExecutor 回归测试"""
import time
import threading
import pytest

from vools.concurrent.futures import VThreadPoolExecutor, VProcessPoolExecutor


class TestShutdownGraceful:
    """BUG-A 回归测试：shutdown_graceful 不在循环中持有锁"""

    def test_no_deadlock_normal_completion(self):
        """正常完成的任务不应死锁"""
        pool = VThreadPoolExecutor(max_workers=2)
        for _ in range(4):
            pool.submit(lambda: time.sleep(0.01))
        result = pool.shutdown_graceful(wait=True, timeout=5.0)
        assert result is True
        assert pool.pending_count == 0
        assert pool.completed_count == 4

    def test_timeout_returns_false(self):
        """超时后应返回 False 而不是死锁"""
        pool = VThreadPoolExecutor(max_workers=2)
        for _ in range(4):
            pool.submit(lambda: time.sleep(1.0))
        result = pool.shutdown_graceful(wait=True, timeout=0.2)
        assert result is False
        assert pool.pending_count > 0

    def test_wait_false_returns_immediately(self):
        """wait=False 应立即返回 True"""
        pool = VThreadPoolExecutor(max_workers=2)
        for _ in range(4):
            pool.submit(lambda: time.sleep(0.01))
        result = pool.shutdown_graceful(wait=False)
        assert result is True

    def test_thread_leak_check(self):
        """shutdown_graceful 不应泄漏线程"""
        before = set(t.name for t in threading.enumerate() if 'VThreadPool' in t.name)
        pool = VThreadPoolExecutor(max_workers=3, thread_name_prefix="RegTest")
        for _ in range(6):
            pool.submit(lambda: time.sleep(0.05))
        pool.shutdown_graceful(wait=True, timeout=5.0)
        time.sleep(0.1)
        after = set(t.name for t in threading.enumerate() if 'RegTest' in t.name)
        leaked = after - before
        assert len(leaked) == 0, f"Leaked threads: {leaked}"

    def test_concurrent_submit_and_shutdown(self):
        """并发提交与 shutdown_graceful 不应死锁"""
        pool = VThreadPoolExecutor(max_workers=2)

        def submit_loop():
            for _ in range(5):
                try:
                    pool.submit(lambda: time.sleep(0.01))
                except RuntimeError:
                    break
                time.sleep(0.01)

        t = threading.Thread(target=submit_loop)
        t.start()
        time.sleep(0.05)
        result = pool.shutdown_graceful(wait=True, timeout=3.0)
        t.join(timeout=3)
        assert result is True


class TestVProcessPoolGraceful:
    """BUG-A 回归测试：VProcessPoolExecutor.shutdown_graceful 同样修复"""

    def test_no_deadlock_normal_completion(self):
        """进程池正常完成不应死锁"""
        pool = VProcessPoolExecutor(max_workers=2)
        for _ in range(3):
            pool.submit(pow, 2, 10)
        result = pool.shutdown_graceful(wait=True, timeout=10.0)
        assert result is True
        assert pool.pending_count == 0
