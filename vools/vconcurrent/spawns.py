"""
vools.concurrent.spawns - 进程派生工具

基于 ``multiprocessing`` 提供进程派生与生命周期管理：

- :class:`SpawnManager`  : 管理多个派生进程的生命周期（注册/启动/停止/监控）
- :func:`spawn`          : 派生一个新进程执行函数，返回 :class:`SpawnHandle`
- :func:`spawn_many`     : 批量派生多个进程执行同一函数不同参数
- :class:`SpawnHandle`   : 进程句柄，支持 ``is_alive() / join() / terminate() / pid / exitcode``
- :func:`restart_on_exit`: 装饰器/上下文管理器，进程退出时自动重启
- :func:`watchdog`       : 看门狗，监控进程存活，超时无心跳则重启

典型用法::

    from vools.concurrent.spawns import spawn, SpawnManager, watchdog

    def worker(n):
        import time
        for i in range(n):
            print(i)
            time.sleep(0.1)

    handle = spawn(worker, args=(5,))
    handle.join()
    print("exit:", handle.exitcode)

    # 批量
    handles = spawn_many(worker, [(3,), (5,), (7,)])
    for h in handles:
        h.join()

    # 管理器
    mgr = SpawnManager()
    h = mgr.register("job1", worker, args=(10,))
    mgr.start_all()
    mgr.stop_all()
"""

from __future__ import annotations

import multiprocessing as _mp
import threading
import time
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

__all__ = [
    "SpawnHandle",
    "SpawnManager",
    "spawn",
    "spawn_many",
    "restart_on_exit",
    "watchdog",
]


# Python 3.6 兼容：Process.is_alive 在所有版本都有
def _get_default_context() -> Any:
    """获取默认 multiprocessing 上下文。

    Windows / macOS 默认 spawn，Linux 默认 fork。
    """
    try:
        return _mp.get_context()
    except Exception:  # pragma: no cover
        return _mp


# ============================================================================
# SpawnHandle
# ============================================================================


class SpawnHandle:
    """派生进程句柄。

    封装 ``multiprocessing.Process``，提供统一的查询/控制接口。

    属性：
        - ``pid``       : 进程 PID（未启动为 None）
        - ``exitcode``  : 退出码（运行中为 None）
        - ``name``      : 进程名

    方法：
        - ``is_alive()``   : 进程是否存活
        - ``join(timeout)``: 等待进程结束
        - ``terminate()``  : 终止进程
        - ``kill()``       : 强制杀死
        - ``join_then(callback)`` : 结束后回调（异步线程）
    """

    def __init__(
        self,
        target: Callable[..., Any],
        args: Sequence[Any] = (),
        kwargs: Optional[Mapping[str, Any]] = None,
        name: Optional[str] = None,
        daemon: bool = False,
        ctx: Optional[Any] = None,
    ) -> None:
        self._target: Callable[..., Any] = target
        self._args: Tuple[Any, ...] = tuple(args)
        self._kwargs: Dict[str, Any] = dict(kwargs or {})
        self._name: str = name or f"SpawnHandle-{id(self)}"
        self._daemon: bool = daemon
        self._ctx: Any = ctx or _get_default_context()
        self._proc: Optional["_mp.Process"] = None
        self._started: bool = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> "SpawnHandle":
        """启动进程。重复调用安全（已启动直接返回）。"""
        with self._lock:
            if self._started:
                return self
            proc = self._ctx.Process(
                target=self._target,
                args=self._args,
                kwargs=self._kwargs,
                name=self._name,
                daemon=self._daemon,
            )
            proc.start()
            self._proc = proc
            self._started = True
            return self

    def terminate(self) -> None:
        """发送 SIGTERM / Windows TerminateProcess。"""
        if self._proc is not None and self.is_alive():
            try:
                self._proc.terminate()
            except Exception:
                pass

    def kill(self) -> None:
        """强制杀死进程（SIGKILL，Windows 等同 terminate）。"""
        if self._proc is None:
            return
        if hasattr(self._proc, "kill"):
            try:
                self._proc.kill()
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
        else:  # pragma: no cover - 老版本 fallback
            self._proc.terminate()

    def join(self, timeout: Optional[float] = None) -> None:
        """等待进程结束。"""
        if self._proc is not None:
            self._proc.join(timeout=timeout)

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def is_alive(self) -> bool:
        """进程是否存活。"""
        if self._proc is None:
            return False
        return self._proc.is_alive()

    @property
    def pid(self) -> Optional[int]:
        """进程 PID。"""
        if self._proc is None:
            return None
        return self._proc.pid

    @property
    def exitcode(self) -> Optional[int]:
        """退出码；运行中为 None。"""
        if self._proc is None:
            return None
        return self._proc.exitcode

    @property
    def name(self) -> str:
        """进程名。"""
        return self._name

    @property
    def process(self) -> Optional["_mp.Process"]:
        """底层 ``Process`` 对象。"""
        return self._proc

    @property
    def is_started(self) -> bool:
        """是否已启动过。"""
        return self._started

    # ------------------------------------------------------------------
    # 异步回调
    # ------------------------------------------------------------------
    def join_then(
        self, callback: Callable[["SpawnHandle"], None], timeout: Optional[float] = None
    ) -> threading.Thread:
        """等待结束后回调（在独立线程中执行）。

        返回该监听线程（daemon）。
        """
        def _runner() -> None:
            self.join(timeout=timeout)
            try:
                callback(self)
            except Exception:
                pass

        t = threading.Thread(target=_runner, daemon=True, name=f"{self._name}-join")
        t.start()
        return t

    # ------------------------------------------------------------------
    # 上下文
    # ------------------------------------------------------------------
    def __enter__(self) -> "SpawnHandle":
        if not self._started:
            self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.is_alive():
            self.terminate()
            try:
                self.join(timeout=5)
            except Exception:
                pass
            if self.is_alive():
                self.kill()

    def __repr__(self) -> str:
        return (
            f"<SpawnHandle name={self._name!r} pid={self.pid} "
            f"alive={self.is_alive()} exitcode={self.exitcode}>"
        )


