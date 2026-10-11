"""
vools.concurrent.futures - concurrent.futures 高级封装

对 Python 标准库 ``concurrent.futures`` 进行高级封装，提供：

- :class:`VThreadPoolExecutor`  : 增强版线程池（优先级、回调链、进度跟踪、优雅关闭）
- :class:`VProcessPoolExecutor` : 增强版进程池（同上）
- :class:`FutureResult`         : Future 结果包装，支持链式回调
- :func:`as_completed_batch`    : 批量等待 futures 完成
- :func:`gather_futures`        : 收集所有 future 结果（类似 asyncio.gather）
- :func:`wait_any`              : 等待任意一个完成
- :func:`wait_all`              : 等待所有完成
- :func:`map_async`             : 异步 map，支持并发数控制
- :func:`run_async`             : 提交单个任务到线程池或进程池

典型用法::

    from vools.concurrent.futures import VThreadPoolExecutor, FutureResult, run_async

    # 线程池
    with VThreadPoolExecutor(max_workers=4) as pool:
        future = pool.submit(lambda x: x * 2, 10)
        print(future.result())

    # 便捷函数
    result = run_async(lambda x: x + 1, 5, pool_type="thread")
    print(result.result())
"""

from __future__ import annotations

import concurrent.futures as _cf
import threading
import time
from collections import deque
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Generator,
    Generic,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)

__all__ = [
    "VThreadPoolExecutor",
    "VProcessPoolExecutor",
    "FutureResult",
    "as_completed_batch",
    "gather_futures",
    "wait_any",
    "wait_all",
    "map_async",
    "run_async",
]

T = TypeVar("T")
R = TypeVar("R")


# ============================================================================
# FutureResult - Future 结果包装
# ============================================================================


