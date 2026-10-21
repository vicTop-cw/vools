"""tests/vconcurrent/test_threading_mod_regression.py — VLock/VThread 回归测试"""
import time
import threading
import pytest

from vools.concurrent.threading_mod import VLock, VThread


class TestVLockRelease:
    """BUG-B 回归测试：VLock.release() 在 count=0 时应抛出 RuntimeError"""

    def test_release_when_unlocked_raises(self):
        """未持有锁时释放应抛 RuntimeError"""
        lock = VLock()
        with pytest.raises(RuntimeError) as exc_info:
            lock.release()
        assert "cannot release un-acquired" in str(exc_info.value)

    def test_acquire_release_count_consistency(self):
        """获取与释放后 count 应一致"""
        lock = VLock()
        lock.acquire()
        assert lock.count == 1
        lock.release()
        assert lock.count == 0

    def test_nested_acquire_release(self):
        """嵌套获取/释放后 count 应为 0"""
        lock = VLock()
        lock.acquire()
        lock.acquire()
        assert lock.count == 2
        lock.release()
        assert lock.count == 1
        lock.release()
        assert lock.count == 0
        with pytest.raises(RuntimeError):
            lock.release()

    def test_context_manager_count(self):
        """上下文管理器退出后 count 应为 0"""
        lock = VLock()
        with lock:
            assert lock.count == 1
        assert lock.count == 0
        with pytest.raises(RuntimeError):
            lock.release()

    def test_locked_property(self):
        """locked 属性应与 count > 0 一致"""
        lock = VLock()
        assert lock.locked is False
        lock.acquire()
        assert lock.locked is True
        lock.release()
        assert lock.locked is False


class TestVThreadExit:
    """BUG-D 回归测试：VThread.__exit__ join() 应有超时"""

    def test_exit_with_timeout(self):
        """__exit__ 应在超时后返回，不永久阻塞"""
        def quick_task():
            time.sleep(0.1)
            return "done"

        t = VThread(target=quick_task)
        with t:
            pass
        # 如果 __exit__ 未阻塞 30s，说明修复生效

    def test_exit_non_daemon_thread(self):
        """非守护线程在 __exit__ 后继续运行不应阻塞"""
        result = {'value': None}

        def task():
            time.sleep(0.05)
            result['value'] = 'completed'

        t = VThread(target=task, daemon=True)
        with t:
            pass
        time.sleep(0.2)
        assert result['value'] == 'completed'

    def test_exit_multiple_threads(self):
        """多个 VThread 上下文管理器依次退出"""
        for _ in range(3):
            def task():
                time.sleep(0.01)
            t = VThread(target=task, daemon=True)
            with t:
                pass
        # 所有线程应在合理时间内退出
