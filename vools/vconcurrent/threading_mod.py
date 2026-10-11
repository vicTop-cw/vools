"""
vools.concurrent.threading_mod - threading 高级封装

对 Python 标准库 threading 进行高级封装，提供更易用、更安全的并发编程 API。

主要组件：
    VThread      - 增强版线程（返回值获取、超时等待、优雅停止、异常捕获）
    VLock        - 增强版 RLock（上下文管理器、超时获取、可重入计数）
    VEvent       - 增强版事件（条件等待 wait_for）
    VSemaphore   - 增强版信号量（超时获取 acquire_timeout）
    VLatch       - 计数门闩（CountDownLatch，等待 N 个线程完成后释放）
    VBarrier     - 屏障（支持回调）

装饰器：
    thread_pool   - 用线程池执行被装饰函数
    run_in_thread - 将同步函数在线程中运行
    synchronized  - 类似 Java 的 synchronized，加锁执行
"""

from __future__ import annotations

import threading
import weakref
from concurrent.futures import Future, ThreadPoolExecutor
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

__all__ = [
    "VThread",
    "VLock",
    "VEvent",
    "VSemaphore",
    "VLatch",
    "VBarrier",
    "thread_pool",
    "run_in_thread",
    "synchronized",
]

# ---------------------------------------------------------------------------
# VThread - 增强版线程
# ---------------------------------------------------------------------------


class VThread(threading.Thread):
    """增强版线程类，继承 threading.Thread。

    在标准线程基础上增加：
        - 返回值获取：通过 ``get_result`` 拿到目标函数的返回值。
        - 超时等待：``get_result`` / ``join`` 支持超时。
        - 优雅停止：通过 ``stop`` 请求停止，目标函数可通过 ``is_stop_requested``
          或 ``stop_event`` 主动检查并退出。
        - 异常捕获：目标函数抛出的异常会被保存，可在 ``get_result`` 时重新抛出，
          也可通过 ``exception`` 属性查看。

    示例::

        def task(thread):
            for i in range(10):
                if thread.is_stop_requested():
                    return "stopped"
                time.sleep(0.1)
            return "done"

        t = VThread(target=task, args=(...,))  # args 中可传入 t 自身
        # 更常见的做法：用 stop_event
        evt = threading.Event()
        t = VThread(target=lambda: task_loop(evt))
        t.start()
        result = t.get_result(timeout=5)
    """

    def __init__(
        self,
        group: Any = None,
        target: Optional[Callable[..., Any]] = None,
        name: Optional[str] = None,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        daemon: Optional[bool] = None,
    ) -> None:
        # 不把 target 传给父类，由本类 run() 接管以捕获返回值与异常
        super().__init__(group=group, name=name, daemon=daemon)
        self._target_fn: Optional[Callable[..., Any]] = target
        self._args: Tuple[Any, ...] = args
        self._kwargs: Dict[str, Any] = dict(kwargs) if kwargs else {}
        self._result: Any = None
        self._exception: Optional[BaseException] = None
        self._stop_event = threading.Event()
        self._done_event = threading.Event()

    # -- 核心运行 -----------------------------------------------------------
    def run(self) -> None:
        """线程入口，捕获目标函数的返回值与异常。"""
        try:
            if self._target_fn is not None:
                self._result = self._target_fn(*self._args, **self._kwargs)
        except BaseException as exc:  # noqa: BLE001 - 捕获并保存所有异常
            self._exception = exc
        finally:
            self._done_event.set()

    # -- 返回值 / 异常 ------------------------------------------------------
    def get_result(self, timeout: Optional[float] = None) -> Any:
        """等待线程结束并返回目标函数的返回值。

        Args:
            timeout: 最长等待时间（秒），``None`` 表示一直等待。

        Returns:
            目标函数的返回值。

        Raises:
            TimeoutError: 超时未完成。
            Exception: 目标函数抛出的原始异常。
        """
        if not self._done_event.wait(timeout):
            raise TimeoutError(
                "VThread %r did not complete within %s seconds" % (self.name, timeout)
            )
        if self._exception is not None:
            raise self._exception
        return self._result

    @property
    def result(self) -> Any:
        """目标函数的返回值（未完成时为 None，不等待）。"""
        return self._result

    @property
    def exception(self) -> Optional[BaseException]:
        """目标函数抛出的异常，未抛出或未完成时为 None。"""
        return self._exception

    @property
    def has_exception(self) -> bool:
        """目标函数是否抛出了异常。"""
        return self._exception is not None

    # -- 优雅停止 -----------------------------------------------------------
    def stop(self, timeout: Optional[float] = None) -> bool:
        """请求线程优雅停止并等待其结束。

        设置停止标志后等待线程退出。目标函数需要主动检查 ``is_stop_requested``
        或 ``stop_event`` 才能真正响应停止请求。

        Args:
            timeout: 最长等待时间（秒）。

        Returns:
            线程是否已在超时前退出。
        """
        self._stop_event.set()
        self.join(timeout)
        return not self.is_alive()

    def is_stop_requested(self) -> bool:
        """是否已收到停止请求。目标函数中应周期性检查此方法。"""
        return self._stop_event.is_set()

    @property
    def stop_event(self) -> threading.Event:
        """内部停止事件，可传递给目标函数用于检查。"""
        return self._stop_event

    # -- 状态查询 -----------------------------------------------------------
    def is_done(self) -> bool:
        """线程是否已执行完毕（无论成功或异常）。"""
        return self._done_event.is_set()

    # -- 上下文管理器 -------------------------------------------------------
    def __enter__(self) -> "VThread":
        if not self.is_alive() and not self._done_event.is_set() and self._target_fn is not None:
            self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.join()
        return False

    def __repr__(self) -> str:
        state = "done" if self._done_event.is_set() else ("alive" if self.is_alive() else "pending")
        return "<VThread name=%r state=%s>" % (self.name, state)


