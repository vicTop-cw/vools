# -*- coding: utf-8 -*-
"""回归测试：@dll 装饰器的 async fallback 必须被 await 而非透传 coroutine object。

覆盖两个同根 bug：
- BUG-194：async_mode=True 时 _run_async 需 await fallback 返回的 coroutine。
- BUG-196：同步 @dll（默认）装饰 async 函数时 wrapper 需用 asyncio.run 驱动 coroutine。
"""

import asyncio

import pytest

from vools.sys.dll import dll


class TestAsyncModeFallback:
    """async_mode=True 的 fallback 必须 await coroutine（BUG-194）。"""

    def test_async_fallback_returns_value(self):
        @dll("nonexistent.dll::foo", async_mode=True)
        async def foo(a):
            return a + 1

        # BUG-194 前返回 <coroutine object foo>，现应得 2
        assert asyncio.run(foo(1)) == 2

    def test_async_fallback_multiple(self):
        @dll("nonexistent.dll::mul", async_mode=True)
        async def mul(a, b):
            return a * b

        assert asyncio.run(mul(6, 7)) == 42

    def test_async_no_fallback_raises(self):
        # body 为 pass → actual_fallback 为 None → 应抛 FileNotFoundError
        @dll("nonexistent.dll::bar", async_mode=True)
        async def bar():
            pass

        with pytest.raises(FileNotFoundError):
            asyncio.run(bar())


class TestSyncDecoratorAsyncFunction:
    """同步 @dll 装饰 async 函数：fallback 须同步返回结果（BUG-196）。"""

    def test_sync_wrapper_drives_coroutine(self):
        @dll("nonexistent.dll::foo")
        async def foo(a):
            return a + 1

        # BUG-196 前返回 coroutine object，现应同步得 2
        assert foo(1) == 2
        assert not asyncio.iscoroutine(foo(1))

    def test_sync_wrapper_pass_body_raises(self):
        @dll("nonexistent.dll::bar")
        async def bar():
            pass

        with pytest.raises(FileNotFoundError):
            bar()