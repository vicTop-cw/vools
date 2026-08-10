"""
asyncio 兼容层 — 统一处理 Python 不同版本的 asyncio 接口

在高版本 Python 使用标准库 asyncio 的原生接口，
在低版本（<3.7）提供手动实现的兼容版本。

提供与标准库一致的接口：
- get_running_loop()           → 获取当前运行的事件循环
- run(coro, *, debug=False)     → 运行协程并返回结果
- create_task(coro, *, name=None) → 创建任务
"""

__all__ = ['get_running_loop', 'run', 'create_task']

import asyncio
import sys

# ================================================================
# 检测运行环境
# ================================================================

_HAS_GET_RUNNING_LOOP = sys.version_info >= (3, 7)
_HAS_ASYNCIO_RUN = sys.version_info >= (3, 7)
_HAS_CREATE_TASK = sys.version_info >= (3, 7)

if _HAS_GET_RUNNING_LOOP and _HAS_ASYNCIO_RUN and _HAS_CREATE_TASK:
    # ── 标准库 asyncio（3.7+） ──
    get_running_loop = asyncio.get_running_loop
    run = asyncio.run
    create_task = asyncio.create_task

else:
    # ── Python 3.6 兼容实现 ──

    def get_running_loop():
        """
        获取当前运行的事件循环。

        Python 3.7+ 有 asyncio.get_running_loop()，
        Python 3.6 使用 asyncio._get_running_loop() 作为替代。

        Returns:
            当前运行的事件循环。

        Raises:
            RuntimeError: 如果没有正在运行的事件循环。
        """
        loop = asyncio._get_running_loop()
        if loop is None:
            raise RuntimeError('no running event loop')
        return loop

    def run(coro, *, debug=False):
        """
        运行一个协程并返回结果。

        Python 3.7+ 有 asyncio.run()，
        Python 3.6 手动实现。

        Args:
            coro: 要运行的协程。
            debug: 是否启用调试模式。

        Returns:
            协程的返回值。
        """
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.set_debug(debug)
            return loop.run_until_complete(coro)
        finally:
            try:
                _cancel_all_tasks(loop)
                if hasattr(loop, 'shutdown_asyncgens'):
                    loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    def create_task(coro, *, name=None):
        """
        创建一个任务。

        Python 3.7+ 有 asyncio.create_task()，
        Python 3.6 使用 asyncio.ensure_future() 作为替代。

        Args:
            coro: 协程对象。
            name: 任务名称（3.6 忽略）。

        Returns:
            Task 对象。
        """
        return asyncio.ensure_future(coro)

    def _cancel_all_tasks(loop):
        """取消所有任务（Python 3.6 兼容）"""
        if hasattr(asyncio, 'all_tasks'):
            to_cancel = asyncio.all_tasks(loop)
        else:
            to_cancel = asyncio.Task.all_tasks(loop)

        if not to_cancel:
            return

        for task in to_cancel:
            task.cancel()

        loop.run_until_complete(
            asyncio.gather(*to_cancel, loop=loop, return_exceptions=True)
        )

        for task in to_cancel:
            if task.cancelled():
                continue
            if task.exception() is not None:
                loop.call_exception_handler({
                    'message': 'unhandled exception during asyncio.run() shutdown',
                    'exception': task.exception(),
                    'task': task,
                })