# ---------------------------------------------------------------------------
# VLock - 增强版 RLock
# ---------------------------------------------------------------------------


class VLock:
    """增强版可重入锁（RLock）。

    支持：
        - 上下文管理器协议（``with VLock():``）。
        - 超时获取：``acquire_timeout`` / ``acquire(timeout=...)``。
        - 可重入计数：同一线程可多次获取，需同样次数释放。

    示例::

        lock = VLock()
        if lock.acquire_timeout(2.0):
            try:
                ...
            finally:
                lock.release()

        with VLock() as lock:
            ...
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._count = 0

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """获取锁。

        Args:
            blocking: 是否阻塞等待。
            timeout: 阻塞超时（秒），``-1`` 表示无限等待。仅在 ``blocking=True`` 时生效。

        Returns:
            是否成功获取。
        """
        ok = self._lock.acquire(blocking, timeout)
        if ok:
            self._count += 1
        return ok

    def acquire_timeout(self, timeout: float) -> bool:
        """尝试在指定时间内获取锁。

        Args:
            timeout: 超时时间（秒）。

        Returns:
            是否成功获取。
        """
        return self._lock.acquire(timeout=timeout)

    def release(self) -> None:
        """释放一次锁。"""
        self._lock.release()
        if self._count > 0:
            self._count -= 1

    @property
    def count(self) -> int:
        """当前持有线程的重入计数（仅持有线程视角有意义）。"""
        return self._count

    @property
    def locked(self) -> bool:
        """锁是否被持有。"""
        return self._count > 0

    def __enter__(self) -> "VLock":
        self._lock.acquire()
        self._count += 1
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self._lock.release()
        if self._count > 0:
            self._count -= 1
        return False

    def __repr__(self) -> str:
        return "<VLock count=%d>" % self._count


# ---------------------------------------------------------------------------
# VEvent - 增强版事件
# ---------------------------------------------------------------------------


class VEvent:
    """增强版事件，支持 ``wait_for(predicate, timeout)`` 条件等待。

    内部使用 Condition 实现，因此 ``wait_for`` 能够在 ``set`` / ``notify`` 时
    被正确唤醒，而非忙等待。

    示例::

        evt = VEvent()
        # 等待某个条件成立
        evt.wait_for(lambda: shared_state.ready, timeout=5)
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._flag = False

    def set(self) -> None:
        """设置事件标志并唤醒所有等待者。"""
        with self._cond:
            self._flag = True
            self._cond.notify_all()

    def clear(self) -> None:
        """清除事件标志。"""
        with self._cond:
            self._flag = False

    def is_set(self) -> bool:
        """事件标志是否被设置。"""
        with self._cond:
            return self._flag

    def wait(self, timeout: Optional[float] = None) -> bool:
        """等待事件被设置。

        Args:
            timeout: 超时（秒），``None`` 表示一直等待。

        Returns:
            事件是否已被设置（超时返回 False）。
        """
        with self._cond:
            if not self._flag:
                self._cond.wait(timeout)
            return self._flag

    def wait_for(self, predicate: Callable[[], bool], timeout: Optional[float] = None) -> bool:
        """等待谓词成立。

        重复等待直到 ``predicate`` 返回 True，或超时。每次事件被 ``set`` 或其它
        线程在关联 Condition 上 ``notify`` 时都会重新检查谓词。

        Args:
            predicate: 返回布尔值的可调用对象。
            timeout: 超时（秒），``None`` 表示一直等待。

        Returns:
            谓词是否在超时前成立。
        """
        with self._cond:
            return self._cond.wait_for(predicate, timeout)

    def notify_all(self) -> None:
        """唤醒所有等待者（即使不 set 标志，也会触发谓词重新检查）。"""
        with self._cond:
            self._cond.notify_all()

    @property
    def condition(self) -> threading.Condition:
        """内部 Condition 对象，可用于更精细的同步。"""
        return self._cond

    def __enter__(self) -> "VEvent":
        self._cond.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self._cond.release()
        return False

    def __repr__(self) -> str:
        return "<VEvent set=%s>" % self._flag


