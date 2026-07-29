"""
vools.concurrent.asyncio_mod - asyncio 高级封装

对 Python 标准库 asyncio 进行高级封装，提供更易用、更安全的异步编程 API。

主要组件：
    AsyncQueue     - 异步队列（带超时）
    AsyncEvent     - 异步事件
    AsyncLock      - 异步锁（上下文管理器、超时获取）
    AsyncSemaphore - 异步信号量（上下文管理器）
    AsyncBarrier   - 异步屏障
    AsyncLatch     - 异步 CountDownLatch
    AsyncPool      - 异步任务池（限制并发数）

工具函数：
    gather         - 并发执行，支持超时、异常处理
    wait_any       - 等待任意一个任务完成
    wait_all       - 等待所有任务完成
    to_async       - 将同步函数转为异步（线程池执行）
    to_sync        - 将异步函数转为同步（运行事件循环）
    run_in_executor - 在执行器中运行同步函数
    delay          - 延迟执行协程
    timeout        - 给协程加超时
    retry_async    - 异步重试装饰器
"""

from __future__ import annotations

import asyncio
import functools
import sys
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Generator,
    Generic,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)

from vools.core.asyncio_compat import create_task, get_running_loop, run

__all__ = [
    "AsyncQueue",
    "AsyncEvent",
    "AsyncLock",
    "AsyncSemaphore",
    "AsyncBarrier",
    "AsyncLatch",
    "AsyncPool",
    "gather",
    "wait_any",
    "wait_all",
    "to_async",
    "to_sync",
    "run_in_executor",
    "delay",
    "timeout",
    "retry_async",
]

_T = TypeVar("_T")

_HAS_ASYNCIO_TIMEOUT = sys.version_info >= (3, 11)


# ---------------------------------------------------------------------------
# AsyncQueue - 异步队列
# ---------------------------------------------------------------------------