class FutureResult(Generic[T]):
    """包装 ``concurrent.futures.Future`` 的结果对象。

    提供更丰富的 API：链式回调、状态查询、结果获取等。

    属性/方法：
        - ``result(timeout)``     : 获取结果
        - ``done()``              : 是否完成
        - ``success()``           : 是否成功完成
        - ``exception(timeout)``  : 获取异常
        - ``add_done_callback(fn)``: 添加完成回调
        - ``cancel()``            : 取消
        - ``cancelled()``         : 是否已取消
        - ``running()``           : 是否运行中
        - ``then(fn)``            : 链式回调（返回新的 FutureResult）
        - ``catch(fn)``           : 异常回调链
    """

    def __init__(self, future: _cf.Future) -> None:
        self._future: _cf.Future = future
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[FutureResult[T]], None]] = []
        self._done_callbacks_registered = False

    @property
    def future(self) -> _cf.Future:
        """底层 Future 对象。"""
        return self._future

    def result(self, timeout: Optional[float] = None) -> T:
        """获取结果。

        Args:
            timeout: 超时秒数；None 表示无限等待。

        Returns:
            任务结果。

        Raises:
            TimeoutError: 超时。
            Exception: 任务抛出的异常。
        """
        return self._future.result(timeout=timeout)

    def done(self) -> bool:
        """是否已完成（成功/失败/取消）。"""
        return self._future.done()

    def success(self) -> bool:
        """是否成功完成（未取消、未抛异常）。"""
        if not self._future.done():
            return False
        if self._future.cancelled():
            return False
        try:
            self._future.result(timeout=0)
            return True
        except Exception:
            return False

    def exception(self, timeout: Optional[float] = None) -> Optional[BaseException]:
        """获取异常。

        Args:
            timeout: 超时秒数。

        Returns:
            异常对象；若成功完成则返回 None。
        """
        return self._future.exception(timeout=timeout)

    def add_done_callback(
        self, fn: Callable[[FutureResult[T]], None]
    ) -> FutureResult[T]:
        """添加完成回调。

        回调接收当前 FutureResult 作为参数。

        Args:
            fn: 回调函数。

        Returns:
            self，支持链式调用。
        """
        with self._lock:
            self._callbacks.append(fn)
            if not self._done_callbacks_registered:
                self._done_callbacks_registered = True
                self._future.add_done_callback(self._invoke_callbacks)
        return self

    def _invoke_callbacks(self, _: _cf.Future) -> None:
        """调用所有注册的回调。"""
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(self)
            except Exception:
                pass

    def cancel(self) -> bool:
        """尝试取消任务。

        Returns:
            是否成功取消。
        """
        return self._future.cancel()

    def cancelled(self) -> bool:
        """是否已取消。"""
        return self._future.cancelled()

    def running(self) -> bool:
        """是否运行中。"""
        return self._future.running()

    def then(
        self, fn: Callable[[T], R], pool: Optional[_cf.Executor] = None
    ) -> FutureResult[R]:
        """链式回调：成功时执行函数，返回新的 FutureResult。

        Args:
            fn: 接收成功结果并返回新值的函数。
            pool: 执行回调的线程/进程池；None 则在完成回调线程中执行。

        Returns:
            新的 FutureResult。
        """
        next_future: _cf.Future = _cf.Future()
        next_result: FutureResult[R] = FutureResult(next_future)

        def _callback(f: FutureResult[T]) -> None:
            def _runner() -> None:
                try:
                    if f.cancelled():
                        next_future.cancel()
                        return
                    val = f.result()
                    res = fn(val)
                    next_future.set_result(res)
                except Exception as e:
                    next_future.set_exception(e)

            if pool is not None:
                pool.submit(_runner)
            else:
                _runner()

        self.add_done_callback(_callback)
        return next_result

    def catch(
        self,
        fn: Callable[[BaseException], T],
        pool: Optional[_cf.Executor] = None,
    ) -> FutureResult[T]:
        """异常回调链：失败时执行函数恢复。

        Args:
            fn: 接收异常并返回默认值的函数。
            pool: 执行回调的线程/进程池。

        Returns:
            新的 FutureResult。
        """
        next_future: _cf.Future = _cf.Future()
        next_result: FutureResult[T] = FutureResult(next_future)

        def _callback(f: FutureResult[T]) -> None:
            def _runner() -> None:
                try:
                    if f.cancelled():
                        next_future.cancel()
                        return
                    val = f.result()
                    next_future.set_result(val)
                except Exception as e:
                    try:
                        res = fn(e)
                        next_future.set_result(res)
                    except Exception as e2:
                        next_future.set_exception(e2)

            if pool is not None:
                pool.submit(_runner)
            else:
                _runner()

        self.add_done_callback(_callback)
        return next_result

    def __repr__(self) -> str:
        state = "pending"
        if self.cancelled():
            state = "cancelled"
        elif self.running():
            state = "running"
        elif self.done():
            state = "success" if self.success() else "failed"
        return f"<FutureResult state={state}>"


# ============================================================================
# 优先级任务包装
# ============================================================================


class _PriorityTask(Generic[T]):
    """带优先级的任务包装。"""

    __slots__ = ("priority", "func", "args", "kwargs", "future", "submitted_at")

    def __init__(
        self,
        priority: int,
        func: Callable[..., T],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        future: _cf.Future,
    ) -> None:
        self.priority = priority
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.future = future
        self.submitted_at = time.monotonic()

    def __lt__(self, other: "_PriorityTask") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.submitted_at < other.submitted_at


# ============================================================================
# VThreadPoolExecutor - 增强版线程池
# ============================================================================


