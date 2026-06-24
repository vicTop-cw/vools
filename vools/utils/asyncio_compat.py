"""
asyncio 兼容性模块

为 Python 3.6 提供 asyncio.get_running_loop() 和 asyncio.run() 的兼容实现。
"""

import asyncio
import sys


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
    if hasattr(asyncio, 'get_running_loop'):
        return asyncio.get_running_loop()
    # Python 3.6 兼容
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
    if hasattr(asyncio, 'run'):
        return asyncio.run(coro, debug=debug)

    # Python 3.6 兼容实现
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
