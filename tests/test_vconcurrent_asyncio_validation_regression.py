# -*- coding: utf-8 -*-
"""回归测试：asyncio_mod 的 maxsize / delay / timeout 校验（BUG-496）。

修复前：

    AsyncQueue(maxsize="x")   # 一路到 repr 才抛 cryptic
                              #   "TypeError: %d format: a real number is required, not str"
    delay(-1, coro)           # 负延迟静默等价于"无延迟"（asyncio.sleep 负值直接返回）
    delay("x", coro)          # 到 sleep 内部才炸
    timeout(coro, 0) / (coro, -1)   # 立即超时（配置错误被当成"超时了"）
    timeout(coro, "x")        # 内部才炸

修复后入口即校验（带参数名），且**校验失败时关闭传入协程**——避免 GC 时的
"coroutine was never awaited" RuntimeWarning（与 BUG-404 的处理同源）。
"""

import asyncio

import pytest

from vools.vconcurrent.asyncio_mod import AsyncQueue, delay, timeout


async def _one():
    return 1


async def _slow():
    await asyncio.sleep(0.3)
    return "slow"


class TestAsyncQueueMaxsize:
    @pytest.mark.parametrize("bad", ["x", None, 1.5])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            AsyncQueue(maxsize=bad)
        assert "maxsize" in str(ei.value)

    @pytest.mark.parametrize("ok", [0, 1, -1])
    def test_int_accepted_including_unbounded(self, ok):
        assert AsyncQueue(maxsize=ok).maxsize == ok


class TestDelayValidation:
    @pytest.mark.parametrize("bad", ["x", None])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            asyncio.run(delay(bad, _one()))
        assert "seconds" in str(ei.value)

    def test_negative(self):
        with pytest.raises(ValueError) as ei:
            asyncio.run(delay(-1, _one()))
        assert "seconds" in str(ei.value)

    def test_valid(self):
        assert asyncio.run(delay(0.01, _one())) == 1

    def test_zero_allowed(self):
        assert asyncio.run(delay(0, _one())) == 1


class TestTimeoutValidation:
    @pytest.mark.parametrize("bad", ["x", None])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            asyncio.run(timeout(_one(), bad))
        assert "seconds" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive(self, bad):
        with pytest.raises(ValueError) as ei:
            asyncio.run(timeout(_one(), bad))
        assert "seconds" in str(ei.value)

    def test_success(self):
        assert asyncio.run(timeout(_one(), 1)) == 1

    def test_real_timeout(self):
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(timeout(_slow(), 0.05))


class TestNoCoroutineLeak:
    def test_validation_failure_closes_coro(self):
        """校验失败时不应产生 "coroutine was never awaited" 警告。"""
        import gc
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(ValueError):
                asyncio.run(delay(-1, _one()))
            gc.collect()
            leaks = [w for w in caught if "never awaited" in str(w.message)]
        assert leaks == []


class TestOtherPrimitivesUnchanged:
    def test_lock_and_semaphore(self):
        from vools.vconcurrent.asyncio_mod import AsyncLock, AsyncSemaphore

        async def scenario():
            lock = AsyncLock()
            assert lock.locked() is False
            await lock.acquire()
            assert lock.locked() is True
            lock.release()

            sem = AsyncSemaphore(2)
            assert sem.value == 2
            await sem.acquire()
            assert sem.value == 1
            sem.release()
            return "ok"

        assert asyncio.run(scenario()) == "ok"

    def test_gather_return_exceptions(self):
        from vools.vconcurrent.asyncio_mod import gather

        async def boom():
            raise ValueError("boom")

        async def scenario():
            results = await gather(_one(), boom(), return_exceptions=True)
            assert results[0] == 1
            assert isinstance(results[1], ValueError)
            return "ok"

        assert asyncio.run(scenario()) == "ok"

    def test_pool_max_workers_validated(self):
        from vools.vconcurrent.asyncio_mod import AsyncPool

        with pytest.raises(ValueError):
            AsyncPool(max_workers=0)
        with pytest.raises(ValueError):
            AsyncPool(max_workers=-1)
