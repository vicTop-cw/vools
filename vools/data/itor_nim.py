import ctypes
import os
import pickle
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
                cls._dll.newItor.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
                                             ctypes.POINTER(ctypes.c_int), ctypes.c_int]
                cls._dll.newItor.restype = ctypes.c_void_p
                cls._dll.nextValue.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                               ctypes.POINTER(ctypes.c_int)]
                cls._dll.nextValue.restype = ctypes.c_bool
                cls._dll.setPause.argtypes = [ctypes.c_void_p]
                cls._dll.resume.argtypes = [ctypes.c_void_p]
                cls._dll.stop.argtypes = [ctypes.c_void_p]
                cls._dll.restart.argtypes = [ctypes.c_void_p]
                cls._dll.sendJump.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
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
        self._data_buffer = None
        self._offsets = []

        serialized_items = [pickle.dumps(item) for item in iterable]
        
        total_len = sum(len(item) for item in serialized_items)
        self._data_buffer = (ctypes.c_ubyte * total_len)()
        
        offset = 0
        self._offsets = []
        for item in serialized_items:
            self._offsets.append(offset)
            for i, byte in enumerate(item):
                self._data_buffer[offset + i] = byte
            offset += len(item)
        
        offsets_arr = (ctypes.c_int * len(self._offsets))(*self._offsets)
        self._handle = self._dll.newItor(self._data_buffer, total_len, offsets_arr, len(self._offsets))

    @property
    def state(self) -> ItorState:
        if self._handle is None:
            return ItorState.STOPPED
        return ItorState(self._dll.state(self._handle))

    def send(self, jump: Any, jump_when: Optional[Callable[['NimItor'], bool]] = None) -> 'NimItor':
        if jump_when is not None:
            return self
        if isinstance(jump, (list, tuple)):
            for v in jump:
                self._send_single(v)
        else:
            self._send_single(jump)
        return self

    def _send_single(self, value):
        serialized = pickle.dumps(value)
        offset = len(self._data_buffer)
        new_len = offset + len(serialized)
        new_buffer = (ctypes.c_ubyte * new_len)()
        for i in range(len(self._data_buffer)):
            new_buffer[i] = self._data_buffer[i]
        for i, byte in enumerate(serialized):
            new_buffer[offset + i] = byte
        self._data_buffer = new_buffer
        self._dll.sendJump(self._handle, offset, len(serialized))

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
        return self

    def history_strategy(self, strategy=None) -> 'NimItor':
        return self

    @classmethod
    def set_history_max(cls, itor: 'NimItor', max_len: int) -> Type['NimItor']:
        return cls

    def __call__(self) -> 'NimItor':
        return NimItor([])

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        offset = ctypes.c_int()
        length = ctypes.c_int()
        if self._dll.nextValue(self._handle, offset, length):
            start = offset.value
            end = start + length.value
            data_bytes = bytes(self._data_buffer[start:end])
            return pickle.loads(data_bytes)
        raise StopIteration

    def __del__(self):
        if self._handle is not None:
            self._dll.freeItor(self._handle)
            self._handle = None