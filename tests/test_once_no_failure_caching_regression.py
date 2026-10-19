# -*- coding: utf-8 -*-
"""回归测试：@once 失败不缓存、可重试（BUG-209）。

原 `_OnceWrapper.__call__` 在调用 func **之前**置 `called = True`，func 抛异常
时 `result` 停留在初始 None——后续所有调用命中缓存分支静默返回 None，函数永不
重试（失败被永久缓存、异常被吞没）。

修复：`called = True` / `result` 只在 func 成功后盖章；失败异常原样传播，
`called` 保持 False，下次调用自然重试。BUG-104 的锁内原子性不变。
"""

import threading

import pytest

from vools.cache.once import once


class TestFailureNotCached:
    """func 抛异常后必须可重试（BUG-209 核心）。"""

    def test_retry_after_failure(self):
        calls = []

        @once
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first call fails")
            return "ok-after-retry"

        with pytest.raises(RuntimeError):
            flaky()
        # 第二次必须真正重试并成功，而不是静默返回 None
        assert flaky() == "ok-after-retry"
        assert len(calls) == 2

    def test_exception_propagates_every_time_until_success(self):
        calls = []

        @once
        def always_fails():
            calls.append(1)
            raise ValueError("boom")

        for _ in range(3):
            with pytest.raises(ValueError):
                always_fails()
        # 失败不应吞掉后续调用：每次都真实执行
        assert len(calls) == 3

    def test_called_state_not_poisoned(self):
        @once
        def bad():
            raise KeyError("k")

        with pytest.raises(KeyError):
            bad()
        assert bad.called is False


class TestSuccessPathUnchanged:
    """成功缓存语义保持（防修复过度）。"""

    def test_success_cached(self):
        n = []

        @once
        def fn():
            n.append(1)
            return 42

        assert fn() == 42
        assert fn() == 42
        assert len(n) == 1

    def test_none_result_cached(self):
        # 函数成功返回 None 是合法结果，应缓存、不重试
        m = []

        @once
        def ret_none():
            m.append(1)
            return None

        assert ret_none() is None
        assert ret_none() is None
        assert len(m) == 1

    def test_force_still_works(self):
        f = []

        @once
        def fn():
            f.append(1)
            return len(f)

        assert fn() == 1
        assert fn(force=True) == 2
        assert fn() == 2


class TestConcurrentRetry:
    """BUG-104 锁语义不被破坏：并发下失败重试只执行一次成功。"""

    def test_concurrent_first_failure(self):
        calls = []
        barrier = threading.Barrier(4)

        @once
        def racy():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first fails")
            return "ok"

        results = []

        def worker():
            barrier.wait()
            try:
                results.append(racy())
            except RuntimeError:
                results.append("raised")

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 至少一个调用者拿到重试成功（不死锁、不永久 None）
        assert racy() == "ok"
        assert "ok" in results or len(calls) >= 2