class AsyncQueue(Generic[_T]):
    """异步队列，支持带超时的 put/get 操作。

    对 ``asyncio.Queue`` 的封装，增加超时支持和更丰富的查询接口。

    示例::

        q = AsyncQueue(maxsize=10)
        await q.put(item, timeout=1.0)
        item = await q.get(timeout=1.0)
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[_T] = asyncio.Queue(maxsize=maxsize)

    async def put(self, item: _T, timeout: Optional[float] = None) -> None:
        """将元素放入队列。

        Args:
            item: 要放入的元素。
            timeout: 超时时间（秒），``None`` 表示无限等待。

        Raises:
            asyncio.TimeoutError: 超时未成功放入。
        """
        if timeout is None:
            await self._queue.put(item)
            return
        try:
            await asyncio.wait_for(self._queue.put(item), timeout)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("AsyncQueue.put timed out after %s seconds" % timeout)

    def put_nowait(self, item: _T) -> None:
        """立即放入元素，队列满时抛出 ``asyncio.QueueFull``。"""
        self._queue.put_nowait(item)

    async def get(self, timeout: Optional[float] = None) -> _T:
        """从队列获取元素。

        Args:
            timeout: 超时时间（秒），``None`` 表示无限等待。

        Returns:
            队列中的元素。

        Raises:
            asyncio.TimeoutError: 超时未获取到元素。
        """
        if timeout is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("AsyncQueue.get timed out after %s seconds" % timeout)

    def get_nowait(self) -> _T:
        """立即获取元素，队列空时抛出 ``asyncio.QueueEmpty``。"""
        return self._queue.get_nowait()

    def qsize(self) -> int:
        """返回队列当前大小。"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """队列是否为空。"""
        return self._queue.empty()

    def full(self) -> bool:
        """队列是否已满。"""
        return self._queue.full()

    async def join(self) -> None:
        """阻塞直到队列中所有任务都被标记为完成。"""
        await self._queue.join()

    def task_done(self) -> None:
        """标记一个任务已完成。"""
        self._queue.task_done()

    @property
    def maxsize(self) -> int:
        """队列最大容量。"""
        return self._queue.maxsize

    def __aiter__(self) -> "AsyncQueue[_T]":
        return self

    async def __anext__(self) -> _T:
        try:
            return await self._queue.get()
        except Exception:
            raise StopAsyncIteration

    def __repr__(self) -> str:
        return "<AsyncQueue qsize=%d maxsize=%d>" % (self.qsize(), self.maxsize)


# ---------------------------------------------------------------------------
# AsyncEvent - 异步事件
# ---------------------------------------------------------------------------


class AsyncEvent:
    """异步事件。

    对 ``asyncio.Event`` 的封装，提供与标准事件一致的接口。

    示例::

        evt = AsyncEvent()
        # 等待事件被设置
        await evt.wait()
        # 设置事件
        evt.set()
    """

    def __init__(self) -> None:
        self._event: asyncio.Event = asyncio.Event()

    def set(self) -> None:
        """设置事件标志，唤醒所有等待的协程。"""
        self._event.set()

    def clear(self) -> None:
        """清除事件标志。"""
        self._event.clear()

    def is_set(self) -> bool:
        """事件是否已设置。"""
        return self._event.is_set()

    async def wait(self, timeout: Optional[float] = None) -> bool:
        """等待事件被设置。

        Args:
            timeout: 超时时间（秒），``None`` 表示无限等待。

        Returns:
            事件是否已设置（超时返回 False）。
        """
        if timeout is None:
            await self._event.wait()
            return True
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def __repr__(self) -> str:
        return "<AsyncEvent set=%s>" % self.is_set()


# ---------------------------------------------------------------------------
# AsyncLock - 异步锁
# ---------------------------------------------------------------------------


class AsyncLock:
    """异步锁，支持上下文管理器和超时获取。

    对 ``asyncio.Lock`` 的封装，增加超时支持。

    示例::

        lock = AsyncLock()
        async with lock:
            ...

        if await lock.acquire(timeout=1.0):
            try:
                ...
            finally:
                lock.release()
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取锁。

        Args:
            timeout: 超时时间（秒），``None`` 表示无限等待。

        Returns:
            是否成功获取锁（超时返回 False）。
        """
        if timeout is None:
            await self._lock.acquire()
            return True
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def release(self) -> None:
        """释放锁。"""
        self._lock.release()

    def locked(self) -> bool:
        """锁是否被持有。"""
        return self._lock.locked()

    async def __aenter__(self) -> "AsyncLock":
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self._lock.release()
        return False

    def __repr__(self) -> str:
        return "<AsyncLock locked=%s>" % self.locked()


# ---------------------------------------------------------------------------
# AsyncSemaphore - 异步信号量
# ---------------------------------------------------------------------------


class AsyncSemaphore:
    """异步信号量，支持上下文管理器。

    对 ``asyncio.Semaphore`` 的封装。

    示例::

        sem = AsyncSemaphore(3)
        async with sem:
            ...
    """

    def __init__(self, value: int = 1) -> None:
        if value < 0:
            raise ValueError("semaphore initial value must be >= 0")
        self._sem: asyncio.Semaphore = asyncio.Semaphore(value)
        self._initial_value: int = value

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取信号量。

        Args:
            timeout: 超时时间（秒），``None`` 表示无限等待。

        Returns:
            是否成功获取（超时返回 False）。
        """
        if timeout is None:
            await self._sem.acquire()
            return True
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def release(self, n: int = 1) -> None:
        """释放信号量。

        Args:
            n: 释放的数量，默认为 1。
        """
        for _ in range(n):
            self._sem.release()

    def locked(self) -> bool:
        """信号量是否已耗尽（无法立即获取）。"""
        return self._sem.locked()

    @property
    def value(self) -> int:
        """当前可用计数。"""
        return self._sem._value  # type: ignore[attr-defined]

    async def __aenter__(self) -> "AsyncSemaphore":
        await self._sem.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self._sem.release()
        return False

    def __repr__(self) -> str:
        return "<AsyncSemaphore value=%d/%d>" % (self.value, self._initial_value)


# ---------------------------------------------------------------------------
# AsyncBarrier - 异步屏障
# ---------------------------------------------------------------------------


