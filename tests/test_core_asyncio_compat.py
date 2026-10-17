# -*- coding: utf-8 -*-
"""测试 vools.core.asyncio_compat。"""

import asyncio
import pytest

from vools.core import asyncio_compat

__all__ = ["TestGetRunningLoop", "TestRun", "TestCreateTask", "TestImport",
           "TestVersionFlags"]


class TestGetRunningLoop:
    """get_running_loop 测试。"""

    def test_in_loop(self):
        async def _inner():
            loop = asyncio_compat.get_running_loop()
            return loop is asyncio.get_running_loop()
        assert asyncio_compat.run(_inner()) is True

    def test_not_in_loop(self):
        with pytest.raises(RuntimeError):
            asyncio_compat.get_running_loop()


class TestRun:
    """run 测试。"""

    def test_simple(self):
        async def f():
            return 42
        assert asyncio_compat.run(f()) == 42

    def test_debug(self):
        async def f():
            return 1
        assert asyncio_compat.run(f(), debug=True) == 1

    def test_exception(self):
        async def f():
            raise ValueError("boom")
        with pytest.raises(ValueError):
            asyncio_compat.run(f())


class TestCreateTask:
    """create_task 测试。"""

    def test_create_task(self):
        async def main():
            async def f():
                return "done"
            task = asyncio_compat.create_task(f())
            return await task
        assert asyncio_compat.run(main()) == "done"


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        assert "get_running_loop" in asyncio_compat.__all__
        assert "run" in asyncio_compat.__all__
        assert "create_task" in asyncio_compat.__all__


class TestVersionFlags:
    """版本标志测试。"""

    def test_flags(self):
        assert asyncio_compat._HAS_GET_RUNNING_LOOP is True
        assert asyncio_compat._HAS_ASYNCIO_RUN is True
        assert asyncio_compat._HAS_CREATE_TASK is True
