import ctypes
import os
from collections import deque
from enum import Enum
from typing import Any, Callable, Optional, Iterable, Type


class ItorState(Enum):
    PENDING = 0
    ITERRING = 1
    PAUSED = 2
    STOPPED = 3


class NimItor:
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

    def history_strategy(self, strategy=None) -> 'NimItor':
        return self

    @classmethod
    def set_history_max(cls, itor: 'NimItor', max_len: int) -> Type['NimItor']:
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
                return self._jump_queue.popleft()

            if self._queue:
                return self._queue.popleft()

            if self._source_exhausted:
                raise StopIteration

            if self._iterator is None:
                self._iterator = iter(self._iterable)
                self._started = True

            try:
                item = next(self._iterator)
                return item
            except StopIteration:
                self._source_exhausted = True

    def __del__(self):
        if self._handle is not None:
            self._dll.freeItor(self._handle)
            self._handle = None