class AsyncBarrier:
    """异步屏障。

    N 个协程调用 ``wait`` 后全部被阻塞，直到第 N 个协程到达；
    此时（可选）回调被其中一个协程执行，随后所有协程被释放。

    示例::

        async def worker(barrier):
            # 第一阶段
            await barrier.wait()
            # 第二阶段

        barrier = AsyncBarrier(3)
        await asyncio.gather(*[worker(barrier) for _ in range(3)])
    """

    def __init__(
        self,
        parties: int,
        action: Optional[Callable[[], Any]] = None,
    ) -> None:
        if parties <= 0:
            raise ValueError("parties must be > 0")
        self._parties: int = parties
        self._action: Optional[Callable[[], Any]] = action
        self._count: int = 0
        self._event: asyncio.Event = asyncio.Event()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._broken: bool = False

    async def wait(self, timeout: Optional[float] = None) -> int:
        """等待到达屏障。

        Args:
            timeout: 超时时间（秒），``None`` 表示无限等待。

        Returns:
            一个 0 到 parties-1 之间的整数，表示到达的序号。

        Raises:
            asyncio.TimeoutError: 超时未到达。
            BrokenBarrierError: 屏障已损坏。
        """
        if self._broken:
            raise BrokenBarrierError("AsyncBarrier is broken")

        async with self._lock:
            self._count += 1
            index = self._parties - self._count
            if self._count == self._parties:
                if self._action is not None:
                    self._action()
                self._event.set()
                return index

        event = self._event
        try:
            if timeout is None:
                await event.wait()
            else:
                try:
                    await asyncio.wait_for(event.wait(), timeout)
                except asyncio.TimeoutError:
                    async with self._lock:
                        if self._count < self._parties:
                            self._broken = True
                            self._event.set()
                    raise asyncio.TimeoutError(
                        "AsyncBarrier.wait timed out after %s seconds" % timeout
                    )
        except Exception:
            if self._broken:
                raise BrokenBarrierError("AsyncBarrier is broken")
            raise

        if self._broken:
            raise BrokenBarrierError("AsyncBarrier is broken")
        return index

    def reset(self) -> None:
        """重置屏障到初始状态。"""
        self._count = 0
        self._broken = False
        self._event.clear()

    def abort(self) -> None:
        """将屏障置为损坏状态，唤醒所有等待者。"""
        self._broken = True
        self._event.set()

    @property
    def parties(self) -> int:
        """需要的协程数。"""
        return self._parties

    @property
    def n_waiting(self) -> int:
        """当前正在等待的协程数。"""
        return self._count

    @property
    def broken(self) -> bool:
        """屏障是否已损坏。"""
        return self._broken

    async def __aenter__(self) -> "AsyncBarrier":
        await self.wait()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        return False

    def __repr__(self) -> str:
        return "<AsyncBarrier parties=%d n_waiting=%d broken=%s>" % (
            self._parties,
            self._count,
            self._broken,
        )


class BrokenBarrierError(Exception):
    """屏障损坏异常。"""
    pass


# ---------------------------------------------------------------------------
# AsyncLatch - 异步 CountDownLatch
# ---------------------------------------------------------------------------


class AsyncLatch:
    """异步计数门闩（CountDownLatch）。

    初始计数为 N，每次 ``count_down`` 将计数减一，当计数归零时所有 ``wait`` 的
    协程被释放。与 Barrier 不同，Latch 不可重置，是一次性的同步点。

    示例::

        latch = AsyncLatch(3)

        async def worker():
            try:
                ...
            finally:
                latch.count_down()

        # 等待 3 个 worker 完成
        await latch.wait()
    """

    def __init__(self, count: int) -> None:
        if count < 0:
            raise ValueError("latch count must be non-negative")
        self._count: int = count
        self._event: asyncio.Event = asyncio.Event()
        if count == 0:
            self._event.set()

    def count_down(self) -> None:
        """计数减一，归零时唤醒所有等待者。"""
        if self._event.is_set():
            return
        self._count -= 1
        if self._count <= 0:
            self._count = 0
            self._event.set()

    async def wait(self, timeout: Optional[float] = None) -> bool:
        """等待计数归零。

        Args:
            timeout: 超时时间（秒），``None`` 表示无限等待。

        Returns:
            计数是否已归零（超时返回 False）。
        """
        if self._event.is_set():
            return True
        if timeout is None:
            await self._event.wait()
            return True
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    @property
    def count(self) -> int:
        """当前剩余计数。"""
        return self._count

    def is_released(self) -> bool:
        """计数是否已归零。"""
        return self._event.is_set()

    async def __aenter__(self) -> "AsyncLatch":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.count_down()
        return False

    def __repr__(self) -> str:
        return "<AsyncLatch count=%d>" % self._count