# ============================================================================
# 函数式 API
# ============================================================================


def spawn(
    func: Callable[..., Any],
    args: Sequence[Any] = (),
    kwargs: Optional[Mapping[str, Any]] = None,
    name: Optional[str] = None,
    daemon: bool = False,
    autostart: bool = True,
) -> SpawnHandle:
    """派生一个新进程执行函数，返回 :class:`SpawnHandle`。

    Args:
        func: 要在子进程中执行的可调用对象（必须可 pickle）。
        args: 位置参数。
        kwargs: 关键字参数。
        name: 进程名。
        daemon: 是否作为守护进程。
        autostart: 是否立即启动（默认 True）。

    Returns:
        SpawnHandle: 进程句柄。

    示例::

        h = spawn(worker, args=(10,))
        h.join()
    """
    handle = SpawnHandle(func, args=args, kwargs=kwargs, name=name, daemon=daemon)
    if autostart:
        handle.start()
    return handle


def spawn_many(
    func: Callable[..., Any],
    args_list: Sequence[Sequence[Any]],
    kwargs_list: Optional[Sequence[Mapping[str, Any]]] = None,
    name_prefix: Optional[str] = None,
    daemon: bool = False,
    autostart: bool = True,
) -> List[SpawnHandle]:
    """批量派生多个进程执行同一函数不同参数。

    Args:
        func: 要执行的可调用对象。
        args_list: 每个进程的位置参数组成的列表。
        kwargs_list: 每个进程的关键字参数列表（与 ``args_list`` 等长）；``None`` 表示全部空。
        name_prefix: 进程名前缀，自动加索引。
        daemon: 是否作为守护进程。
        autostart: 是否立即启动。

    Returns:
        List[SpawnHandle]: 句柄列表。

    示例::

        handles = spawn_many(worker, [(1,), (2,), (3,)])
        for h in handles:
            h.join()
    """
    if kwargs_list is not None and len(kwargs_list) != len(args_list):
        raise ValueError("kwargs_list length must match args_list length")

    handles: List[SpawnHandle] = []
    for i, args in enumerate(args_list):
        kw = kwargs_list[i] if kwargs_list is not None else None
        name = f"{name_prefix}-{i}" if name_prefix else None
        h = SpawnHandle(func, args=args, kwargs=kw, name=name, daemon=daemon)
        handles.append(h)
    if autostart:
        for h in handles:
            h.start()
    return handles


