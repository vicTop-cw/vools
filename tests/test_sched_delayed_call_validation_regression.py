# -*- coding: utf-8 -*-
"""回归测试：delayed_call 参数校验（BUG-400）。

`delayed_call` 把参数原样交给 ``threading.Timer``，零校验：

    delayed_call('x', print)      # 接受 → 后台线程里 TypeError，被 threading 吞掉
    delayed_call(1, 'nope')       # 同样静默失败（stderr 只有 "Exception in thread"）
    delayed_call(-1, print)       # 接受 → 立即触发
    delayed_call(-1)              # 装饰器模式同样接受

调用方拿到 Timer 对象、却永远等不到回调，完全没有错误提示。

修复：`seconds` 必须是数字（bool 除外）且 >= 0（0 合法=立即执行）；
`func` 为 None（装饰器模式）或可调用，否则 TypeError；装饰器模式在
`delayed_call(seconds)` 调用时即校验（不再延迟到调用被装饰函数时）。

正常直接调用/装饰器延迟执行行为不变。
"""

import time

import pytest

from vools.vconcurrent.sched_mod import delayed_call


class TestValidation:
    @pytest.mark.parametrize('bad', ['x', None, True, [1]])
    def test_non_numeric_seconds(self, bad):
        with pytest.raises(TypeError) as ei:
            delayed_call(bad, print)
        assert 'seconds' in str(ei.value)

    @pytest.mark.parametrize('bad', [-1, -0.5])
    def test_negative_seconds(self, bad):
        with pytest.raises(ValueError):
            delayed_call(bad, print)
        # 装饰器模式同样在装饰期报错
        with pytest.raises(ValueError):
            delayed_call(bad)

    @pytest.mark.parametrize('bad', ['nope', 42, object()])
    def test_non_callable_func(self, bad):
        with pytest.raises(TypeError) as ei:
            delayed_call(1, bad)
        assert 'func' in str(ei.value)

    @pytest.mark.parametrize('bad', ['x', None])
    def test_decorator_mode_seconds(self, bad):
        with pytest.raises(TypeError):
            delayed_call(bad)


class TestValidUsageUnchanged:
    def test_direct_call(self):
        hits = []
        thread = delayed_call(0.05, lambda x: hits.append(x), 7)
        assert type(thread).__name__ == 'Timer'
        time.sleep(0.25)
        assert hits == [7]

    def test_zero_seconds(self):
        hits = []
        delayed_call(0, lambda: hits.append(1))
        time.sleep(0.1)
        assert hits == [1]

    def test_decorator(self):
        hits = []

        @delayed_call(0.05)
        def greet(name):
            hits.append(name)

        greet('world')
        time.sleep(0.25)
        assert hits == ['world']

    def test_kwargs_forwarded(self):
        hits = []

        def target(a, b=None):
            hits.append((a, b))

        delayed_call(0.02, target, 1, b=2)
        time.sleep(0.2)
        assert hits == [(1, 2)]