# ---------------------------------------------------------------------------
# gather - 并发执行，支持超时、异常处理
# ---------------------------------------------------------------------------


async def gather(
    *aws: Union[Awaitable[_T], Coroutine[Any, Any, _T]],
    timeout: Optional[float] = None,
    return_exceptions: bool = False,
) -> List[_T]:
    """并发执行多个协程/任务，支持超时和异常处理。

    类似 ``asyncio.gather``，但增加了超时支持。

    Args:
        *aws: 要并发执行的协程/任务。
        timeout: 总超时时间（秒），``None`` 表示无超时。
        return_exceptions: 是否将异常作为结果返回。

    Returns:
        结果列表，顺序与输入一致。

    Raises:
        asyncio.TimeoutError: 超时未完成。
        Exception: 任一任务抛出异常且 return_exceptions=False 时。
    """
    if timeout is None:
        results = await asyncio.gather(*aws, return_exceptions=return_exceptions)
        return list(results)

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*aws, return_exceptions=return_exceptions),
            timeout,
        )
        return list(results)
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(
            "gather timed out after %s seconds" % timeout
        )


# ---------------------------------------------------------------------------
# wait_any / wait_all
# ---------------------------------------------------------------------------


async def wait_any(
    *aws: Union[Awaitable[_T], Coroutine[Any, Any, _T]],
    timeout: Optional[float] = None,
) -> Tuple[Set[asyncio.Task[_T]], Set[asyncio.Task[_T]]]:
    """等待任意一个任务完成。

    Args:
        *aws: 要等待的协程/任务。
        timeout: 超时时间（秒），``None`` 表示无限等待。

    Returns:
        (done, pending) 元组，分别是已完成和未完成的任务集合。
    """
    tasks = [
        aws_i if isinstance(aws_i, asyncio.Task) else create_task(aws_i)
        for aws_i in aws
    ]
    done, pending = await asyncio.wait(
        tasks,
        timeout=timeout,
        return_when=asyncio.FIRST_COMPLETED,
    )
    return done, pending


async def wait_all(
    *aws: Union[Awaitable[_T], Coroutine[Any, Any, _T]],
    timeout: Optional[float] = None,
) -> Tuple[Set[asyncio.Task[_T]], Set[asyncio.Task[_T]]]:
    """等待所有任务完成。

    Args:
        *aws: 要等待的协程/任务。
        timeout: 超时时间（秒），``None`` 表示无限等待。

    Returns:
        (done, pending) 元组，分别是已完成和未完成的任务集合。
    """
    tasks = [
        aws_i if isinstance(aws_i, asyncio.Task) else create_task(aws_i)
        for aws_i in aws
    ]
    done, pending = await asyncio.wait(
        tasks,
        timeout=timeout,
        return_when=asyncio.ALL_COMPLETED,
    )
    return done, pending


# ---------------------------------------------------------------------------
# run_in_executor - 在执行器中运行同步函数
# ---------------------------------------------------------------------------


async def run_in_executor(
    func: Callable[..., _T],
    *args: Any,
    executor: Optional[Executor] = None,
    **kwargs: Any,
) -> _T:
    """在执行器中运行同步函数并返回结果。

    Args:
        func: 要执行的同步函数。
        *args: 位置参数。
        executor: 执行器实例，``None`` 时使用默认线程池。
        **kwargs: 关键字参数。

    Returns:
        函数执行结果。
    """
    loop = get_running_loop()
    if kwargs:
        partial_func = functools.partial(func, *args, **kwargs)
    else:
        partial_func = functools.partial(func, *args)
    return await loop.run_in_executor(executor, partial_func)


