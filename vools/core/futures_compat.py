"""
futures 兼容层 — 统一处理 Python 不同版本的 concurrent.futures 差异

在高版本 Python（3.7+）直接透传标准库 ThreadPoolExecutor / ProcessPoolExecutor，
在低版本（3.6）做参数降级与行为模拟：

- ThreadPoolExecutor 的 ``initializer``/``initargs`` 是 3.7+ 参数：
  * 未提供 initializer 时直接省略该参数；
  * 提供了 initializer 时用「每线程一次性初始化」包装（threading.local 守卫）
    模拟标准库语义。
- ProcessPoolExecutor 的 ``mp_context``/``initializer``/``initargs`` 是 3.7+ 参数：
  * 未提供时直接省略；
  * 提供了 initializer 时无法跨进程模拟，抛出明确的 NotImplementedError。

提供与标准库语义一致的工厂接口：
- make_thread_executor(max_workers, thread_name_prefix, initializer, initargs)
- make_process_executor(max_workers, mp_context, initializer, initargs)
"""

__all__ = [
    'make_thread_executor',
    'make_process_executor',
    'shutdown_executor',
    'HAS_EXECUTOR_INITIALIZER',
    'HAS_SHUTDOWN_CANCEL_FUTURES',
]

import sys
import threading
from concurrent import futures as _cf

# ================================================================
# 检测运行环境
# ================================================================

# ThreadPoolExecutor/ProcessPoolExecutor 的 initializer/initargs 是 3.7+ 参数
HAS_EXECUTOR_INITIALIZER = sys.version_info >= (3, 7)
# Executor.shutdown(cancel_futures=...) 是 3.9+ 参数
HAS_SHUTDOWN_CANCEL_FUTURES = sys.version_info >= (3, 9)


def _cancel_pending_best_effort(executor):
    """py<3.9 模拟 cancel_futures=True：尽力取消尚未开始执行的任务。

    标准库 3.9+ 的 shutdown(cancel_futures=True) 会清空工作队列并取消其中的
    future。3.6~3.8 没有该参数，这里用「尽力而为」策略：尝试访问内部工作队列
    并逐个 cancel。内部结构随版本变化，因此全程 try/except 保护——取不到就
    退化为「不取消」，绝不因为模拟失败而抛错。
    """
    queues = []
    for attr in ('_work_queue', '_call_queue'):
        q = getattr(executor, attr, None)
        if q is not None:
            queues.append(q)
    for q in queues:
        try:
            while True:
                item = q.get_nowait()
                future = getattr(item, 'future', None)
                if future is not None:
                    future.cancel()
        except Exception:
            # 队列空了（Empty）或内部结构不符预期：停止尝试即可
            break


def shutdown_executor(executor, wait=True, cancel_futures=False):
    """跨版本关闭 Executor。

    Args:
        executor: ThreadPoolExecutor / ProcessPoolExecutor 实例
        wait: 是否等待已提交任务完成
        cancel_futures: 是否取消尚未开始的任务（3.9+ 原生；3.6~3.8 尽力模拟）
    """
    if HAS_SHUTDOWN_CANCEL_FUTURES:
        executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        return
    if cancel_futures:
        _cancel_pending_best_effort(executor)
    executor.shutdown(wait=wait)


if HAS_EXECUTOR_INITIALIZER:
    # ── 标准库 3.7+：直接透传 ──

    def make_thread_executor(max_workers=None, thread_name_prefix=None,
                             initializer=None, initargs=()):
        """创建 ThreadPoolExecutor（3.7+ 原生支持 initializer）"""
        return _cf.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
            initializer=initializer,
            initargs=initargs,
        )

    def make_process_executor(max_workers=None, mp_context=None,
                              initializer=None, initargs=()):
        """创建 ProcessPoolExecutor（3.7+ 原生支持 mp_context/initializer）"""
        return _cf.ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=mp_context,
            initializer=initializer,
            initargs=initargs,
        )

else:
    # ── Python 3.6 兼容实现 ──

    class _EmulatedInitThreadPool(_cf.ThreadPoolExecutor):
        """py3.6 线程池：用 threading.local 守卫模拟 initializer 每线程跑一次。"""

        def __init__(self, max_workers=None, thread_name_prefix=None,
                     initializer=None, initargs=()):
            super().__init__(
                max_workers=max_workers,
                thread_name_prefix=thread_name_prefix,
            )
            self._init_fn = initializer
            self._init_args = initargs
            self._init_local = threading.local()

        def _ensure_init(self):
            if not getattr(self._init_local, 'done', False):
                self._init_local.done = True
                if self._init_fn is not None:
                    self._init_fn(*self._init_args)

        def submit(self, fn, *args, **kwargs):
            if self._init_fn is None:
                return super().submit(fn, *args, **kwargs)

            def _wrapped(*a, **k):
                self._ensure_init()
                return fn(*a, **k)

            return super().submit(_wrapped, *args, **kwargs)

    def make_thread_executor(max_workers=None, thread_name_prefix=None,
                             initializer=None, initargs=()):
        """创建 ThreadPoolExecutor（py3.6：initializer 走模拟实现）"""
        if initializer is None:
            return _cf.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=thread_name_prefix,
            )
        return _EmulatedInitThreadPool(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
            initializer=initializer,
            initargs=initargs,
        )

    def make_process_executor(max_workers=None, mp_context=None,
                              initializer=None, initargs=()):
        """创建 ProcessPoolExecutor（py3.6：省略 3.7+ 参数）"""
        if initializer is not None:
            raise NotImplementedError(
                "ProcessPoolExecutor(initializer=...) 需要 Python 3.7+；"
                "py3.6 无法跨进程模拟 initializer"
            )
        if mp_context is not None:
            raise NotImplementedError(
                "ProcessPoolExecutor(mp_context=...) 需要 Python 3.7+"
            )
        return _cf.ProcessPoolExecutor(max_workers=max_workers)