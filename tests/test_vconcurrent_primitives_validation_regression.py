# -*- coding: utf-8 -*-
"""回归测试：vconcurrent 原语的参数校验（BUG-346）。

修复前：

    VLatch("x")                 # TypeError: '<' not supported between instances of 'str' and 'int'
    VBarrier("x")               # 同上（parties）
    VSemaphore("x")             # 同上（value）
    sem = VSemaphore(1)
    sem.acquire("x")            # **永久阻塞**！truthy 的 blocking 被当成 True 且
                                # timeout=None —— 调用方以为自己传了超时

修复：三个构造函数校验整数（bool 拒绝）；``acquire`` 校验 blocking 必须 bool、
timeout 必须非负数值，且 blocking=False 带 timeout 时按 threading 语义抛 ValueError；
``acquire_timeout`` 同样校验 timeout。

本文件里的阻塞类断言都带较小时限并通过子线程/超时参数保护，避免测试挂死。
"""

import threading
import time

import pytest

from vools.vconcurrent.threading_mod import VBarrier, VLatch, VSemaphore


class TestLatchValidation:
    @pytest.mark.parametrize("bad", ["x", None, 1.5, True])
    def test_non_int_count(self, bad):
        with pytest.raises(TypeError) as ei:
            VLatch(bad)
        assert "count" in str(ei.value)

    def test_negative(self):
        with pytest.raises(ValueError):
            VLatch(-1)

    def test_valid(self):
        assert VLatch(2) is not None
        assert VLatch(0) is not None


class TestBarrierValidation:
    @pytest.mark.parametrize("bad", ["x", None, 1.5, True])
    def test_non_int_parties(self, bad):
        with pytest.raises(TypeError) as ei:
            VBarrier(bad)
        assert "parties" in str(ei.value)

    def test_negative(self):
        with pytest.raises(ValueError):
            VBarrier(-1)

    def test_valid(self):
        assert VBarrier(2) is not None


class TestSemaphoreConstructorValidation:
    @pytest.mark.parametrize("bad", ["x", None, 1.5, True])
    def test_non_int_value(self, bad):
        with pytest.raises(TypeError) as ei:
            VSemaphore(bad)
        assert "value" in str(ei.value)

    def test_negative(self):
        with pytest.raises(ValueError):
            VSemaphore(-1)

    def test_valid(self):
        assert VSemaphore(2) is not None
        assert VSemaphore(0) is not None


class TestSemaphoreAcquireValidation:
    @pytest.mark.parametrize("bad", ["x", 1, 0.5, None])
    def test_blocking_must_be_bool(self, bad):
        """修复前 acquire('x') 会把 truthy 当 blocking=True 永久阻塞。"""
        sem = VSemaphore(1)
        with pytest.raises(TypeError) as ei:
            sem.acquire(blocking=bad)
        assert "blocking" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_timeout_type(self, bad):
        sem = VSemaphore(1)
        with pytest.raises(TypeError) as ei:
            sem.acquire(blocking=True, timeout=bad)
        assert "timeout" in str(ei.value)

    def test_negative_timeout(self):
        sem = VSemaphore(1)
        with pytest.raises(ValueError):
            sem.acquire(blocking=True, timeout=-1)

    def test_non_blocking_with_timeout(self):
        sem = VSemaphore(1)
        with pytest.raises(ValueError):
            sem.acquire(blocking=False, timeout=1)

    @pytest.mark.parametrize("bad", ["x", None, [1]])
    def test_acquire_timeout_type(self, bad):
        sem = VSemaphore(1)
        with pytest.raises(TypeError) as ei:
            sem.acquire_timeout(bad)
        assert "timeout" in str(ei.value)

    def test_acquire_timeout_negative(self):
        sem = VSemaphore(1)
        with pytest.raises(ValueError):
            sem.acquire_timeout(-1)


class TestSemaphoreBehaviourUnchanged:
    def test_acquire_timeout_returns_false_when_exhausted(self):
        sem = VSemaphore(1)
        assert sem.acquire_timeout(0.01) is True
        started = time.time()
        assert sem.acquire_timeout(0.05) is False
        # 必须真的在超时附近返回，而不是永久阻塞
        assert time.time() - started < 2.0

    def test_blocking_with_timeout(self):
        sem = VSemaphore(1)
        assert sem.acquire(blocking=True, timeout=0.05) is True
        assert sem.acquire(blocking=True, timeout=0.05) is False

    def test_non_blocking(self):
        sem = VSemaphore(1)
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is False

    def test_release_and_context_manager(self):
        sem = VSemaphore(1)
        with sem:
            assert sem.acquire(blocking=False) is False
        assert sem.acquire(blocking=False) is True

    def test_release_non_positive_noop(self):
        sem = VSemaphore(1)
        assert sem.release(0) is None
        assert sem.release(-1) is None


class TestLatchBehaviourUnchanged:
    def test_count_down_and_wait(self):
        latch = VLatch(1)
        assert latch.wait(0.01) is False
        latch.count_down()
        assert latch.wait(0.05) is True
