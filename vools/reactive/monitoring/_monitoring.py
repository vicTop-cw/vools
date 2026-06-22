"""
vools-reactive MonitorSubject & MonitorObserver - 监控模块的抽象基类

所有 *Subject / *Observer 都继承这两个基类，消除重复代码、统一 API。

使用：
    class ClipSubject(MonitorSubject[ClipData, ClipboardDispatcher]):
        ...

    class ClipObserver(MonitorObserver[ClipData, ClipChangeType]):
        ...

生命周期事件：
    MonitorSubject 内部维护一个 _life_subject，在 start/stop 时发射 True/False。
    下游可通过 subject.lifecycle.subscribe(...) 或 MonitorObserver 的 on_start/on_stop 订阅。
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from typing import (
    Any,
    Callable,
    Generic,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
)

from ..core.observable import DefaultObserver, Observable, Observer, Subscription
from ..core.subject import Subject
__all__ = ['log', 'T', 'E', 'D', 'MonitorSubject', 'MonitorObserver', 'SimpleMonitorSubject']

log = logging.getLogger("vools.reactive.monitoring")

# ── 类型变量 ───────────────────────────────────────────────
T = TypeVar("T")          # 事件数据（KeyData/MouseData/ClipData/FileData/FolderData）
E = TypeVar("E")          # 事件类型枚举（KeyEventType/MouseEventType/ClipChangeType/...）
D = TypeVar("D")          # Dispatcher 类型


# ═══════════════════════════════════════════════════════════
#   MonitorSubject - 带生命周期 & Dispatcher 的 Subject 基类
# ═══════════════════════════════════════════════════════════


class MonitorSubject(Subject[T], Generic[T, D], ABC):
    """
    带生命周期监控能力的 Subject 抽象基类。

    子类需要实现：
        _create_dispatcher() -> D
        _connect_dispatcher() -> None

    提供：
        start() / stop()        # 生命周期控制
        __enter__/__exit__      # 上下文管理器
        lifecycle               # Observable[bool]，True=start, False=stop
        dispatcher / backend_name / dispatch_count / is_running  # 通用属性
    """

    __slots__ = ("_dispatcher", "_life_subject", "_has_started_once", "_kwargs_cache")

    def __init__(self) -> None:
        super().__init__()
        self._dispatcher: Optional[D] = None
        self._life_subject: Subject[bool] = Subject()
        self._has_started_once: bool = False

    # ── 子类必须实现 ────────────────────────────────────────

    @abstractmethod
    def _create_dispatcher(self) -> D:
        """创建具体 Dispatcher 实例。"""

    @abstractmethod
    def _connect_dispatcher(self) -> None:
        """把 Dispatcher.subject 连接到 self（事件转发到 MonitorSubject）。"""

    # ── 生命周期 ────────────────────────────────────────────

    def start(self) -> "MonitorSubject[T, D]":
        if self._dispatcher is None:
            self._dispatcher = self._create_dispatcher()
            self._connect_dispatcher()

        if not self._dispatcher.is_running:
            self._dispatcher.start()
            self._life_subject.on_next(True)
        self._has_started_once = True
        return self

    def stop(self) -> "MonitorSubject[T, D]":
        if self._dispatcher is not None and self._dispatcher.is_running:
            self._dispatcher.stop()
            self._life_subject.on_next(False)
        return self

    @property
    def is_running(self) -> bool:
        return self._dispatcher is not None and self._dispatcher.is_running

    # ── 上下文管理器 ────────────────────────────────────────

    def __enter__(self) -> "MonitorSubject[T, D]":
        self.start()
        return self

    def __exit__(self, exc_type: Any = None, exc_val: Any = None, exc_tb: Any = None) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    # ── 生命周期流 ──────────────────────────────────────────

    @property
    def lifecycle(self) -> Observable[bool]:
        """订阅 start/stop 事件的 Observable。

        >>> subject.lifecycle.subscribe(
        ...     on_next=lambda started: print("started" if started else "stopped")
        ... )
        """
        return self._life_subject.as_observable()

    # ── 通用属性代理（子类可覆盖补充） ────────────────────────

    @property
    def dispatcher(self) -> D:
        if self._dispatcher is None:
            raise RuntimeError("Dispatcher 尚未创建，请先调用 start() 或构造时初始化")
        return self._dispatcher

    @property
    def backend_name(self) -> str:
        if self._dispatcher is None:
            return ""
        return getattr(self._dispatcher, "backend_name", "")

    @property
    def dispatch_count(self) -> int:
        if self._dispatcher is None:
            return 0
        return getattr(self._dispatcher, "dispatch_count", 0)

    @property
    def self_filtered_count(self) -> int:
        if self._dispatcher is None:
            return 0
        return getattr(self._dispatcher, "self_filtered_count", 0)


# ═══════════════════════════════════════════════════════════
#   MonitorObserver - 按事件类型路由的观察者基类
# ═══════════════════════════════════════════════════════════


class MonitorObserver(Observer[T], Generic[T, E]):
    """
    按事件类型路由的观察者抽象基类，实现标准 Observer 接口。

    标准 Observer 接口：
        on_next(value)        # 直接传入 subscribe(observer=obs) 也能工作
        on_error(error)
        on_completed()

    子类需要实现：
        _event_type_of(value: T) -> E          # 从事件中提取枚举类型
        _handler_for(event_type: E) -> Callable[[T], Any] | None   # 根据类型取回调

    参数：
        on_any              # 所有事件统一回调（在类型路由之前触发）
        on_error            # 错误回调
        on_completed        # 完成回调
        on_start / on_stop  # 当 attach MonitorSubject 时触发的生命周期回调
        log_errors          # 是否记录回调异常（默认 True）
    """

    __slots__ = (
        "_on_any",
        "_on_error",
        "_on_completed",
        "_on_start",
        "_on_stop",
        "_subscription",
        "_life_subscription",
        "_log_errors",
        "_last_value",
    )

    def __init__(
        self,
        *,
        on_any: Optional[Callable[[T], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
        on_start: Optional[Callable[[], Any]] = None,
        on_stop: Optional[Callable[[], Any]] = None,
        log_errors: bool = True,
    ) -> None:
        self._on_any = on_any
        self._on_error = on_error
        self._on_completed = on_completed
        self._on_start = on_start
        self._on_stop = on_stop
        self._log_errors = log_errors
        self._subscription: Optional[Subscription] = None
        self._life_subscription: Optional[Subscription] = None
        self._last_value: Optional[T] = None

    # ── Observer 接口 ────────────────────────────────────────

    def on_next(self, value: T) -> None:
        self._last_value = value

        if self._on_any is not None:
            try:
                self._on_any(value)
            except Exception as e:
                if self._log_errors:
                    log.debug("MonitorObserver.on_any 异常: %s", e)

        et = self._event_type_of(value)
        handler = self._handler_for(et)
        if handler is not None:
            try:
                handler(value)
            except Exception as e:
                if self._log_errors:
                    log.debug("MonitorObserver 事件(%s)处理异常: %s", et, e)

    def on_error(self, err: Exception) -> None:
        if self._on_error is not None:
            try:
                self._on_error(err)
            except Exception as e:
                if self._log_errors:
                    log.debug("MonitorObserver.on_error 回调异常: %s", e)

    def on_completed(self) -> None:
        if self._on_completed is not None:
            try:
                self._on_completed()
            except Exception as e:
                if self._log_errors:
                    log.debug("MonitorObserver.on_completed 回调异常: %s", e)

    # ── 子类实现：事件类型提取 + 类型到回调映射 ─────────────

    @abstractmethod
    def _event_type_of(self, value: T) -> E:
        """从事件数据中提取事件类型枚举。"""

    @abstractmethod
    def _handler_for(self, event_type: E) -> Optional[Callable[[T], Any]]:
        """根据事件类型返回对应的回调函数。"""

    # ── 订阅管理 ────────────────────────────────────────────

    def subscribe(self, source: Any) -> Subscription:
        """订阅 Observable/Subject/MonitorSubject。"""
        self.unsubscribe()

        self._subscription = source.subscribe(
            on_next=self.on_next,
            on_error=self.on_error,
            on_completed=self.on_completed,
        )

        # 如果 source 是 MonitorSubject 或提供 lifecycle 流，订阅其启停事件
        if (self._on_start is not None or self._on_stop is not None):
            lifecycle = getattr(source, "lifecycle", None)
            if lifecycle is not None:
                self._life_subscription = lifecycle.subscribe(
                    on_next=self._on_lifecycle_event,
                )
        return self._subscription

    def _on_lifecycle_event(self, started: bool) -> None:
        if started and self._on_start is not None:
            try:
                self._on_start()
            except Exception as e:
                if self._log_errors:
                    log.debug("MonitorObserver.on_start 异常: %s", e)
        elif (not started) and self._on_stop is not None:
            try:
                self._on_stop()
            except Exception as e:
                if self._log_errors:
                    log.debug("MonitorObserver.on_stop 异常: %s", e)

    def attach(self, source: Any) -> "MonitorObserver[T, E]":
        """链式 attach，便于 with 语法。"""
        self.subscribe(source)
        return self

    def unsubscribe(self) -> None:
        if self._subscription is not None:
            try:
                self._subscription.unsubscribe()
            except Exception:
                pass
            self._subscription = None
        if self._life_subscription is not None:
            try:
                self._life_subscription.unsubscribe()
            except Exception:
                pass
            self._life_subscription = None

    @property
    def is_subscribed(self) -> bool:
        return self._subscription is not None

    @property
    def last_value(self) -> Optional[T]:
        return self._last_value

    def __enter__(self) -> "MonitorObserver[T, E]":
        return self

    def __exit__(self, exc_type: Any = None, exc_val: Any = None, exc_tb: Any = None) -> None:
        self.unsubscribe()


# ═══════════════════════════════════════════════════════════
#   简易 MonitorSubject 工厂 —— 用于快速创建（内部使用）
# ═══════════════════════════════════════════════════════════


class SimpleMonitorSubject(MonitorSubject[T, D]):
    """最简单的 MonitorSubject 实现 —— 传入 dispatcher_factory 即可。

    用法：
        SimpleMonitorSubject(
            dispatcher_factory=lambda: MyDispatcher(...),
        )

    Attributes:
        _factory: 创建 Dispatcher 的工厂函数
    """

    __slots__ = ("_factory",)

    def __init__(self, dispatcher_factory: Callable[[], D]) -> None:
        """初始化简易 MonitorSubject。

        Args:
            dispatcher_factory: 返回 Dispatcher 实例的工厂函数
        """
        super().__init__()
        self._factory = dispatcher_factory
        # 立即创建并连接（保持与旧版 API 一致：实例化后即可 subscribe）
        self._dispatcher = self._factory()
        self._connect_dispatcher()

    def _create_dispatcher(self) -> D:
        return self._factory()

    def _connect_dispatcher(self) -> None:
        # Dispatcher.subject -> self.on_next/on_error/on_completed
        self._dispatcher.subject.subscribe(
            on_next=self.on_next,
            on_error=self.on_error,
            on_completed=self.on_completed,
        )