import ctypes
import os
from collections import deque
from enum import Enum
from typing import Any, Callable, Optional, Iterable, Type

from ..core.base import VoolsBase


class ItorState(Enum):
    PENDING = 0
    ITERRING = 1
    PAUSED = 2
    STOPPED = 3


class NimItor(VoolsBase):
    # BUG-418: get_itor() 在 Nim 可用时返回 NimItor，但它未继承 VoolsBase，
    # 与 Python 版 Itor 的统一 API 不一致（do/copy/to_dict/from_dict/update
    # 对 NimItor 全部 AttributeError）。a676de6 的 do 统一重构只覆盖 Python 侧。

    _dll = None
    _use_nim = False

    @classmethod
    def _load_dll(cls):
        if cls._dll is None:
            dll_path = os.path.join(os.path.dirname(__file__), 'itor.dll')
            if os.path.exists(dll_path):
                cls._dll = ctypes.CDLL(dll_path)
                cls._dll.newItor.argtypes = []
                cls._dll.newItor.restype = ctypes.c_void_p
                cls._dll.waitForData.argtypes = [ctypes.c_void_p]
                cls._dll.waitForData.restype = ctypes.c_bool
                cls._dll.signalData.argtypes = [ctypes.c_void_p]
                cls._dll.setPause.argtypes = [ctypes.c_void_p]
                cls._dll.resume.argtypes = [ctypes.c_void_p]
                cls._dll.stop.argtypes = [ctypes.c_void_p]
                cls._dll.restart.argtypes = [ctypes.c_void_p]
                cls._dll.state.argtypes = [ctypes.c_void_p]
                cls._dll.state.restype = ctypes.c_int
                cls._dll.freeItor.argtypes = [ctypes.c_void_p]
        return cls._dll is not None

    @classmethod
    def use_nim(cls, enabled: bool = True):
        if enabled:
            cls._use_nim = cls._load_dll()
            return cls._use_nim
        cls._use_nim = False
        return True

    def __init__(self, iterable: Iterable):
        if not self._load_dll():
            raise RuntimeError("Nim DLL not found")

        self._handle = None
        self._iterable = iterable
        self._iterator = None
        self._queue = deque()
        self._jump_queue = deque()
        self._source_exhausted = False
        self._started = False

        # BUG-419: 历史记录与策略（与 Python 版 Itor 对齐）。
        # 原实现 set_history_max/history_strategy 是**忽略参数的 no-op**，
        # 调用方以为限制生效实则完全没有记录历史。
        self._history: list = []
        self._history_strategy = None

        self._handle = self._dll.newItor()

    @property
    def state(self) -> ItorState:
        if self._handle is None:
            return ItorState.STOPPED
        dll_state = self._dll.state(self._handle)
        if dll_state == ItorState.STOPPED.value:
            return ItorState.STOPPED
        if dll_state == ItorState.PAUSED.value:
            return ItorState.PAUSED
        # DLL 无法区分 PENDING / ITERRING，由 Python 端维护起始标志
        if self._source_exhausted and not self._queue and not self._jump_queue:
            return ItorState.STOPPED
        return ItorState.ITERRING if self._started else ItorState.PENDING

    def send(self, jump: Any, jump_when: Optional[Callable[['NimItor'], bool]] = None) -> 'NimItor':
        if jump_when is not None:
            return self
        if isinstance(jump, (list, tuple)):
            for v in jump:
                self._jump_queue.append(v)
        else:
            self._jump_queue.append(jump)
        self._dll.signalData(self._handle)
        return self

    def set_pause(self) -> 'NimItor':
        self._dll.setPause(self._handle)
        return self

    def resume(self) -> 'NimItor':
        self._dll.resume(self._handle)
        return self

    def stop(self) -> 'NimItor':
        self._dll.stop(self._handle)
        return self

    def restart(self) -> 'NimItor':
        self._dll.restart(self._handle)
        self._iterator = None
        self._queue = deque()
        self._jump_queue = deque()
        self._source_exhausted = False
        return self

    def _record(self, item: Any) -> Any:
        """把产出值记入历史并应用历史策略（BUG-419）。"""
        self._history.append(item)
        strategy = self._history_strategy
        if strategy is not None:
            try:
                strategy(self)
            except Exception:
                pass
        return item

    def history_strategy(self, strategy=None) -> 'NimItor':
        """设置历史保留策略（BUG-419）。

        与 Python 版 :meth:`Itor.history_strategy` 语义一致：``strategy`` 为
        ``None`` 表示完全保留；策略函数接收 ``NimItor`` 实例并在每次产出后
        被调用（可在回调里修剪 ``itor._history``）。
        """
        self._history_strategy = strategy
        return self


    @classmethod
    def set_history_max(cls, itor: 'NimItor', max_len: int) -> Type['NimItor']:
        """
        与 Python 版 :meth:`Itor.set_history_max` 保持同一套校验与语义：

        - ``max_len == -1``：完全保留（清除已有策略）；
        - ``max_len >= 0``：最多保留最近 ``max_len`` 条；
        - 非整数 -> ``TypeError``；``< -1`` -> ``ValueError``。

        注意：Nim 侧的 ``restart`` 由 C DLL 提供，其重放行为不由本包装层
        控制（见 README 限制说明）。
        """
        if isinstance(max_len, bool) or not isinstance(max_len, int):
            raise TypeError("max_len must be an integer")
        if max_len < -1:
            raise ValueError("max_len must be >= -1")

        if max_len == -1:
            itor.history_strategy(None)
            return cls

        def keep_last(itor_: 'NimItor') -> None:
            history = itor_._history
            if len(history) > max_len:
                del history[: len(history) - max_len]

        itor.history_strategy(keep_last)
        return cls


    def __call__(self) -> 'NimItor':
        return NimItor(self._iterable)

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        while True:
            # 已停止的迭代器立即终止（无论队列中是否还有缓存值）
            if self._handle is not None and self._dll.state(self._handle) == ItorState.STOPPED.value:
                raise StopIteration

            if self._jump_queue:
                return self._record(self._jump_queue.popleft())

            if self._queue:
                return self._record(self._queue.popleft())

            if self._source_exhausted:
                raise StopIteration

            if self._iterator is None:
                self._iterator = iter(self._iterable)
                self._started = True

            try:
                item = next(self._iterator)
                return self._record(item)
            except StopIteration:
                self._source_exhausted = True

    def __del__(self):
        if self._handle is not None:
            self._dll.freeItor(self._handle)
            self._handle = None


__all__ = [
    'ItorState',
    'NimItor'
]
