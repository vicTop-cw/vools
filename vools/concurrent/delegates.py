"""
vools.concurrent.delegates - 委托模式实现

提供多播委托、事件总线、消息分发器等委托模式工具，支持同步和异步调用。

主要组件：
    Delegate         - 多播委托（类似 C# 的 delegate）
    AsyncDelegate    - 异步版本委托（回调在独立线程中执行）
    EventBus         - 事件总线（支持通配符事件、优先级）
    MessageDispatcher - 消息分发器（按类型分发）
    CallbackChain    - 回调链（可决定是否继续传递）
    delegate         - 装饰器，将函数包装为 Delegate
    thread_safe      - 装饰器，给委托/事件总线加上线程安全锁
"""

from __future__ import annotations

import threading
from functools import wraps
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Type, TypeVar

__all__ = [
    "Delegate",
    "AsyncDelegate",
    "EventBus",
    "MessageDispatcher",
    "CallbackChain",
    "delegate",
    "thread_safe",
]

_T = TypeVar("_T")
_F = TypeVar("_F", bound=Callable[..., Any])


# ============================================================================
# Delegate - 多播委托
# ============================================================================


class Delegate:
    """多播委托，类似 C# 的 delegate。

    支持 ``+=`` / ``-=`` 操作符添加和移除回调，``invoke`` 调用所有回调
    并返回结果列表。

    示例::

        def handler1(x):
            return x * 2

        def handler2(x):
            return x + 10

        d = Delegate()
        d += handler1
        d += handler2
        results = d.invoke(5)  # [10, 15]
        d -= handler1
    """

    def __init__(self) -> None:
        self._handlers: List[Callable[..., Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 回调管理
    # ------------------------------------------------------------------
    def add(self, handler: Callable[..., Any]) -> "Delegate":
        """添加一个回调。

        Args:
            handler: 回调函数。

        Returns:
            Delegate: 自身，支持链式调用。
        """
        with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)
        return self

    def remove(self, handler: Callable[..., Any]) -> "Delegate":
        """移除一个回调。

        Args:
            handler: 要移除的回调函数。

        Returns:
            Delegate: 自身，支持链式调用。
        """
        with self._lock:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass
        return self

    def clear(self) -> None:
        """移除所有回调。"""
        with self._lock:
            self._handlers.clear()

    @property
    def handlers(self) -> List[Callable[..., Any]]:
        """当前所有回调的副本。"""
        with self._lock:
            return list(self._handlers)

    @property
    def count(self) -> int:
        """回调数量。"""
        with self._lock:
            return len(self._handlers)

    # ------------------------------------------------------------------
    # 调用
    # ------------------------------------------------------------------
    def invoke(self, *args: Any, **kwargs: Any) -> List[Any]:
        """调用所有回调，按添加顺序执行，返回结果列表。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            List[Any]: 各回调的返回值组成的列表。
        """
        with self._lock:
            handlers = list(self._handlers)
        results: List[Any] = []
        for handler in handlers:
            results.append(handler(*args, **kwargs))
        return results

    def invoke_safe(self, *args: Any, **kwargs: Any) -> List[Any]:
        """安全调用所有回调，单个回调异常不影响其他回调。

        异常会被捕获并忽略。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            List[Any]: 各回调的返回值组成的列表（异常的回调结果为 None）。
        """
        with self._lock:
            handlers = list(self._handlers)
        results: List[Any] = []
        for handler in handlers:
            try:
                results.append(handler(*args, **kwargs))
            except Exception:
                results.append(None)
        return results

    # ------------------------------------------------------------------
    # 操作符重载
    # ------------------------------------------------------------------
    def __iadd__(self, handler: Callable[..., Any]) -> "Delegate":
        return self.add(handler)

    def __isub__(self, handler: Callable[..., Any]) -> "Delegate":
        return self.remove(handler)

    def __call__(self, *args: Any, **kwargs: Any) -> List[Any]:
        return self.invoke(*args, **kwargs)

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return self.count > 0

    def __contains__(self, handler: object) -> bool:
        with self._lock:
            return handler in self._handlers

    def __iter__(self) -> Generator[Callable[..., Any], None, None]:
        with self._lock:
            handlers = list(self._handlers)
        for h in handlers:
            yield h

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "Delegate":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.clear()
        return False

    def __repr__(self) -> str:
        return f"<Delegate handlers={self.count}>"


# ============================================================================
# AsyncDelegate - 异步委托
# ============================================================================


class AsyncDelegate:
    """异步版本委托，回调在独立线程中执行。

    每个回调在单独的线程中执行，``invoke`` 立即返回线程对象列表。

    示例::

        def slow_task(x):
            time.sleep(1)
            return x * 2

        d = AsyncDelegate()
        d += slow_task
        threads = d.invoke(5)  # 立即返回，不阻塞
        for t in threads:
            t.join()
    """

    def __init__(self, daemon: bool = True) -> None:
        self._handlers: List[Callable[..., Any]] = []
        self._lock = threading.RLock()
        self._daemon = daemon

    # ------------------------------------------------------------------
    # 回调管理
    # ------------------------------------------------------------------
    def add(self, handler: Callable[..., Any]) -> "AsyncDelegate":
        """添加一个回调。"""
        with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)
        return self

    def remove(self, handler: Callable[..., Any]) -> "AsyncDelegate":
        """移除一个回调。"""
        with self._lock:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass
        return self

    def clear(self) -> None:
        """移除所有回调。"""
        with self._lock:
            self._handlers.clear()

    @property
    def handlers(self) -> List[Callable[..., Any]]:
        """当前所有回调的副本。"""
        with self._lock:
            return list(self._handlers)

    @property
    def count(self) -> int:
        """回调数量。"""
        with self._lock:
            return len(self._handlers)

    # ------------------------------------------------------------------
    # 调用
    # ------------------------------------------------------------------
    def invoke(self, *args: Any, **kwargs: Any) -> List[threading.Thread]:
        """异步调用所有回调，每个回调在独立线程中执行。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            List[threading.Thread]: 执行各回调的线程列表。
        """
        with self._lock:
            handlers = list(self._handlers)
        threads: List[threading.Thread] = []
        for i, handler in enumerate(handlers):
            t = threading.Thread(
                target=handler,
                args=args,
                kwargs=kwargs,
                daemon=self._daemon,
                name=f"AsyncDelegate-{i}-{handler.__name__ if hasattr(handler, '__name__') else 'anon'}",
            )
            t.start()
            threads.append(t)
        return threads

    def invoke_and_wait(
        self, *args: Any, timeout: Optional[float] = None, **kwargs: Any
    ) -> List[Any]:
        """异步调用所有回调并等待全部完成。

        Args:
            *args: 位置参数。
            timeout: 每个线程的等待超时（秒），``None`` 表示无限等待。
            **kwargs: 关键字参数。

        Returns:
            List[Any]: 各回调的返回值列表（无法获取返回值的为 None）。

        Note:
            由于线程不直接返回值，本方法通过包装函数捕获返回值。
        """
        with self._lock:
            handlers = list(self._handlers)

        results: List[Any] = [None] * len(handlers)
        threads: List[threading.Thread] = []

        def _runner(idx: int, h: Callable[..., Any]) -> None:
            try:
                results[idx] = h(*args, **kwargs)
            except Exception:
                results[idx] = None

        for i, handler in enumerate(handlers):
            t = threading.Thread(
                target=_runner,
                args=(i, handler),
                daemon=self._daemon,
                name=f"AsyncDelegate-wait-{i}",
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=timeout)

        return results

    # ------------------------------------------------------------------
    # 操作符重载
    # ------------------------------------------------------------------
    def __iadd__(self, handler: Callable[..., Any]) -> "AsyncDelegate":
        return self.add(handler)

    def __isub__(self, handler: Callable[..., Any]) -> "AsyncDelegate":
        return self.remove(handler)

    def __call__(self, *args: Any, **kwargs: Any) -> List[threading.Thread]:
        return self.invoke(*args, **kwargs)

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return self.count > 0

    def __contains__(self, handler: object) -> bool:
        with self._lock:
            return handler in self._handlers

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "AsyncDelegate":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.clear()
        return False

    def __repr__(self) -> str:
        return f"<AsyncDelegate handlers={self.count} daemon={self._daemon}>"