# ============================================================================
# restart_on_exit
# ============================================================================


class _RestartController:
    """``restart_on_exit`` 的实现核心。

    可作为装饰器使用，也可作为上下文管理器使用：

        # 装饰器
        @restart_on_exit(max_restarts=3, delay=1.0)
        def worker():
            ...

        handle = worker()  # 返回 SpawnHandle

        # 上下文
        with restart_on_exit(worker, args=(5,), max_restarts=3) as handle:
            ...
    """

    def __init__(
        self,
        func: Optional[Callable[..., Any]] = None,
        args: Sequence[Any] = (),
        kwargs: Optional[Mapping[str, Any]] = None,
        max_restarts: int = 3,
        delay: float = 1.0,
        backoff: float = 1.0,
        name: Optional[str] = None,
        daemon: bool = False,
    ) -> None:
        self._func: Optional[Callable[..., Any]] = func
        self._args: Tuple[Any, ...] = tuple(args)
        self._kwargs: Dict[str, Any] = dict(kwargs or {})
        self._max_restarts: int = max_restarts
        self._delay: float = delay
        self._backoff: float = backoff
        self._name: Optional[str] = name
        self._daemon: bool = daemon

        self._handle: Optional[SpawnHandle] = None
        self._watch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._restart_count: int = 0

    # ------------------------------------------------------------------
    # 装饰器协议
    # ------------------------------------------------------------------
    def __call__(self, *args: Any, **kwargs: Any) -> SpawnHandle:
        """当作为装饰器使用时，``__call__`` 触发实际启动。

        装饰后调用 ``func(*args, **kwargs)`` 返回 :class:`SpawnHandle`。
        """
        if self._func is None:
            raise RuntimeError("restart_on_exit: func not provided")
        merged_args = args if args else self._args
        merged_kwargs = {**self._kwargs, **kwargs}
        return self._start_watch(
            self._func, merged_args, merged_kwargs, self._name
        )

    # ------------------------------------------------------------------
    # 上下文管理
    # ------------------------------------------------------------------
    def __enter__(self) -> SpawnHandle:
        if self._func is None:
            raise RuntimeError("restart_on_exit: func not provided for context use")
        self._handle = self._start_watch(
            self._func, self._args, self._kwargs, self._name
        )
        return self._handle

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------
    def stop(self) -> None:
        """停止监控并终止当前进程。"""
        self._stop_event.set()
        if self._handle is not None and self._handle.is_alive():
            self._handle.terminate()
            try:
                self._handle.join(timeout=5)
            except Exception:
                pass
            if self._handle.is_alive():
                self._handle.kill()
        if self._watch_thread is not None and self._watch_thread.is_alive():
            self._watch_thread.join(timeout=2)

    @property
    def handle(self) -> Optional[SpawnHandle]:
        """当前句柄。"""
        return self._handle

    @property
    def restart_count(self) -> int:
        """已重启次数。"""
        return self._restart_count

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _start_watch(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        name: Optional[str],
    ) -> SpawnHandle:
        handle = spawn(func, args=args, kwargs=kwargs, name=name, daemon=self._daemon)
        self._handle = handle

        def _watch() -> None:
            nonlocal handle
            delay = self._delay
            while not self._stop_event.is_set():
                handle.join()
                if self._stop_event.is_set():
                    return
                # 正常退出（exitcode == 0）不重启
                if handle.exitcode == 0:
                    return
                if self._restart_count >= self._max_restarts:
                    return
                self._restart_count += 1
                # 退避
                if self._stop_event.wait(timeout=delay):
                    return
                # 重新启动
                new_handle = spawn(
                    func,
                    args=args,
                    kwargs=kwargs,
                    name=name,
                    daemon=self._daemon,
                )
                # 把新的 handle 暴露出去
                self._handle = new_handle
                handle = new_handle
                delay = delay * self._backoff if self._backoff > 0 else delay

        self._watch_thread = threading.Thread(
            target=_watch, daemon=True, name=f"{name or 'restart'}-watch"
        )
        self._watch_thread.start()
        return handle