# ---------------------------------------------------------------------------
# to_async - 将同步函数转为异步
# ---------------------------------------------------------------------------


def to_async(
    func: Optional[Callable[..., _T]] = None,
    *,
    executor: Optional[Executor] = None,
) -> Any:
    """装饰器/函数：将同步函数转为异步函数（在线程池中执行）。

    用法：

    1. 直接装饰::

        @to_async
        def sync_func(x):
            return x * 2

        result = await sync_func(21)

    2. 指定执行器::

        @to_async(executor=my_executor)
        def sync_func(x):
            return x * 2

    Args:
        func: 要转换的函数。
        executor: 执行器实例，``None`` 时使用默认线程池。

    Returns:
        异步包装函数（作为装饰器时返回装饰器）。
    """

    def decorator(f: Callable[..., _T]) -> Callable[..., Coroutine[Any, Any, _T]]:
        @functools.wraps(f)
        async def wrapper(*args: Any, **kwargs: Any) -> _T:
            return await run_in_executor(f, *args, executor=executor, **kwargs)

        return wrapper

    if func is not None and callable(func):
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# to_sync - 将异步函数转为同步
# ---------------------------------------------------------------------------


def to_sync(
    func: Optional[Callable[..., Coroutine[Any, Any, _T]]] = None,
    *,
    debug: bool = False,
) -> Any:
    """装饰器/函数：将异步函数转为同步函数（运行事件循环）。

    用法：

    1. 直接装饰::

        @to_sync
        async def async_func(x):
            return x * 2

        result = async_func(21)

    2. 带参数::

        @to_sync(debug=True)
        async def async_func(x):
            return x * 2

    Args:
        func: 要转换的异步函数。
        debug: 是否启用事件循环调试模式。

    Returns:
        同步包装函数（作为装饰器时返回装饰器）。
    """

    def decorator(f: Callable[..., Coroutine[Any, Any, _T]]) -> Callable[..., _T]:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> _T:
            coro = f(*args, **kwargs)
            return run(coro, debug=debug)

        return wrapper

    if func is not None and callable(func):
        return decorator(func)
    return decorator


# ---------------------------------------------------------------------------
# AsyncPool - 异步任务池
# ---------------------------------------------------------------------------


class AsyncPool:
    """异步任务池，限制并发数。

    使用信号量限制同时运行的任务数量，提供 submit/map/gather 接口。

    示例::

        pool = AsyncPool(max_workers=4)
        async with pool:
            results = await pool.gather([coro1(), coro2(), coro3()])
    """

    def __init__(
        self,
        max_workers: int,
        *,
        return_exceptions: bool = False,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be > 0")
        self._max_workers: int = max_workers
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_workers)
        self._return_exceptions: bool = return_exceptions
        self._tasks: List[asyncio.Task[Any]] = []
        self._closed: bool = False

    async def _run_with_semaphore(self, coro: Coroutine[Any, Any, _T]) -> _T:
        async with self._semaphore:
            return await coro

    async def submit(
        self,
        coro: Coroutine[Any, Any, _T],
    ) -> asyncio.Task[_T]:
        """提交一个协程到池中执行。

        Args:
            coro: 要执行的协程。

        Returns:
            Task 对象。
        """
        if self._closed:
            raise RuntimeError("AsyncPool is closed")
        task = create_task(self._run_with_semaphore(coro))
        self._tasks.append(task)
        return task

    async def map(
        self,
        func: Callable[..., Coroutine[Any, Any, _T]],
        iterable: Any,
        *,
        timeout: Optional[float] = None,
    ) -> List[_T]:
        """并发映射，对可迭代对象的每个元素调用异步函数。

        Args:
            func: 异步函数。
            iterable: 可迭代对象。
            timeout: 总超时时间（秒）。

        Returns:
            结果列表，顺序与输入一致。
        """
        if self._closed:
            raise RuntimeError("AsyncPool is closed")
        coros = [func(item) for item in iterable]
        return await self.gather(*coros, timeout=timeout)

    async def gather(
        self,
        *coros: Coroutine[Any, Any, _T],
        timeout: Optional[float] = None,
        return_exceptions: Optional[bool] = None,
    ) -> List[_T]:
        """并发执行多个协程，受池并发数限制。

        Args:
            *coros: 要执行的协程。
            timeout: 总超时时间（秒）。
            return_exceptions: 是否将异常作为结果返回，默认使用池的设置。

        Returns:
            结果列表，顺序与输入一致。
        """
        if self._closed:
            raise RuntimeError("AsyncPool is closed")
        use_return_exceptions = (
            return_exceptions
            if return_exceptions is not None
            else self._return_exceptions
        )
        limited_coros = [self._run_with_semaphore(c) for c in coros]
        return await gather(
            *limited_coros,
            timeout=timeout,
            return_exceptions=use_return_exceptions,
        )

    def close(self) -> None:
        """关闭任务池，不再接受新任务。"""
        self._closed = True

    async def join(self) -> None:
        """等待所有已提交的任务完成。"""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @property
    def max_workers(self) -> int:
        """最大并发数。"""
        return self._max_workers

    @property
    def active_count(self) -> int:
        """当前活跃任务数（近似值）。"""
        return self._max_workers - self._semaphore._value  # type: ignore[attr-defined]

    async def __aenter__(self) -> "AsyncPool":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def __repr__(self) -> str:
        return "<AsyncPool max_workers=%d active=%d>" % (
            self._max_workers,
            self.active_count,
        )


