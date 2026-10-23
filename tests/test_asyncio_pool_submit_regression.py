# -*- coding: utf-8 -*-
"""回归测试：AsyncPool.submit 同步返回 Task（BUG-404）。

`AsyncPool.submit` 原先被声明成 ``async def``：

    task = pool.submit(coro)      # 得到的是**协程**，不是文档承诺的 Task
    result = await pool.submit(coro)
    # -> 运行外层协程，返回**内层 Task**（双重包装）；再 await 一次才拿到值
    # 极易静默拿错类型（例如把 Task 当结果存进列表/比较）

修复：`submit` 改为普通同步方法，直接创建并返回 ``asyncio.Task``；
`sawait task` 一次即得结果；池已关闭时抛 RuntimeError（并关闭传入协程，避免
"coroutine was never awaited" 警告）。

同时验证 `map`/`gather`/`close`/上下文管理器、`to_async`/`to_sync`/
`retry_async` 行为不变。
"""

import asyncio
import gc
import warnings

import pytest

from vools.vconcurrent.asyncio_mod import AsyncPool, retry_async, to_async, to_sync


async def _square(x):
    return x * x


class TestSubmitIsSync:
    def test_returns_task(self):
        async def run():
            pool = AsyncPool(max_workers=2)
            try:
                task = pool.submit(_square(3))
                assert isinstance(task, asyncio.Task)
                # 一次 await 即得真实结果（修复前得到的是另一个 Task）
                assert await task == 9
            finally:
                pool.close()

        asyncio.run(run())

    def test_not_coroutine_function(self):
        import inspect

        assert not inspect.iscoroutinefunction(AsyncPool.submit)


class TestOtherPoolMethodsUnchanged:
    def test_map_and_gather(self):
        async def run():
            pool = AsyncPool(max_workers=2)
            try:
                assert await pool.map(_square, [1, 2, 3]) == [1, 4, 9]
                assert await pool.gather(_square(2), _square(3)) == [4, 9]
            finally:
                pool.close()

        asyncio.run(run())

    def test_close_rejects_further_submit(self):
        async def run():
            pool = AsyncPool(max_workers=1)
            pool.close()
            with pytest.raises(RuntimeError):
                pool.submit(_square(1))

        asyncio.run(run())

    def test_close_does_not_leave_unawaited_coroutine(self):
        async def run():
            pool = AsyncPool(max_workers=1)
            pool.close()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                with pytest.raises(RuntimeError):
                    pool.submit(_square(2))
                gc.collect()
            assert not [w for w in caught if 'never awaited' in str(w.message)]

        asyncio.run(run())

    def test_async_context_manager(self):
        async def run():
            async with AsyncPool(max_workers=2) as pool:
                assert await pool.map(_square, [2]) == [4]

        asyncio.run(run())


class TestHelpersUnchanged:
    def test_to_async(self):
        @to_async
        def double(x):
            return x * 2

        async def run():
            assert await double(21) == 42

        asyncio.run(run())

    def test_to_sync_in_sync_context(self):
        @to_sync
        async def double(x):
            return x * 2

        assert double(21) == 42

    def test_retry_async_succeeds_after_failures(self):
        calls = {'n': 0}

        @retry_async(max_retries=2, backoff=0.005)
        async def flaky():
            calls['n'] += 1
            if calls['n'] < 3:
                raise ValueError('retry')
            return 'ok'

        async def run():
            assert await flaky() == 'ok'

        asyncio.run(run())
        assert calls['n'] == 3

    def test_retry_async_exhausted(self):
        calls = {'n': 0}

        @retry_async(max_retries=1, backoff=0.005)
        async def always_fail():
            calls['n'] += 1
            raise RuntimeError('boom')

        async def run():
            with pytest.raises(RuntimeError):
                await always_fail()

        asyncio.run(run())
        assert calls['n'] == 2   # 首次 + 1 次重试