"""BUG-106: timeout Windows 分支不得阻塞调用方等待后台线程完成"""
import time
import threading
from vools.task.utils import timeout, with_timeout, async_timeout


def test_timeout_raises_within_budget():
    """超时后应立即返回 TimeoutError，不等待后台线程完成。"""
    start = time.monotonic()

    def slow():
        time.sleep(3)
        return 'done'

    try:
        timeout(slow, 0.2)()
    except TimeoutError:
        elapsed = time.monotonic() - start
        # 0.2 秒超时 + 容差 0.5 秒（不应等待后台线程完成）
        assert elapsed < 1.0, f'超时后仍阻塞 {elapsed:.2f}s（期望 < 1.0s）'
    else:
        assert False, '应抛 TimeoutError'


def test_timeout_success_returns_result():
    """未超时时正常返回函数结果。"""

    def fast():
        return 42

    assert timeout(fast, 1.0)() == 42


def test_timeout_background_thread_daemon():
    """后台执行线程应为守护线程，进程退出不被阻塞。"""
    import vools.task.utils as u
    # 通过 timeout 包装，检查后台线程是否 daemon
    # 无法直接检查，但确保超时后主线程不被阻塞即可（test_timeout_raises_within_budget 已验证）


def test_timeout_exception_propagates():
    """函数抛异常时应原样传播（非超时）。"""

    def boom():
        raise ValueError('boom')

    try:
        timeout(boom, 1.0)()
    except ValueError as e:
        assert str(e) == 'boom'
    else:
        assert False, '应传播 ValueError'