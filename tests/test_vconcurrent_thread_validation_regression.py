# -*- coding: utf-8 -*-
"""回归测试：threading_mod 构造/装饰参数校验（BUG-492）。

修复前：

    VThread(target=123)      # 起一个"活着但必然 TypeError"的线程（调用期才暴露）
    VThread(args='abc')      # **静默逐字符展开** ('a','b','c') 传给目标函数
                             #   —— 与 BUG-490 的 spawn(args='abc') 同族
    VThread(name=123)        # 静默变成 name='123'
    VThread(daemon='yes')    # 静默当真值
    VThread(kwargs=[1])      # 裸 "cannot convert dictionary update sequence…"
    run_in_thread(daemon='yes') / (name=123)   # 静默接受
    thread_pool(max_workers=0)                 # 装饰期底层 ValueError（不带参数名）

修复后全部在入口以带参数名的 TypeError/ValueError 拒绝。
"""

import time

import pytest

import vools.vconcurrent.threading_mod as tm


class TestVThreadValidation:
    @pytest.mark.parametrize("bad", [123, "x", [1]])
    def test_target_not_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            tm.VThread(target=bad)
        assert "target" in str(ei.value)

    def test_target_none_allowed(self):
        t = tm.VThread(target=None)
        assert t.name

    @pytest.mark.parametrize("bad", [123, 1.5])
    def test_name_type(self, bad):
        with pytest.raises(TypeError) as ei:
            tm.VThread(target=lambda: None, name=bad)
        assert "name" in str(ei.value)

    @pytest.mark.parametrize("bad", ["yes", 1, 0])
    def test_daemon_type(self, bad):
        with pytest.raises(TypeError) as ei:
            tm.VThread(target=lambda: None, daemon=bad)
        assert "daemon" in str(ei.value)

    @pytest.mark.parametrize("bad", ["abc", b"ab", 1])
    def test_args_must_be_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            tm.VThread(target=lambda *a: a, args=bad)
        assert "args" in str(ei.value)

    def test_kwargs_must_be_dict(self):
        with pytest.raises(TypeError) as ei:
            tm.VThread(target=lambda: None, kwargs=[1])
        assert "kwargs" in str(ei.value)


class TestDecoratorValidation:
    def test_run_in_thread_daemon(self):
        with pytest.raises(TypeError) as ei:
            tm.run_in_thread(daemon="yes")
        assert "daemon" in str(ei.value)

    def test_run_in_thread_name(self):
        with pytest.raises(TypeError) as ei:
            tm.run_in_thread(name=123)
        assert "name" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_thread_pool_non_positive(self, bad):
        with pytest.raises(ValueError) as ei:
            tm.thread_pool(max_workers=bad)
        assert "max_workers" in str(ei.value)

    def test_thread_pool_wrong_type(self):
        with pytest.raises(TypeError) as ei:
            tm.thread_pool(max_workers="x")
        assert "max_workers" in str(ei.value)


class TestBehaviourUnchanged:
    def test_vthread_result_and_exception(self):
        t = tm.VThread(target=lambda a, b=0: a + b, args=(1,), kwargs={"b": 2})
        t.start()
        t.join(2)
        assert t.is_done() is True
        assert t.get_result() == 3
        assert t.has_exception is False

        def boom():
            raise ValueError("boom")

        tb = tm.VThread(target=boom)
        tb.start()
        tb.join(2)
        assert tb.has_exception is True
        assert isinstance(tb.exception, ValueError)
        with pytest.raises(ValueError):
            tb.get_result()

    def test_run_in_thread(self):
        @tm.run_in_thread(daemon=True, name="w1")
        def double(x):
            return x * 2

        t = double(21)
        assert t.get_result(2) == 42

    def test_thread_pool(self):
        @tm.thread_pool(max_workers=2)
        def inc(x):
            return x + 1

        assert inc(1).result() == 2

    def test_synchronized(self):
        lock = tm.VLock()
        calls = []

        @tm.synchronized(lock)
        def f(x):
            calls.append(x)
            return x

        assert f(1) == 1
        assert calls == [1]

    def test_vlatch(self):
        latch = tm.VLatch(2)
        assert latch.count == 2
        latch.count_down()
        assert latch.is_released() is False
        latch.count_down()
        assert latch.is_released() is True

    def test_vbarrier_parties(self):
        barrier = tm.VBarrier(2)
        assert barrier.parties == 2
        assert barrier.n_waiting == 0
        assert barrier.broken is False