# ---------------------------------------------------------------------------
# delay - 异步延迟执行
# ---------------------------------------------------------------------------


async def delay(
    seconds: float,
    coro: Coroutine[Any, Any, _T],
) -> _T:
    """延迟指定时间后执行协程。

    Args:
        seconds: 延迟秒数。
        coro: 要执行的协程。

    Returns:
        协程的返回值。
    """
    await asyncio.sleep(seconds)
    return await coro


# ---------------------------------------------------------------------------
# timeout - 异步超时
# ---------------------------------------------------------------------------


async def timeout(
    coro: Coroutine[Any, Any, _T],
    seconds: float,
) -> _T:
    """给协程添加超时。

    Args:
        coro: 要执行的协程。
        seconds: 超时时间（秒）。

    Returns:
        协程的返回值。

    Raises:
        asyncio.TimeoutError: 超时未完成。
    """
    try:
        return await asyncio.wait_for(coro, seconds)
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(
            "coroutine timed out after %s seconds" % seconds
        )


# ---------------------------------------------------------------------------
# retry_async - 异步重试装饰器
# ---------------------------------------------------------------------------


def retry_async(
    max_retries: int = 3,
    *,
    backoff: float = 0.0,
    backoff_factor: float = 1.0,
    exceptions: Tuple[type, ...] = (Exception,),
) -> Any:
    """异步重试装饰器。

    支持最大重试次数、退避策略（指数退避）。

    Args:
        max_retries: 最大重试次数（不含首次调用）。
        backoff: 初始退避时间（秒）。
        backoff_factor: 退避乘数，每次重试后 backoff *= backoff_factor。
        exceptions: 需要重试的异常类型元组。

    示例::

        @retry_async(max_retries=3, backoff=0.5, backoff_factor=2.0)
        async def fetch(url):
            return await http_get(url)
    """
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    if backoff < 0:
        raise ValueError("backoff must be >= 0")
    if backoff_factor < 1.0:
        raise ValueError("backoff_factor must be >= 1.0")

    def decorator(
        func: Callable[..., Coroutine[Any, Any, _T]]
    ) -> Callable[..., Coroutine[Any, Any, _T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> _T:
            current_backoff = backoff
            last_exception: Optional[BaseException] = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        if current_backoff > 0:
                            await asyncio.sleep(current_backoff)
                            current_backoff *= backoff_factor
                    else:
                        raise

            # 理论上不会走到这里
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("retry_async: unexpected state")

        return wrapper

    return decorator