def restart_on_exit(
    func: Optional[Callable[..., Any]] = None,
    args: Sequence[Any] = (),
    kwargs: Optional[Mapping[str, Any]] = None,
    max_restarts: int = 3,
    delay: float = 1.0,
    backoff: float = 1.0,
    name: Optional[str] = None,
    daemon: bool = False,
) -> Union[_RestartController, Callable[[Callable[..., Any]], _RestartController]]:
    """进程退出时自动重启（装饰器 / 上下文管理器 / 直接调用）。

    Args:
        func: 要执行的函数；为 ``None`` 时作为装饰器工厂使用。
        args: 位置参数。
        kwargs: 关键字参数。
        max_restarts: 最大重启次数。
        delay: 重启前延迟秒数。
        backoff: 每次重启的退避倍率（>1 表示指数退避）。
        name: 进程名前缀。
        daemon: 是否守护进程。

    Returns:
        当 ``func`` 为 ``None`` 时返回装饰器；否则返回 :class:`_RestartController` 实例。

    用法一：装饰器::

        @restart_on_exit(max_restarts=5, delay=0.5)
        def worker(n):
            ...

        handle = worker(10)  # 启动并监控

    用法二：上下文::

        with restart_on_exit(worker, args=(10,), max_restarts=5) as h:
            time.sleep(60)

    用法三：直接调用::

        ctrl = restart_on_exit(worker, args=(10,))
        handle = ctrl()
        ...
        ctrl.stop()
    """
    controller = _RestartController(
        func=func,
        args=args,
        kwargs=kwargs,
        max_restarts=max_restarts,
        delay=delay,
        backoff=backoff,
        name=name,
        daemon=daemon,
    )
    if func is None:
        # 用作装饰器工厂
        def decorator(fn: Callable[..., Any]) -> _RestartController:
            controller._func = fn
            return controller

        return decorator
    return controller


# ============================================================================
# watchdog
# ============================================================================


class _Watchdog:
    """看门狗：监控进程存活，超时无心跳则重启。

    通过 :func:`watchdog` 工厂函数创建。
    """

    def __init__(
        self,
        handle: SpawnHandle,
        timeout: float,
        on_dead: Optional[Callable[[SpawnHandle], None]] = None,
        restart: bool = False,
        max_restarts: int = 3,
    ) -> None:
        self._handle: SpawnHandle = handle
        self._timeout: float = float(timeout)
        self._on_dead: Optional[Callable[[SpawnHandle], None]] = on_dead
        self._restart: bool = restart
        self._max_restarts: int = max_restarts

        self._last_heartbeat: float = time.monotonic()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._restart_count: int = 0

    # ------------------------------------------------------------------
    # 心跳
    # ------------------------------------------------------------------
    def heartbeat(self) -> None:
        """子进程心跳：更新最近活跃时间。"""
        with self._lock:
            self._last_heartbeat = time.monotonic()

    @property
    def last_heartbeat(self) -> float:
        """最近一次心跳的 monotonic 时间。"""
        with self._lock:
            return self._last_heartbeat

    @property
    def restart_count(self) -> int:
        """已重启次数。"""
        return self._restart_count

    # ------------------------------------------------------------------
    # 启停
    # ------------------------------------------------------------------
    def start(self) -> "_Watchdog":
        """启动看门狗监控线程。"""
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        t = threading.Thread(target=self._run, daemon=True, name="watchdog")
        t.start()
        self._thread = t
        return self

    def stop(self) -> None:
        """停止看门狗。"""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)

    # ------------------------------------------------------------------
    # 上下文
    # ------------------------------------------------------------------
    def __enter__(self) -> "_Watchdog":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _run(self) -> None:
        interval = max(self._timeout / 4, 0.1)
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=interval):
                return
            now = time.monotonic()
            with self._lock:
                last = self._last_heartbeat
            # 进程已退出，不处理（restart_on_exit 负责）
            if not self._handle.is_alive():
                continue
            # 心跳超时
            if now - last > self._timeout:
                self._on_timeout()

    def _on_timeout(self) -> None:
        """超时处理：触发回调，可选重启。"""
        if self._on_dead is not None:
            try:
                self._on_dead(self._handle)
            except Exception:
                pass
        if self._restart and self._restart_count < self._max_restarts:
            try:
                self._handle.kill()
                self._handle.join(timeout=2)
            except Exception:
                pass
            self._restart_count += 1
            # 重新拉起一个新进程（使用同一目标函数）
            proc = self._handle.process
            if proc is not None:
                # 通过 SpawnHandle 重新启动：构造新的句柄
                new_handle = SpawnHandle(
                    target=self._handle._target,
                    args=self._handle._args,
                    kwargs=self._handle._kwargs,
                    name=self._handle.name,
                    daemon=self._handle._daemon,
                )
                new_handle.start()
                # 替换句柄引用
                self._handle = new_handle
                with self._lock:
                    self._last_heartbeat = time.monotonic()


