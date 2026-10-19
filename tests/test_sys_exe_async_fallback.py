# -*- coding: utf-8 -*-
"""回归测试：@exe 装饰器的 async fallback 必须被 await 而非透传 coroutine object。

覆盖 BUG-197：exe.py 与 dll.py 同根的 async fallback 泄漏，同步 wrapper 与
async_mode 两条路径都曾返回未 await 的 coroutine object 并触发 RuntimeWarning。
"""

import asyncio

import pytest

from vools.sys.exe import exe


class TestExeAsyncFallback:
    """async_mode=True 的 fallback 必须 await coroutine。"""

    def test_async_fallback_returns_value(self):
        @exe("nonexistent.bin", async_mode=True)
        async def foo(a):
            return a + 1

        # BUG-197 前返回 <coroutine object foo> 并报 never awaited，现应得 2
        assert asyncio.run(foo(1)) == 2

    def test_async_no_fallback_raises(self):
        @exe("nonexistent.bin", async_mode=True)
        async def bar():
            pass

        with pytest.raises((FileNotFoundError, OSError)):
            asyncio.run(bar())


class TestExeSyncDecoratorAsyncFunction:
    """同步 @exe 装饰 async 函数：fallback 须同步返回结果。"""

    def test_sync_wrapper_drives_coroutine(self):
        @exe("nonexistent.bin")
        async def foo(a):
            return a + 1

        # BUG-197 前返回 coroutine object，现应同步得 2
        assert foo(1) == 2
        assert not asyncio.iscoroutine(foo(1))

    def test_sync_pass_body_raises(self):
        @exe("nonexistent.bin")
        async def bar():
            pass

        with pytest.raises((FileNotFoundError, OSError)):
            bar()