# ============================================================================
# EventBus - 事件总线
# ============================================================================


class EventBus:
    """事件总线，支持订阅/发布模式。

    特性：
        - 按事件名订阅和发布
        - 支持通配符事件（``*`` 匹配所有事件）
        - 支持订阅优先级（数值越小优先级越高）
        - 线程安全

    示例::

        bus = EventBus()

        def on_data(data):
            print("data:", data)

        def on_any(event, data):
            print("any event:", event, data)

        bus.subscribe("data", on_data)
        bus.subscribe("*", on_any)  # 通配符
        bus.publish("data", {"key": "value"})
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Tuple[int, Callable[..., Any]]]] = {}
        self._lock = threading.RLock()
        self._wildcard = "*"

    # ------------------------------------------------------------------
    # 订阅/取消订阅
    # ------------------------------------------------------------------
    def subscribe(
        self,
        event: str,
        handler: Callable[..., Any],
        priority: int = 0,
    ) -> "EventBus":
        """订阅事件。

        Args:
            event: 事件名；``"*"`` 表示通配符，匹配所有事件。
            handler: 事件处理函数，签名为 ``handler(event, *args, **kwargs)``
                     或 ``handler(*args, **kwargs)``。
            priority: 优先级，数值越小优先级越高，默认 0。

        Returns:
            EventBus: 自身，支持链式调用。
        """
        with self._lock:
            if event not in self._subscribers:
                self._subscribers[event] = []
            subscribers = self._subscribers[event]
            entry = (priority, handler)
            if entry not in subscribers:
                subscribers.append(entry)
                subscribers.sort(key=lambda x: x[0])
        return self

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> "EventBus":
        """取消订阅事件。

        Args:
            event: 事件名。
            handler: 要取消的处理函数。

        Returns:
            EventBus: 自身，支持链式调用。
        """
        with self._lock:
            if event in self._subscribers:
                self._subscribers[event] = [
                    (p, h) for p, h in self._subscribers[event] if h is not handler
                ]
                if not self._subscribers[event]:
                    del self._subscribers[event]
        return self

    def unsubscribe_all(self, event: Optional[str] = None) -> None:
        """取消所有订阅。

        Args:
            event: 指定事件名；``None`` 表示取消所有事件的订阅。
        """
        with self._lock:
            if event is None:
                self._subscribers.clear()
            elif event in self._subscribers:
                del self._subscribers[event]

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------
    def publish(self, event: str, *args: Any, **kwargs: Any) -> List[Any]:
        """发布事件。

        按优先级顺序调用所有匹配的订阅者（精确匹配 + 通配符匹配）。
        精确匹配的订阅者优先于通配符订阅者。

        Args:
            event: 事件名。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            List[Any]: 各订阅者的返回值列表。
        """
        with self._lock:
            exact = list(self._subscribers.get(event, []))
            wildcard = list(self._subscribers.get(self._wildcard, []))

        all_handlers: List[Tuple[int, bool, Callable[..., Any]]] = []
        for pri, h in exact:
            all_handlers.append((pri, False, h))
        for pri, h in wildcard:
            all_handlers.append((pri, True, h))

        all_handlers.sort(key=lambda x: (x[0], x[1]))

        results: List[Any] = []
        for _, _, handler in all_handlers:
            try:
                results.append(handler(event, *args, **kwargs))
            except TypeError:
                try:
                    results.append(handler(*args, **kwargs))
                except Exception:
                    results.append(None)
            except Exception:
                results.append(None)
        return results

    def publish_safe(self, event: str, *args: Any, **kwargs: Any) -> List[Any]:
        """安全发布事件，单个订阅者异常不影响其他订阅者。

        Args:
            event: 事件名。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            List[Any]: 各订阅者的返回值列表（异常的为 None）。
        """
        with self._lock:
            exact = list(self._subscribers.get(event, []))
            wildcard = list(self._subscribers.get(self._wildcard, []))

        all_handlers: List[Tuple[int, bool, Callable[..., Any]]] = []
        for pri, h in exact:
            all_handlers.append((pri, False, h))
        for pri, h in wildcard:
            all_handlers.append((pri, True, h))

        all_handlers.sort(key=lambda x: (x[0], x[1]))

        results: List[Any] = []
        for _, _, handler in all_handlers:
            try:
                try:
                    results.append(handler(event, *args, **kwargs))
                except TypeError:
                    results.append(handler(*args, **kwargs))
            except Exception:
                results.append(None)
        return results

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def has_subscribers(self, event: str) -> bool:
        """检查事件是否有订阅者（包括通配符）。"""
        with self._lock:
            return bool(self._subscribers.get(event)) or bool(
                self._subscribers.get(self._wildcard)
            )

    def subscriber_count(self, event: str) -> int:
        """获取事件的订阅者数量（包括通配符）。"""
        with self._lock:
            count = len(self._subscribers.get(event, []))
            count += len(self._subscribers.get(self._wildcard, []))
            return count

    def events(self) -> List[str]:
        """获取所有有订阅者的事件名列表。"""
        with self._lock:
            return list(self._subscribers.keys())

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "EventBus":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.unsubscribe_all()
        return False

    def __repr__(self) -> str:
        with self._lock:
            n = sum(len(v) for v in self._subscribers.values())
            e = len(self._subscribers)
        return f"<EventBus events={e} subscribers={n}>"


# ============================================================================
# MessageDispatcher - 消息分发器
# ============================================================================


class MessageDispatcher:
    """消息分发器，支持按消息类型注册处理器并分发。

    与 EventBus 的区别：
        - EventBus 按字符串事件名分发
        - MessageDispatcher 按消息对象的类型（class）分发
        - MessageDispatcher 支持继承链匹配（父类处理器也能处理子类消息）

    示例::

        class StartMessage:
            pass

        class StopMessage:
            pass

        dispatcher = MessageDispatcher()

        def on_start(msg):
            print("start")

        def on_stop(msg):
            print("stop")

        dispatcher.register(StartMessage, on_start)
        dispatcher.register(StopMessage, on_stop)
        dispatcher.dispatch(StartMessage())
    """

    def __init__(self) -> None:
        self._handlers: Dict[Type[Any], List[Callable[[Any], Any]]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 注册/注销
    # ------------------------------------------------------------------
    def register(self, msg_type: Type[Any], handler: Callable[[Any], Any]) -> "MessageDispatcher":
        """注册消息处理器。

        Args:
            msg_type: 消息类型（类）。
            handler: 处理函数，接收一个消息参数。

        Returns:
            MessageDispatcher: 自身，支持链式调用。
        """
        with self._lock:
            if msg_type not in self._handlers:
                self._handlers[msg_type] = []
            if handler not in self._handlers[msg_type]:
                self._handlers[msg_type].append(handler)
        return self

    def unregister(self, msg_type: Type[Any], handler: Callable[[Any], Any]) -> "MessageDispatcher":
        """注销消息处理器。

        Args:
            msg_type: 消息类型。
            handler: 要注销的处理函数。

        Returns:
            MessageDispatcher: 自身，支持链式调用。
        """
        with self._lock:
            if msg_type in self._handlers:
                try:
                    self._handlers[msg_type].remove(handler)
                    if not self._handlers[msg_type]:
                        del self._handlers[msg_type]
                except ValueError:
                    pass
        return self

    def unregister_all(self, msg_type: Optional[Type[Any]] = None) -> None:
        """注销所有处理器。

        Args:
            msg_type: 指定消息类型；``None`` 表示注销所有类型。
        """
        with self._lock:
            if msg_type is None:
                self._handlers.clear()
            elif msg_type in self._handlers:
                del self._handlers[msg_type]

    # ------------------------------------------------------------------
    # 分发
    # ------------------------------------------------------------------
    def dispatch(self, message: Any) -> List[Any]:
        """分发消息到所有匹配的处理器。

        匹配规则：消息类型完全匹配，或消息是某个已注册类型的子类。

        Args:
            message: 消息对象。

        Returns:
            List[Any]: 各处理器的返回值列表。
        """
        msg_type = type(message)
        with self._lock:
            handlers: List[Callable[[Any], Any]] = []
            for registered_type, h_list in self._handlers.items():
                if issubclass(msg_type, registered_type):
                    handlers.extend(h_list)

        results: List[Any] = []
        for handler in handlers:
            results.append(handler(message))
        return results

    def dispatch_safe(self, message: Any) -> List[Any]:
        """安全分发消息，单个处理器异常不影响其他处理器。

        Args:
            message: 消息对象。

        Returns:
            List[Any]: 各处理器的返回值列表（异常的为 None）。
        """
        msg_type = type(message)
        with self._lock:
            handlers: List[Callable[[Any], Any]] = []
            for registered_type, h_list in self._handlers.items():
                if issubclass(msg_type, registered_type):
                    handlers.extend(h_list)

        results: List[Any] = []
        for handler in handlers:
            try:
                results.append(handler(message))
            except Exception:
                results.append(None)
        return results

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def has_handlers(self, msg_type: Type[Any]) -> bool:
        """检查某消息类型是否有处理器（含父类匹配）。"""
        with self._lock:
            for registered_type in self._handlers:
                if issubclass(msg_type, registered_type):
                    return True
            return False

    def handler_count(self, msg_type: Type[Any]) -> int:
        """获取某消息类型的处理器数量（含父类匹配）。"""
        with self._lock:
            count = 0
            for registered_type, h_list in self._handlers.items():
                if issubclass(msg_type, registered_type):
                    count += len(h_list)
            return count

    def registered_types(self) -> List[Type[Any]]:
        """获取所有已注册的消息类型。"""
        with self._lock:
            return list(self._handlers.keys())

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "MessageDispatcher":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.unregister_all()
        return False

    def __repr__(self) -> str:
        with self._lock:
            n = sum(len(v) for v in self._handlers.values())
            t = len(self._handlers)
        return f"<MessageDispatcher types={t} handlers={n}>"


# ============================================================================
# CallbackChain - 回调链
# ============================================================================


class CallbackChain:
    """回调链，每个回调可决定是否继续传递。

    回调返回 ``True`` 表示继续链传递，返回 ``False`` 或其他假值表示停止。
    支持前置回调和后置回调。

    示例::

        chain = CallbackChain()

        def step1(data):
            print("step1")
            return True  # 继续

        def step2(data):
            print("step2")
            return False  # 停止，step3 不会执行

        def step3(data):
            print("step3")
            return True

        chain.add(step1)
        chain.add(step2)
        chain.add(step3)
        chain.execute("data")  # 只执行 step1 和 step2
    """

    def __init__(self) -> None:
        self._callbacks: List[Callable[..., bool]] = []
        self._pre_callbacks: List[Callable[..., Any]] = []
        self._post_callbacks: List[Callable[..., Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 回调管理
    # ------------------------------------------------------------------
    def add(self, callback: Callable[..., bool]) -> "CallbackChain":
        """添加一个链回调。

        Args:
            callback: 回调函数，返回 True 继续，返回 False 停止。

        Returns:
            CallbackChain: 自身，支持链式调用。
        """
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)
        return self

    def remove(self, callback: Callable[..., bool]) -> "CallbackChain":
        """移除一个链回调。"""
        with self._lock:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass
        return self

    def add_pre(self, callback: Callable[..., Any]) -> "CallbackChain":
        """添加前置回调（在链执行前调用，不影响链的传递）。"""
        with self._lock:
            if callback not in self._pre_callbacks:
                self._pre_callbacks.append(callback)
        return self

    def remove_pre(self, callback: Callable[..., Any]) -> "CallbackChain":
        """移除前置回调。"""
        with self._lock:
            try:
                self._pre_callbacks.remove(callback)
            except ValueError:
                pass
        return self

    def add_post(self, callback: Callable[..., Any]) -> "CallbackChain":
        """添加后置回调（在链执行后调用，无论是否中途停止）。"""
        with self._lock:
            if callback not in self._post_callbacks:
                self._post_callbacks.append(callback)
        return self

    def remove_post(self, callback: Callable[..., Any]) -> "CallbackChain":
        """移除后置回调。"""
        with self._lock:
            try:
                self._post_callbacks.remove(callback)
            except ValueError:
                pass
        return self

    def clear(self) -> None:
        """移除所有回调。"""
        with self._lock:
            self._callbacks.clear()
            self._pre_callbacks.clear()
            self._post_callbacks.clear()

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def execute(self, *args: Any, **kwargs: Any) -> bool:
        """执行回调链。

        顺序：前置回调 -> 链回调（按顺序，返回 False 停止） -> 后置回调。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            bool: 链是否完整执行完毕（所有链回调都返回 True）。
        """
        with self._lock:
            pre = list(self._pre_callbacks)
            callbacks = list(self._callbacks)
            post = list(self._post_callbacks)

        for pre_cb in pre:
            try:
                pre_cb(*args, **kwargs)
            except Exception:
                pass

        completed = True
        for cb in callbacks:
            try:
                result = cb(*args, **kwargs)
                if not result:
                    completed = False
                    break
            except Exception:
                completed = False
                break

        for post_cb in post:
            try:
                post_cb(*args, **kwargs)
            except Exception:
                pass

        return completed

    # ------------------------------------------------------------------
    # 操作符重载
    # ------------------------------------------------------------------
    def __iadd__(self, callback: Callable[..., bool]) -> "CallbackChain":
        return self.add(callback)

    def __isub__(self, callback: Callable[..., bool]) -> "CallbackChain":
        return self.remove(callback)

    def __call__(self, *args: Any, **kwargs: Any) -> bool:
        return self.execute(*args, **kwargs)

    def __len__(self) -> int:
        with self._lock:
            return len(self._callbacks) + len(self._pre_callbacks) + len(self._post_callbacks)

    def __bool__(self) -> bool:
        return len(self) > 0

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> "CallbackChain":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.clear()
        return False

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"<CallbackChain main={len(self._callbacks)} "
                f"pre={len(self._pre_callbacks)} post={len(self._post_callbacks)}>"
            )


# ============================================================================
# 装饰器
# ============================================================================


def delegate(func: Optional[_F] = None) -> Any:
    """装饰器：将函数包装为 Delegate。

    用法一：直接装饰::

        @delegate
        def on_event(x):
            return x * 2

        on_event += another_handler  # 可以添加更多回调
        results = on_event(5)  # 调用所有回调

    用法二：先创建后赋值::

        d = delegate()  # 空委托
        d += handler

    Args:
        func: 要包装的函数；为 None 时返回空 Delegate。

    Returns:
        Delegate 实例。
    """
    if func is None:
        return Delegate()

    d = Delegate()
    d.add(func)
    return d


def thread_safe(target: Any = None, lock: Optional[threading.RLock] = None) -> Any:
    """装饰器：给委托/事件总线加上线程安全锁包装。

    注意：Delegate、EventBus 等本身已是线程安全的，此装饰器用于
    在自定义类或函数上添加线程安全。

    用法一：装饰类::

        @thread_safe
        class MyService:
            def method(self):
                ...

    用法二：装饰函数::

        @thread_safe
        def critical_section():
            ...

    用法三：指定锁::

        my_lock = threading.RLock()
        @thread_safe(lock=my_lock)
        def func():
            ...

    Args:
        target: 要装饰的类或函数。
        lock: 要使用的锁；为 None 时创建新的 RLock。

    Returns:
        装饰后的类或函数。
    """
    _lock = lock if lock is not None else threading.RLock()

    def _decorator(obj: Any) -> Any:
        if isinstance(obj, type):
            # 装饰类：给所有公共方法加锁
            orig_class = obj

            class _ThreadSafeWrapper:
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    self._obj = orig_class(*args, **kwargs)
                    self._lock = _lock

                def __getattr__(self, name: str) -> Any:
                    attr = getattr(self._obj, name)
                    if callable(attr) and not name.startswith("_"):
                        @wraps(attr)
                        def wrapper(*a: Any, **kw: Any) -> Any:
                            with self._lock:
                                return attr(*a, **kw)
                        return wrapper
                    return attr

                def __enter__(self) -> Any:
                    if hasattr(self._obj, "__enter__"):
                        self._lock.acquire()
                        self._obj.__enter__()
                        return self
                    return self

                def __exit__(self, *args: Any) -> bool:
                    try:
                        if hasattr(self._obj, "__exit__"):
                            return self._obj.__exit__(*args)
                        return False
                    finally:
                        self._lock.release()

            _ThreadSafeWrapper.__name__ = orig_class.__name__
            _ThreadSafeWrapper.__doc__ = orig_class.__doc__
            return _ThreadSafeWrapper

        elif callable(obj):
            # 装饰函数
            @wraps(obj)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with _lock:
                    return obj(*args, **kwargs)
            return wrapper

        else:
            return obj

    if target is None:
        return _decorator
    return _decorator(target)