def watchdog(
    handle: SpawnHandle,
    timeout: float,
    on_dead: Optional[Callable[[SpawnHandle], None]] = None,
    restart: bool = False,
    max_restarts: int = 3,
    autostart: bool = True,
) -> _Watchdog:
    """为 :class:`SpawnHandle` 启动一个看门狗。

    进程在 ``timeout`` 秒内未调用 :meth:`_Watchdog.heartbeat` 则判定为"死亡"，
    触发 ``on_dead(handle)`` 回调；若 ``restart=True`` 则自动重启进程。

    Args:
        handle: 被监控的 SpawnHandle。
        timeout: 心跳超时秒数。
        on_dead: 进程死亡时的回调。
        restart: 是否自动重启。
        max_restarts: 最大重启次数。
        autostart: 是否立即启动看门狗线程。

    Returns:
        _Watchdog: 看门狗控制器。

    示例::

        h = spawn(worker, args=(60,))
        wd = watchdog(h, timeout=10.0)
        # 在 worker 内部定期调用 wd.heartbeat()
        ...
        wd.stop()
    """
    wd = _Watchdog(
        handle=handle,
        timeout=timeout,
        on_dead=on_dead,
        restart=restart,
        max_restarts=max_restarts,
    )
    if autostart:
        wd.start()
    return wd


# ============================================================================
# SpawnManager
# ============================================================================