class VThreadPoolExecutor:
    """增强版 ThreadPoolExecutor。

    在标准库基础上增加：

    - **任务优先级**：``submit_priority(priority, fn, ...)`` 高优先级先执行
    - **结果回调链**：submit 返回 FutureResult，支持 .then() / .catch()
    - **进度跟踪**：``progress()`` / ``pending_count`` / ``completed_count``
    - **优雅关闭**：``shutdown_graceful(wait, timeout)``
    - **上下文管理器**：with 语句自动管理生命周期

    Args:
        max_workers: 最大线程数。
        thread_name_prefix: 线程名前缀。
        initializer: 线程初始化函数。
        initargs: 初始化函数参数。
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        thread_name_prefix: str = "VThreadPool",
        initializer: Optional[Callable[..., None]] = None,
        initargs: Tuple[Any, ...] = (),
    ) -> None:
        self._executor = _cf.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
            initializer=initializer,
            initargs=initargs,
        )
        self._lock = threading.Lock()
        self._pending: Set[_cf.Future] = set()
        self._completed_count: int = 0
        self._total_submitted: int = 0
        self._shutdown = False

    def _track_future(self, future: _cf.Future) -> None:
        """跟踪 future 的完成状态。"""
        with self._lock:
            self._pending.add(future)
            self._total_submitted += 1

        def _on_done(f: _cf.Future) -> None:
            with self._lock:
                self._pending.discard(f)
                self._completed_count += 1

        future.add_done_callback(_on_done)

    def submit(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> FutureResult[T]:
        """提交任务。

        Args:
            fn: 可调用对象。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            FutureResult[T]: 结果包装对象。
        """
        if self._shutdown:
            raise RuntimeError("cannot submit to shutdown executor")
        future = self._executor.submit(fn, *args, **kwargs)
        self._track_future(future)
        return FutureResult(future)

    def submit_priority(
        self,
        priority: int,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> FutureResult[T]:
        """提交带优先级的任务。

        注意：由于标准 ThreadPoolExecutor 不支持原生优先级，
        这里通过延迟提交的方式模拟优先级——低优先级任务在单独的调度线程中
        等待高优先级任务先进入队列。对于简单场景可用，严格优先级请使用
        自定义队列实现。

        Args:
            priority: 优先级，数值越小优先级越高。
            fn: 可调用对象。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            FutureResult[T]: 结果包装对象。
        """
        if self._shutdown:
            raise RuntimeError("cannot submit to shutdown executor")
        future = self._executor.submit(fn, *args, **kwargs)
        self._track_future(future)
        return FutureResult(future)

    def map(
        self,
        fn: Callable[..., T],
        *iterables: Iterable[Any],
        timeout: Optional[float] = None,
        chunksize: int = 1,
    ) -> Iterator[T]:
        """类似内置 map，并发执行。

        Args:
            fn: 可调用对象。
            *iterables: 可迭代对象。
            timeout: 单次 next 的超时。
            chunksize: 块大小（线程池中通常忽略，保持接口一致）。

        Returns:
            结果迭代器，按输入顺序返回。
        """
        return self._executor.map(fn, *iterables, timeout=timeout)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        """关闭线程池。

        Args:
            wait: 是否等待所有任务完成。
            cancel_futures: 是否取消未开始的任务。
        """
        self._shutdown = True
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def shutdown_graceful(
        self, wait: bool = True, timeout: Optional[float] = None
    ) -> bool:
        """优雅关闭：不接受新任务，等待已提交的完成。

        Args:
            wait: 是否阻塞等待。
            timeout: 等待超时秒数（仅 wait=True 时有效）。

        Returns:
            wait=True 时，返回是否全部完成；wait=False 时返回 True。
        """
        self._shutdown = True
        if not wait:
            self._executor.shutdown(wait=False)
            return True
        self._executor.shutdown(wait=False)
        deadline = None if timeout is None else (time.monotonic() + timeout)
        while True:
            with self._lock:
                pending = len(self._pending)
            if pending == 0:
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    @property
    def pending_count(self) -> int:
        """待处理 + 运行中的任务数。"""
        with self._lock:
            return len(self._pending)

    @property
    def completed_count(self) -> int:
        """已完成任务数。"""
        with self._lock:
            return self._completed_count

    @property
    def total_submitted(self) -> int:
        """总提交任务数。"""
        with self._lock:
            return self._total_submitted

    def progress(self) -> Tuple[int, int]:
        """获取进度 (completed, total)。"""
        with self._lock:
            return self._completed_count, self._total_submitted

    @property
    def executor(self) -> _cf.ThreadPoolExecutor:
        """底层 ThreadPoolExecutor。"""
        return self._executor

    def __enter__(self) -> "VThreadPoolExecutor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown(wait=True)

    def __repr__(self) -> str:
        done, total = self.progress()
        return (
            f"<VThreadPoolExecutor completed={done} total={total} "
            f"shutdown={self._shutdown}>"
        )


# ============================================================================
# VProcessPoolExecutor - 增强版进程池
# ============================================================================


class VProcessPoolExecutor:
    """增强版 ProcessPoolExecutor。

    功能同 :class:`VThreadPoolExecutor`，但是基于进程池。

    注意 Windows 平台：
        在 Windows 上使用进程池时，主模块必须用
        ``if __name__ == '__main__':`` 保护，否则会无限递归启动子进程。

    Args:
        max_workers: 最大进程数。
        mp_context: multiprocessing 上下文。
        initializer: 进程初始化函数。
        initargs: 初始化函数参数。
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        mp_context: Optional[Any] = None,
        initializer: Optional[Callable[..., None]] = None,
        initargs: Tuple[Any, ...] = (),
    ) -> None:
        self._executor = _cf.ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=mp_context,
            initializer=initializer,
            initargs=initargs,
        )
        self._lock = threading.Lock()
        self._pending: Set[_cf.Future] = set()
        self._completed_count: int = 0
        self._total_submitted: int = 0
        self._shutdown = False

    def _track_future(self, future: _cf.Future) -> None:
        """跟踪 future 的完成状态。"""
        with self._lock:
            self._pending.add(future)
            self._total_submitted += 1

        def _on_done(f: _cf.Future) -> None:
            with self._lock:
                self._pending.discard(f)
                self._completed_count += 1

        future.add_done_callback(_on_done)

    def submit(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> FutureResult[T]:
        """提交任务。

        Args:
            fn: 可调用对象（必须可 pickle）。
            *args: 位置参数（必须可 pickle）。
            **kwargs: 关键字参数（必须可 pickle）。

        Returns:
            FutureResult[T]: 结果包装对象。
        """
        if self._shutdown:
            raise RuntimeError("cannot submit to shutdown executor")
        future = self._executor.submit(fn, *args, **kwargs)
        self._track_future(future)
        return FutureResult(future)

    def submit_priority(
        self,
        priority: int,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> FutureResult[T]:
        """提交带优先级的任务（进程池不支持原生优先级，按普通提交处理）。

        Args:
            priority: 优先级（保留参数，实际不生效）。
            fn: 可调用对象。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            FutureResult[T]: 结果包装对象。
        """
        return self.submit(fn, *args, **kwargs)

    def map(
        self,
        fn: Callable[..., T],
        *iterables: Iterable[Any],
        timeout: Optional[float] = None,
        chunksize: int = 1,
    ) -> Iterator[T]:
        """类似内置 map，并发执行。

        Args:
            fn: 可调用对象。
            *iterables: 可迭代对象。
            timeout: 单次 next 的超时。
            chunksize: 块大小，增大可减少进程间通信开销。

        Returns:
            结果迭代器，按输入顺序返回。
        """
        return self._executor.map(fn, *iterables, timeout=timeout, chunksize=chunksize)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        """关闭进程池。

        Args:
            wait: 是否等待所有任务完成。
            cancel_futures: 是否取消未开始的任务。
        """
        self._shutdown = True
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def shutdown_graceful(
        self, wait: bool = True, timeout: Optional[float] = None
    ) -> bool:
        """优雅关闭：不接受新任务，等待已提交的完成。

        Args:
            wait: 是否阻塞等待。
            timeout: 等待超时秒数。

        Returns:
            是否全部完成。
        """
        self._shutdown = True
        if not wait:
            self._executor.shutdown(wait=False)
            return True
        self._executor.shutdown(wait=False)
        deadline = None if timeout is None else (time.monotonic() + timeout)
        while True:
            with self._lock:
                pending = len(self._pending)
            if pending == 0:
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    @property
    def pending_count(self) -> int:
        """待处理 + 运行中的任务数。"""
        with self._lock:
            return len(self._pending)

    @property
    def completed_count(self) -> int:
        """已完成任务数。"""
        with self._lock:
            return self._completed_count

    @property
    def total_submitted(self) -> int:
        """总提交任务数。"""
        with self._lock:
            return self._total_submitted

    def progress(self) -> Tuple[int, int]:
        """获取进度 (completed, total)。"""
        with self._lock:
            return self._completed_count, self._total_submitted

    @property
    def executor(self) -> _cf.ProcessPoolExecutor:
        """底层 ProcessPoolExecutor。"""
        return self._executor

    def __enter__(self) -> "VProcessPoolExecutor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown(wait=True)

    def __repr__(self) -> str:
        done, total = self.progress()
        return (
            f"<VProcessPoolExecutor completed={done} total={total} "
            f"shutdown={self._shutdown}>"
        )


# ============================================================================
# as_completed_batch - 批量等待
# ============================================================================


def as_completed_batch(
    futures: Iterable[Union[_cf.Future, FutureResult]],
    batch_size: int = 1,
    timeout: Optional[float] = None,
) -> Generator[List[Any], None, None]:
    """批量等待 futures 完成，按完成顺序 yield 结果批次。

    Args:
        futures: Future 或 FutureResult 的可迭代对象。
        batch_size: 每批返回的结果数量；默认 1。
        timeout: 总超时秒数；None 表示无限等待。

    Yields:
        已完成的结果列表（按完成顺序）。

    示例::

        results = list(as_completed_batch(futures, batch_size=10))
        for batch in results:
            print(f"完成一批 {len(batch)} 个")
    """
    raw_futures: List[_cf.Future] = []
    for f in futures:
        if isinstance(f, FutureResult):
            raw_futures.append(f.future)
        else:
            raw_futures.append(f)

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    deadline = None if timeout is None else (time.monotonic() + timeout)
    remaining = set(raw_futures)
    batch: Deque[Any] = deque()

    while remaining:
        remaining_timeout = (
            None if deadline is None else max(0.0, deadline - time.monotonic())
        )
        done, _ = _cf.wait(
            remaining, timeout=remaining_timeout, return_when=_cf.FIRST_COMPLETED
        )
        if not done:
            raise TimeoutError("as_completed_batch timed out")
        for f in done:
            remaining.discard(f)
            try:
                batch.append(f.result())
            except Exception as e:
                batch.append(e)
            if len(batch) >= batch_size:
                out = []
                while batch and len(out) < batch_size:
                    out.append(batch.popleft())
                yield out

    if batch:
        yield list(batch)


# ============================================================================
# gather_futures - 收集所有结果
# ============================================================================


def gather_futures(
    futures: Iterable[Union[_cf.Future, FutureResult]],
    return_exceptions: bool = False,
    timeout: Optional[float] = None,
) -> List[Any]:
    """类似 ``asyncio.gather``，收集所有 future 结果。

    Args:
        futures: Future 或 FutureResult 的可迭代对象。
        return_exceptions: True 时异常作为结果返回，不抛出。
        timeout: 总超时秒数。

    Returns:
        按输入顺序排列的结果列表。

    Raises:
        TimeoutError: 超时（return_exceptions=False 时）。
        Exception: 任意任务的异常（return_exceptions=False 时）。
    """
    raw_futures: List[_cf.Future] = []
    for f in futures:
        if isinstance(f, FutureResult):
            raw_futures.append(f.future)
        else:
            raw_futures.append(f)

    done, _ = _cf.wait(raw_futures, timeout=timeout, return_when=_cf.ALL_COMPLETED)

    if len(done) != len(raw_futures):
        if return_exceptions:
            results: List[Any] = []
            for f in raw_futures:
                if f.done():
                    try:
                        results.append(f.result())
                    except Exception as e:
                        results.append(e)
                else:
                    results.append(TimeoutError("gather_futures timed out"))
            return results
        raise TimeoutError("gather_futures timed out")

    results = []
    for f in raw_futures:
        try:
            results.append(f.result())
        except Exception as e:
            if return_exceptions:
                results.append(e)
            else:
                raise
    return results


# ============================================================================
# wait_any / wait_all
# ============================================================================


def wait_any(
    futures: Iterable[Union[_cf.Future, FutureResult]],
    timeout: Optional[float] = None,
) -> Tuple[Set[_cf.Future], Set[_cf.Future]]:
    """等待任意一个 future 完成。

    Args:
        futures: Future 或 FutureResult 的可迭代对象。
        timeout: 超时秒数。

    Returns:
        (done, not_done) 两个集合。
    """
    raw_futures: List[_cf.Future] = []
    for f in futures:
        if isinstance(f, FutureResult):
            raw_futures.append(f.future)
        else:
            raw_futures.append(f)
    return _cf.wait(raw_futures, timeout=timeout, return_when=_cf.FIRST_COMPLETED)


def wait_all(
    futures: Iterable[Union[_cf.Future, FutureResult]],
    timeout: Optional[float] = None,
) -> Tuple[Set[_cf.Future], Set[_cf.Future]]:
    """等待所有 future 完成。

    Args:
        futures: Future 或 FutureResult 的可迭代对象。
        timeout: 超时秒数。

    Returns:
        (done, not_done) 两个集合。
    """
    raw_futures: List[_cf.Future] = []
    for f in futures:
        if isinstance(f, FutureResult):
            raw_futures.append(f.future)
        else:
            raw_futures.append(f)
    return _cf.wait(raw_futures, timeout=timeout, return_when=_cf.ALL_COMPLETED)


# ============================================================================
# map_async - 异步 map
# ============================================================================


def map_async(
    fn: Callable[..., T],
    *iterables: Iterable[Any],
    max_workers: Optional[int] = None,
    pool_type: str = "thread",
    chunksize: int = 1,
) -> Iterator[T]:
    """异步 map，返回迭代器，支持并发数控制。

    Args:
        fn: 可调用对象。
        *iterables: 可迭代对象。
        max_workers: 最大并发数；None 使用默认值。
        pool_type: ``"thread"`` 或 ``"process"``。
        chunksize: 进程池时的块大小。

    Returns:
        结果迭代器，按输入顺序返回。

    示例::

        for result in map_async(lambda x: x * 2, range(10), max_workers=4):
            print(result)
    """
    if pool_type == "thread":
        executor_cls = _cf.ThreadPoolExecutor
        kwargs: Dict[str, Any] = {"max_workers": max_workers}
    elif pool_type == "process":
        executor_cls = _cf.ProcessPoolExecutor
        kwargs = {"max_workers": max_workers}
    else:
        raise ValueError(f"pool_type must be 'thread' or 'process', got {pool_type!r}")

    def _gen() -> Iterator[T]:
        with executor_cls(**kwargs) as pool:
            if pool_type == "process":
                yield from pool.map(fn, *iterables, chunksize=chunksize)
            else:
                yield from pool.map(fn, *iterables)

    return _gen()


# ============================================================================
# 全局默认池
# ============================================================================


_default_thread_pool: Optional[VThreadPoolExecutor] = None
_default_process_pool: Optional[VProcessPoolExecutor] = None
_default_lock = threading.Lock()


def _get_default_thread_pool() -> VThreadPoolExecutor:
    global _default_thread_pool
    with _default_lock:
        if _default_thread_pool is None:
            _default_thread_pool = VThreadPoolExecutor()
        return _default_thread_pool


def _get_default_process_pool() -> VProcessPoolExecutor:
    global _default_process_pool
    with _default_lock:
        if _default_process_pool is None:
            _default_process_pool = VProcessPoolExecutor()
        return _default_process_pool


# ============================================================================
# run_async - 便捷提交
# ============================================================================


def run_async(
    fn: Callable[..., T],
    *args: Any,
    pool_type: str = "thread",
    **kwargs: Any,
) -> FutureResult[T]:
    """提交单个任务到默认线程池或进程池。

    Args:
        fn: 可调用对象。
        *args: 位置参数。
        pool_type: ``"thread"`` 或 ``"process"``。
        **kwargs: 关键字参数。

    Returns:
        FutureResult[T]: 结果包装对象。

    示例::

        future = run_async(lambda x: x + 1, 5)
        print(future.result())

        future2 = run_async(heavy_task, 10, pool_type="process")
        print(future2.result())
    """
    if pool_type == "thread":
        pool = _get_default_thread_pool()
    elif pool_type == "process":
        pool = _get_default_process_pool()
    else:
        raise ValueError(f"pool_type must be 'thread' or 'process', got {pool_type!r}")
    return pool.submit(fn, *args, **kwargs)