# ---------------------------------------------------------------------------
# VSemaphore - 增强版信号量
# ---------------------------------------------------------------------------


class VSemaphore:
    """增强版信号量，支持 ``acquire_timeout(timeout)``。

    示例::

        sem = VSemaphore(3)
        if sem.acquire_timeout(2.0):
            try:
                ...
            finally:
                sem.release()
    """

    def __init__(self, value: int = 1) -> None:
        if value < 0:
            raise ValueError("semaphore initial value must be >= 0")
        self._sem = threading.Semaphore(value)

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """获取信号量。

        Args:
            blocking: 是否阻塞。
            timeout: 超时（秒），仅 ``blocking=True`` 时有效。

        Returns:
            是否成功获取。
        """
        return self._sem.acquire(blocking=blocking, timeout=timeout)

    def acquire_timeout(self, timeout: float) -> bool:
        """在指定时间内尝试获取信号量。

        Args:
            timeout: 超时（秒）。

        Returns:
            是否成功获取。
        """
        return self._sem.acquire(timeout=timeout)

    def release(self, n: int = 1) -> None:
        """释放信号量。"""
        self._sem.release(n)

    def __enter__(self) -> "VSemaphore":
        self._sem.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self._sem.release()
        return False

    def __repr__(self) -> str:
        return "<VSemaphore %r>" % self._sem


# ---------------------------------------------------------------------------
# VLatch - 计数门闩 (CountDownLatch)
# ---------------------------------------------------------------------------


