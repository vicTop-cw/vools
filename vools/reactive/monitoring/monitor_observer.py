# -*- coding: utf-8 -*-
"""监控类 Observer 抽象基类 —— 统一事件类型路由分发逻辑。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..core.observable import Observer
__all__ = ['MonitorObserver']


class MonitorObserver(Observer, ABC):
    """按事件类型路由的 Observer 抽象基类。

    每个事件先通过 ``_event_type_of()`` 提取事件类型，再通过
    ``_handler_for()`` 查找对应回调。这样就不需要在每个子类中重复
    写 if/elif 事件类型判断逻辑。

    子类只需实现：
      - ``_event_type_of(value)``: 返回事件类型（如 KeyEventType）
      - ``_handler_for(event_type)``: 根据事件类型返回回调，可返回 None

    可选的 ``_on_any``: 无论事件类型是什么，都在路由处理后调用。

    用法示例::

        class KeyObserver(MonitorObserver):
            def _event_type_of(self, value):
                return value.event_type
            def _handler_for(self, event_type):
                if event_type == KeyEventType.KEY_DOWN:
                    return self._on_press
                return None

        obs = KeyObserver(on_press=lambda kd: print(kd))
        obs.subscribe(key_subject)
    """

    def __init__(
        self,
        *,
        on_any: Optional[Callable[[Any], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._on_any = on_any
        self._on_error_hook = on_error
        self._on_completed_hook = on_completed
        self._sub: Any = None
        self._source: Any = None

    @abstractmethod
    def _event_type_of(self, value: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def _handler_for(self, event_type: Any) -> Optional[Callable[[Any], Any]]:
        raise NotImplementedError

    def on_next(self, value: Any) -> None:
        event_type = self._event_type_of(value)
        handler = self._handler_for(event_type)
        if handler is not None:
            handler(value)
        if self._on_any is not None:
            self._on_any(value)

    def on_error(self, err: Exception) -> None:
        if self._on_error_hook is not None:
            self._on_error_hook(err)
        else:
            raise err

    def on_completed(self) -> None:
        if self._on_completed_hook is not None:
            self._on_completed_hook()

    def subscribe(self, source: Any) -> Any:
        """从 Observable 订阅。"""
        self._source = source
        self._sub = source.subscribe(
            on_next=self.on_next,
            on_error=self.on_error,
            on_completed=self.on_completed,
        )
        return self._sub

    def attach(self, source: Any) -> "MonitorObserver":
        """链式 attach（支持 with 语法）。"""
        self.subscribe(source)
        return self

    def unsubscribe(self) -> None:
        if self._sub:
            try:
                self._sub.unsubscribe()
            except Exception:
                pass
            self._sub = None

    @property
    def is_subscribed(self) -> bool:
        return self._sub is not None and getattr(self._sub, "is_active", True)

    def __enter__(self) -> "MonitorObserver":
        return self

    def __exit__(self, *args: Any) -> None:
        self.unsubscribe()


        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"