class SpawnManager:
    """派生进程管理器。

    集中管理多个 :class:`SpawnHandle`，支持：

    - ``register(name, func, args, kwargs)`` : 注册一个任务
    - ``start(name)`` / ``start_all()``      : 启动指定/全部任务
    - ``stop(name)`` / ``stop_all()``        : 停止指定/全部任务
    - ``restart(name)``                      : 重启指定任务
    - ``status()``                           : 获取所有任务状态
    - ``monitor(timeout)``                   : 阻塞等待全部结束

    示例::

        mgr = SpawnManager()
        mgr.register("job1", worker, args=(10,))
        mgr.register("job2", worker, args=(20,))
        mgr.start_all()
        mgr.monitor()  # 等待全部结束
        for name, st in mgr.status().items():
            print(name, st)
    """

    def __init__(self, default_daemon: bool = False) -> None:
        self._handles: Dict[str, SpawnHandle] = {}
        self._specs: Dict[str, Dict[str, Any]] = {}
        self._default_daemon: bool = default_daemon
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------
    def register(
        self,
        name: str,
        func: Callable[..., Any],
        args: Sequence[Any] = (),
        kwargs: Optional[Mapping[str, Any]] = None,
        daemon: Optional[bool] = None,
        autostart: bool = False,
    ) -> SpawnHandle:
        """注册一个任务。

        Args:
            name: 任务名（唯一）。
            func: 可调用对象。
            args: 位置参数。
            kwargs: 关键字参数。
            daemon: 是否守护进程；``None`` 使用管理器默认。
            autostart: 是否立即启动。

        Returns:
            SpawnHandle: 任务句柄。
        """
        with self._lock:
            if name in self._handles:
                raise ValueError(f"Task '{name}' already registered")
            is_daemon = self._default_daemon if daemon is None else daemon
            handle = SpawnHandle(
                func, args=args, kwargs=kwargs, name=name, daemon=is_daemon
            )
            self._handles[name] = handle
            self._specs[name] = {
                "func": func,
                "args": tuple(args),
                "kwargs": dict(kwargs or {}),
                "daemon": is_daemon,
            }
            if autostart:
                handle.start()
            return handle

    def unregister(self, name: str) -> Optional[SpawnHandle]:
        """移除一个任务（必须已停止）。"""
        with self._lock:
            handle = self._handles.get(name)
            if handle is None:
                return None
            if handle.is_alive():
                raise RuntimeError(f"Task '{name}' is still alive, stop it first")
            self._handles.pop(name, None)
            self._specs.pop(name, None)
            return handle

    # ------------------------------------------------------------------
    # 启停
    # ------------------------------------------------------------------
    def start(self, name: str) -> SpawnHandle:
        """启动指定任务。若已启动且存活则直接返回。"""
        with self._lock:
            handle = self._handles.get(name)
            if handle is None:
                raise KeyError(f"Task '{name}' not found")
            if not handle.is_started:
                handle.start()
            elif not handle.is_alive():
                # 已结束，重新创建并启动
                spec = self._specs[name]
                new_h = SpawnHandle(
                    spec["func"],
                    args=spec["args"],
                    kwargs=spec["kwargs"],
                    name=name,
                    daemon=spec["daemon"],
                )
                new_h.start()
                self._handles[name] = new_h
                return new_h
            return handle

    def start_all(self) -> None:
        """启动全部已注册任务。"""
        with self._lock:
            for name in list(self._handles.keys()):
                self.start(name)

    def stop(self, name: str, timeout: float = 5.0) -> None:
        """停止指定任务。"""
        with self._lock:
            handle = self._handles.get(name)
            if handle is None:
                return
        if handle.is_alive():
            handle.terminate()
            try:
                handle.join(timeout=timeout)
            except Exception:
                pass
            if handle.is_alive():
                handle.kill()

    def stop_all(self, timeout: float = 5.0) -> None:
        """停止全部任务。"""
        with self._lock:
            names = list(self._handles.keys())
        for name in names:
            self.stop(name, timeout=timeout)

    def restart(self, name: str) -> SpawnHandle:
        """重启指定任务（先停止，再启动）。"""
        with self._lock:
            if name not in self._handles:
                raise KeyError(f"Task '{name}' not found")
        self.stop(name)
        # 重新创建并启动
        with self._lock:
            spec = self._specs[name]
            new_h = SpawnHandle(
                spec["func"],
                args=spec["args"],
                kwargs=spec["kwargs"],
                name=name,
                daemon=spec["daemon"],
            )
            new_h.start()
            self._handles[name] = new_h
            return new_h

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get(self, name: str) -> Optional[SpawnHandle]:
        """获取任务句柄。"""
        with self._lock:
            return self._handles.get(name)

    def names(self) -> List[str]:
        """所有任务名。"""
        with self._lock:
            return list(self._handles.keys())

    def is_alive(self, name: str) -> bool:
        """指定任务是否存活。"""
        with self._lock:
            handle = self._handles.get(name)
            return handle.is_alive() if handle is not None else False

    def status(self) -> Dict[str, Dict[str, Any]]:
        """所有任务状态。

        每项格式::

            {"pid": int|None, "alive": bool, "exitcode": int|None, "started": bool}
        """
        with self._lock:
            out: Dict[str, Dict[str, Any]] = {}
            for name, handle in self._handles.items():
                out[name] = {
                    "pid": handle.pid,
                    "alive": handle.is_alive(),
                    "exitcode": handle.exitcode,
                    "started": handle.is_started,
                }
            return out

    # ------------------------------------------------------------------
    # 阻塞等待
    # ------------------------------------------------------------------
    def monitor(self, timeout: Optional[float] = None) -> bool:
        """阻塞等待全部任务结束。

        Args:
            timeout: 总超时秒数；``None`` 表示无限等待。

        Returns:
            bool: 全部已结束时为 True，超时则为 False。
        """
        deadline = None if timeout is None else (time.monotonic() + timeout)
        while True:
            with self._lock:
                handles = list(self._handles.values())
            if not handles:
                return True
            all_dead = True
            for h in handles:
                if h.is_alive():
                    all_dead = False
                    break
            if all_dead:
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    # ------------------------------------------------------------------
    # 上下文
    # ------------------------------------------------------------------
    def __enter__(self) -> "SpawnManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop_all()

    def __len__(self) -> int:
        with self._lock:
            return len(self._handles)

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._handles

    def __repr__(self) -> str:
        with self._lock:
            n = len(self._handles)
            alive = sum(1 for h in self._handles.values() if h.is_alive())
        return f"<SpawnManager tasks={n} alive={alive}>"