class VLatch:
    """计数门闩（CountDownLatch）。

    初始计数为 N，每次 ``count_down`` 将计数减一，当计数归零时所有 ``wait`` 的
    线程被释放。与 Barrier 不同，Latch 不可重置，是一次性的同步点。

    示例::

        latch = VLatch(3)

        def worker():
            try:
                ...
            finally:
                latch.count_down()

        # 主线程等待 3 个 worker 完成
        latch.wait()
    """

    def __init__(self, count: int) -> None:
        if count < 0:
            raise ValueError("latch count must be non-negative")
        self._count = count
        self._cond = threading.Condition()

    def count_down(self) -> None:
        """计数减一，归零时唤醒所有等待者。"""
        with self._cond:
            if self._count > 0:
                self._count -= 1
                if self._count == 0:
                    self._cond.notify_all()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """等待计数归零。

        Args:
            timeout: 超时（秒），``None`` 表示一直等待。

        Returns:
            计数是否已归零（超时返回 False）。
        """
        with self._cond:
            if self._count == 0:
                return True
            self._cond.wait(timeout)
            return self._count == 0

    @property
    def count(self) -> int:
        """当前剩余计数。"""
        with self._cond:
            return self._count

    def is_released(self) -> bool:
        """计数是否已归零。"""
        with self._cond:
            return self._count == 0

    def __enter__(self) -> "VLatch":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        # 退出作用域时自动 count_down，便于 with 表达"完成本任务"
        self.count_down()
        return False

    def __repr__(self) -> str:
        return "<VLatch count=%d>" % self.count


# ---------------------------------------------------------------------------
# VBarrier - 屏障
# ---------------------------------------------------------------------------


