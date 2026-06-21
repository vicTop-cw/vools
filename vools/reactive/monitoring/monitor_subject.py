# -*- coding: utf-8 -*-
"""监控类 Subject 抽象基类 —— 统一 start/stop 生命周期管理。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Set, Tuple

from ..core.subject import Subject
__all__ = ['MonitorSubject']


class MonitorSubject(Subject, ABC):
    """带生命周期监控能力的 Subject 抽象基类。

    子类只需实现：
      - ``_create_dispatcher()``: 创建并返回 dispatcher 实例
      - ``_connect_dispatcher()``: 将 dispatcher 的事件连接到 ``self.on_next``

    子类应该在自己的 ``__init__`` 中：
      1. 设置所有配置属性（如 self._backend, self._interval 等）
      2. 调用 ``super().__init__()``（它会自动调用 _create_dispatcher()）

    用法示例::

        class KeySubject(MonitorSubject):
            def __init__(self, backend='auto'):
                self._backend = backend
                super().__init__()  # 内部会调用 _create_dispatcher()

            def _create_dispatcher(self):
                return KeyboardDispatcher(backend=self._backend)

            def _connect_dispatcher(self):
                self._dispatcher.subject.subscribe(on_next=self.on_next)

        subj = KeySubject()
        subj.subscribe(on_next=print)
        subj.start()
    """

    def __init__(self):
        super().__init__()
        # 先初始化基础状态，然后创建 dispatcher（子类属性此时应已设置）
        self._monitoring: bool = False
        self._conn_sub: Any = None
        self._dispatcher: Any = self._create_dispatcher()

    @property
    def monitoring(self) -> bool:
        return self._monitoring

    @property
    def dispatcher(self) -> Any:
        return self._dispatcher

    @property
    def subject(self) -> Any:
        # 兼容旧 API: 返回自身（因为 self 就是 Subject）
        return self

    @abstractmethod
    def _create_dispatcher(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def _connect_dispatcher(self) -> None:
        raise NotImplementedError

    def start(self) -> "MonitorSubject":
        """启动监控。"""
        if self._conn_sub is None:
            self._connect_dispatcher()
        if not getattr(self._dispatcher, "is_running", False):
            self._dispatcher.start()
        self._monitoring = True
        return self

    def stop(self) -> "MonitorSubject":
        """停止监控。"""
        if self._dispatcher is not None and getattr(
            self._dispatcher, "is_running", False
        ):
            self._dispatcher.stop()
        self._monitoring = False
        return self

    @property
    def is_running(self) -> bool:
        if self._dispatcher is None:
            return False
        return bool(getattr(self._dispatcher, "is_running", False))

    def __bool__(self) -> bool:
        return self._monitoring

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} monitoring={self._monitoring}>"

    def __enter__(self) -> "MonitorSubject":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


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
    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass