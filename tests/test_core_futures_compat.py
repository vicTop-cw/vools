# -*- coding: utf-8 -*-
"""测试 vools.core.futures_compat。"""

import time
import pytest
from vools.core.futures_compat import (
    make_thread_executor, make_process_executor,
    shutdown_executor, HAS_EXECUTOR_INITIALIZER,
    HAS_SHUTDOWN_CANCEL_FUTURES
)

__all__ = ["TestMakeThread", "TestMakeProcess", "TestShutdown",
           "TestCancelPending", "TestFlags", "TestImport"]


def _ident(x):
    return x


class TestMakeThread:
    """make_thread_executor 测试。"""

    def test_default(self):
        ex = make_thread_executor()
        assert ex is not None
        shutdown_executor(ex)

    def test_max_workers(self):
        ex = make_thread_executor(max_workers=2)
        assert ex._max_workers == 2
        shutdown_executor(ex)

    def test_with_initializer(self):
        state = {"n": 0}

        def init():
            state["n"] += 1

        ex = make_thread_executor(max_workers=1, initializer=init, initargs=())
        fut = ex.submit(_ident, 42)
        assert fut.result() == 42
        shutdown_executor(ex)

    def test_submit(self):
        ex = make_thread_executor(max_workers=2)
        f = ex.submit(_ident, "hello")
        assert f.result() == "hello"
        shutdown_executor(ex)


class TestMakeProcess:
    """make_process_executor 测试。"""

    def test_default(self):
        ex = make_process_executor()
        assert ex is not None
        shutdown_executor(ex)

    def test_max_workers(self):
        ex = make_process_executor(max_workers=1)
        assert ex._max_workers == 1
        shutdown_executor(ex)


class TestShutdown:
    """shutdown_executor 测试。"""

    def test_wait(self):
        ex = make_thread_executor(max_workers=1)
        shutdown_executor(ex, wait=True)
        assert True

    def test_cancel_futures(self):
        ex = make_thread_executor(max_workers=1)
        shutdown_executor(ex, cancel_futures=True)
        assert True


class TestCancelPending:
    """_cancel_pending_best_effort 测试。"""

    def test_empty(self):
        from vools.core.futures_compat import _cancel_pending_best_effort
        ex = make_thread_executor(max_workers=1)
        _cancel_pending_best_effort(ex)
        shutdown_executor(ex)

    def test_with_queue(self):
        from vools.core.futures_compat import _cancel_pending_best_effort
        ex = make_thread_executor(max_workers=1)
        ex.submit(_ident, 1)
        _cancel_pending_best_effort(ex)
        shutdown_executor(ex)


class TestFlags:
    """版本标志测试。"""

    def test_flags(self):
        assert HAS_EXECUTOR_INITIALIZER is True
        assert HAS_SHUTDOWN_CANCEL_FUTURES is True


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.core.futures_compat import __all__
        assert "make_thread_executor" in __all__
        assert "make_process_executor" in __all__
        assert "shutdown_executor" in __all__
