# -*- coding: utf-8 -*-
"""回归测试：@bridge 装饰器的 async fallback 必须被 await 而非透传 coroutine object。

覆盖 BUG-198：bridge_decorator.py 的 wrapper 同步返回 fallback 结果，若 fallback 是
async 函数则曾返回未 await 的 coroutine object。现 wrapper 用 asyncio.run 驱动它。
"""

import asyncio

import pytest

from vools.decorators.bridge_decorator import bridge


def _unavailable_symbol():
    # 一个几乎不可能被桥接库提供的符号名，保证走 fallback 路径
    return "serialize.definitely_not_exists_symbol_9z7q"


class TestBridgeAsyncFallback:
    """显式 async fallback 必须同步返回结果（BUG-198）。"""

    def test_fallback_path_returns_value(self):
        async def py_fallback(a):
            return a + 1

        @bridge("nim", _unavailable_symbol(), fallback=py_fallback)
        def foo(a):
            pass

        # BUG-198 前返回 coroutine object，现应同步得 2
        r = foo(1)
        assert r == 2
        assert not asyncio.iscoroutine(r)

    def test_fallback_multiple(self):
        async def py_fallback(a, b):
            return a * b

        @bridge("rust", _unavailable_symbol(), fallback=py_fallback)
        def mul(a, b):
            pass

        r = mul(6, 7)
        assert r == 42
        assert not asyncio.iscoroutine(r)

    def test_no_fallback_raises(self):
        @bridge("go", _unavailable_symbol())
        def bar():
            pass

        with pytest.raises(RuntimeError):
            bar()

    def test_sync_fallback_unchanged(self):
        def py_fallback(a):
            return a + 1

        @bridge("scala", _unavailable_symbol(), fallback=py_fallback)
        def foo(a):
            pass

        assert foo(1) == 2