class VBarrier:
    """屏障，支持到达回调。

    包装 ``threading.Barrier``，N 个线程调用 ``wait`` 后全部被阻塞，直到第 N 个
    线程到达；此时（可选）回调被其中一个线程执行，随后所有线程被释放。

    示例::

        def on_release():
            print("all threads arrived")

        barrier = VBarrier(3, action=on_release)
        barrier.wait()  # 在每个工作线程中调用
    """

    def __init__(
        self,
        parties: int,
        action: Optional[Callable[[], Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if parties < 0:
            raise ValueError("parties must be non-negative")
        self._barrier = threading.Barrier(parties, action=action, timeout=timeout)

    def wait(self, timeout: Optional[float] = None) -> int:
        """等待到达屏障。

        Args:
            timeout: 超时（秒），覆盖默认超时。

        Returns:
            一个 0 到 parties-1 之间的整数，表示调用者到达的序号。

        Raises:
            threading.BrokenBarrierError: 屏障已损坏或等待时超时/被中断。
        """
        return self._barrier.wait(timeout)

    def reset(self) -> None:
        """重置屏障到初始状态，已等待的线程会收到 BrokenBarrierError。"""
        self._barrier.reset()

    def abort(self) -> None:
        """将屏障置为损坏状态，唤醒所有等待线程。"""
        self._barrier.abort()

    @property
    def parties(self) -> int:
        """需要的线程数。"""
        return self._barrier.parties

    @property
    def n_waiting(self) -> int:
        """当前正在等待的线程数。"""
        return self._barrier.n_waiting

    @property
    def broken(self) -> bool:
        """屏障是否已损坏。"""
        return self._barrier.broken

    def __enter__(self) -> "VBarrier":
        self.wait()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        return False

    def __repr__(self) -> str:
        return "<VBarrier parties=%d n_waiting=%d broken=%s>" % (
            self.parties,
            self.n_waiting,
            self.broken,
        )


# ---------------------------------------------------------------------------
# 装饰器
# ---------------------------------------------------------------------------


def thread_pool(max_workers: Optional[int] = None) -> Callable[[Callable], Callable]:
    """函数装饰器：用线程池执行被装饰函数。

    调用被装饰函数时会将任务提交到一个持久化的线程池，立即返回
    ``concurrent.futures.Future``。调用方可通过 ``future.result()`` 获取结果。

    Args:
        max_workers: 线程池最大工作线程数，``None`` 使用默认值。

    示例::

        @thread_pool(max_workers=4)
        def download(url):
            return requests.get(url).text

        future = download("https://example.com")
        html = future.result()
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Future]:
        executor = ThreadPoolExecutor(max_workers=max_workers)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Future:
            return executor.submit(func, *args, **kwargs)

        def shutdown(wait: bool = True) -> None:
            """关闭底层线程池。"""
            executor.shutdown(wait=wait)

        # 暴露 executor 与 shutdown 供外部管理生命周期
        wrapper.executor = executor  # type: ignore[attr-defined]
        wrapper.shutdown = shutdown  # type: ignore[attr-defined]
        return wrapper

    return decorator


def run_in_thread(
    daemon: bool = False,
    name: Optional[str] = None,
) -> Callable[[Callable], Callable]:
    """函数装饰器：将同步函数在新线程中运行。

    每次调用都会创建并启动一个 :class:`VThread`，返回该线程对象。调用方可通过
    ``thread.get_result()`` 获取返回值或异常。

    Args:
        daemon: 是否作为守护线程运行。
        name: 线程名前缀。

    示例::

        @run_in_thread(daemon=True)
        def slow_task(x):
            time.sleep(1)
            return x * 2

        t = slow_task(21)
        print(t.get_result())  # 42
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., VThread]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> VThread:
            thread_name = name if name is not None else func.__name__
            thread = VThread(
                target=func,
                name=thread_name,
                args=args,
                kwargs=kwargs,
                daemon=daemon,
            )
            thread.start()
            return thread

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# synchronized - 类似 Java 的 synchronized
# ---------------------------------------------------------------------------

_object_locks: "weakref.WeakKeyDictionary[Any, threading.RLock]" = weakref.WeakKeyDictionary()
_object_locks_guard = threading.Lock()
_global_fallback_lock = threading.RLock()


def _resolve_object_lock(obj: Any) -> threading.RLock:
    """获取或创建对象级 RLock，用于 synchronized 的 per-instance / per-class 锁。

    不可弱引用的对象（如基本类型）回退到全局锁。
    """
    try:
        with _object_locks_guard:
            lk = _object_locks.get(obj)
            if lk is None:
                lk = threading.RLock()
                _object_locks[obj] = lk
            return lk
    except TypeError:
        return _global_fallback_lock


def _is_lock_like(obj: Any) -> bool:
    """判断对象是否为锁（具有 acquire/release 上下文管理语义）。"""
    return hasattr(obj, "acquire") and hasattr(obj, "release") and hasattr(obj, "__enter__")


def synchronized(lock: Any = None) -> Any:
    """类似 Java 的 synchronized 装饰器，加锁执行被装饰函数。

    用法：

        1. 直接装饰（每个被装饰函数拥有独立锁）::

            @synchronized
            def func(): ...

        2. 带括号装饰（等价于 1）::

            @synchronized()
            def func(): ...

        3. 指定锁对象::

            my_lock = VLock()
            @synchronized(my_lock)
            def func(): ...

        4. 实例方法默认使用 per-instance 锁（类方法使用 per-class 锁）::

            class Service:
                @synchronized
                def update(self):
                    # 同一实例的 update 互斥，不同实例不互斥
                    ...

    Args:
        lock: 指定的锁对象；为 None 时自动选取（实例方法取实例锁，否则取函数级锁）。
    """

    def _build(func: Callable[..., Any], explicit_lock: Any) -> Callable[..., Any]:
        per_func_lock = threading.RLock()

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if explicit_lock is not None:
                ctx = explicit_lock
            elif args:
                ctx = _resolve_object_lock(args[0])
            else:
                ctx = per_func_lock
            with ctx:
                return func(*args, **kwargs)

        # 暴露实际使用的锁便于外部协调
        wrapper.lock = explicit_lock if explicit_lock is not None else per_func_lock  # type: ignore[attr-defined]
        return wrapper

    # 直接用作装饰器：@synchronized
    if lock is None:
        return lambda func: _build(func, None)

    if callable(lock) and not _is_lock_like(lock):
        # @synchronized 直接作用于函数
        func = lock
        return _build(func, None)

    # @synchronized() 或 @synchronized(some_lock)
    return lambda func: _build(func, lock)
