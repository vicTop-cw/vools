# -*- coding: utf-8 -*-
"""测试 vools.task.utils — 函数式工具 / 重试 / 超时 / 装饰器。"""

import asyncio
import time

import pytest

from vools.task.utils import (
    identity, const, compose, pipe, partial,
    retry, catch, finally_fn,
    async_retry, async_timeout,
    with_timeout, with_retry, with_logging,
)

__all__ = ["TestFunctional", "TestTaskHelpers", "TestAsync",
           "TestDecorators", "TestImport"]


class TestFunctional:
    """函数式工具测试。"""

    def test_identity(self):
        assert identity(42) == 42
        assert identity("x") == "x"
        obj = object()
        assert identity(obj) is obj

    def test_const(self):
        f = const(5)
        assert f() == 5
        assert f(1, 2, 3) == 5
        assert f(a=1, b=2) == 5

    def test_compose(self):
        f = compose(lambda x: x + 1, lambda x: x * 2)
        assert f(3) == 7  # (3 * 2) + 1

    def test_compose_empty(self):
        assert compose()(42) == 42

    def test_compose_single(self):
        f = compose(lambda x: x + 1)
        assert f(1) == 2

    def test_pipe(self):
        f = pipe(lambda x: x * 2, lambda x: x + 1)
        assert f(3) == 7  # (3 * 2) + 1

    def test_pipe_empty(self):
        assert pipe()(42) == 42

    def test_partial(self):
        add = partial(lambda a, b: a + b, 1)
        assert add(2) == 3

    def test_partial_kwargs(self):
        f = partial(lambda a, b=0: a + b, b=5)
        assert f(1) == 6


class TestTaskHelpers:
    """任务辅助函数测试。"""

    def test_retry_success(self):
        calls = []
        def f():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("retry")
            return "done"
        result = retry(f, times=5, delay=0.01)
        assert result == "done"
        assert len(calls) == 3

    def test_retry_all_fail(self):
        def f():
            raise ValueError("always")
        with pytest.raises(ValueError, match="always"):
            retry(f, times=3, delay=0.01)

    def test_retry_no_retry_on_success(self):
        calls = []
        def f():
            calls.append(1)
            return "ok"
        result = retry(f, times=3, delay=0.01)
        assert result == "ok"
        assert len(calls) == 1

    def test_catch_success(self):
        assert catch(lambda: 42) == 42

    def test_catch_failure(self):
        assert catch(lambda: int("not a number"), default=0) == 0

    def test_catch_custom_exception(self):
        # ValueError 未在 exceptions 中 → 传播
        with pytest.raises(ValueError):
            catch(lambda: int("x"), exceptions=(KeyError,))

    def test_finally_fn(self):
        seen = []
        def main():
            seen.append("main")
            return 1
        def cleanup():
            seen.append("cleanup")
        wrapped = finally_fn(main, cleanup)
        assert wrapped() == 1
        assert seen == ["main", "cleanup"]

    def test_finally_fn_on_error(self):
        seen = []
        def main():
            raise ValueError("boom")
        def cleanup():
            seen.append("cleanup")
        wrapped = finally_fn(main, cleanup)
        with pytest.raises(ValueError):
            wrapped()
        assert seen == ["cleanup"]


class TestAsync:
    """异步工具测试。"""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_async_retry_success(self):
        calls = []
        async def f():
            calls.append(1)
            if len(calls) < 2:
                raise ValueError("retry")
            return "ok"
        result = self._run(async_retry(f, times=3, delay=0.01))
        assert result == "ok"

    def test_async_retry_fail(self):
        async def f():
            raise ValueError("always")
        with pytest.raises(ValueError):
            self._run(async_retry(f, times=3, delay=0.01))

    def test_async_timeout_success(self):
        async def f():
            await asyncio.sleep(0.01)
            return "done"
        result = self._run(async_timeout(f(), seconds=1.0))
        assert result == "done"

    def test_async_timeout_expired(self):
        async def f():
            await asyncio.sleep(1.0)
            return "late"
        with pytest.raises(asyncio.TimeoutError):
            self._run(async_timeout(f(), seconds=0.01))


class TestDecorators:
    """装饰器测试。"""

    def test_with_timeout_success(self):
        @with_timeout(1.0)
        def quick():
            return "ok"
        assert quick() == "ok"

    def test_with_timeout_expired(self):
        @with_timeout(0.1)
        def slow():
            time.sleep(1.0)
            return "late"
        with pytest.raises(TimeoutError):
            slow()

    def test_with_retry_success(self):
        calls = []
        @with_retry(times=3, delay=0.01)
        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise ValueError("retry")
            return "ok"
        assert flaky() == "ok"

    def test_with_retry_fail(self):
        @with_retry(times=2, delay=0.01)
        def always_fail():
            raise ValueError("boom")
        with pytest.raises(ValueError):
            always_fail()

    def test_with_logging_success(self, capsys):
        @with_logging()
        def task():
            return 1
        assert task() == 1
        out = capsys.readouterr().out
        assert "[START] task" in out
        assert "[END] task" in out

    def test_with_logging_error(self, capsys):
        @with_logging()
        def task():
            raise ValueError("boom")
        with pytest.raises(ValueError):
            task()
        out = capsys.readouterr().out
        assert "[START] task" in out
        assert "[ERROR] task" in out


class TestImport:
    """导入与 __all__ 测试。"""

    def test_all(self):
        from vools.task.utils import __all__
        assert "identity" in __all__
        assert "const" in __all__
        assert "compose" in __all__
        assert "pipe" in __all__
        assert "retry" in __all__
        assert "timeout" in __all__
        assert "catch" in __all__
        assert "finally_fn" in __all__
        assert "async_retry" in __all__
        assert "async_timeout" in __all__
        assert "with_timeout" in __all__
        assert "with_retry" in __all__
        assert "with_logging" in __all__
        assert "Result" in __all__

    def test_result_export(self):
        from vools.task.utils import Result
        r = Result.success(1)
        assert r.is_success
        assert r.unwrap() == 1
