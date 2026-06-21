"""
mouse - Mouse input monitoring and simulation.
"""
from __future__ import annotations

import ctypes
import datetime
import itertools
import json
import logging
import pickle
import sys
import time
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import (
    Any, Callable, Dict, List, Optional, Tuple,
    Union, TYPE_CHECKING,
)
from threading import Thread, Lock, Event
from collections import defaultdict
from queue import Queue

from .monitor_subject import MonitorSubject
from .monitor_observer import MonitorObserver
__all__ = ['log', 'MAX_SIGNATURE_AGE', 'MouseEventType', 'MouseData', 'MouseDispatcher', 'MouseSubject', 'MouseObserver', 'from_mouse', 'write_to_mouse']

if TYPE_CHECKING:
    from vools.reactive.core.observable import Observable, Observer, Subscription
    from vools.reactive.core.subject import Subject

log = logging.getLogger(__name__)

_seq_counter = itertools.count(1)
MAX_SIGNATURE_AGE = 0.5


class MouseEventType(IntEnum):
    MOVE = 0
    LEFT_DOWN = 1
    LEFT_UP = 2
    RIGHT_DOWN = 3
    RIGHT_UP = 4
    MIDDLE_DOWN = 5
    MIDDLE_UP = 6
    SCROLL = 7
    DRAG = 8
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



def _make_mouse_signature(x: int, y: int, event_type: int) -> Tuple[int, int, int]:
    return (x, y, event_type)


@dataclass
class MouseData:
    x: int = 0
    y: int = 0
    event_type: int = MouseEventType.MOVE
    button: str = ""
    delta: int = 0
    timestamp: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    sequence: int = 0
    tags: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.button == "":
            et = MouseEventType(self.event_type)
            if et in (MouseEventType.LEFT_DOWN, MouseEventType.LEFT_UP):
                object.__setattr__(self, 'button', 'left')
            elif et in (MouseEventType.RIGHT_DOWN, MouseEventType.RIGHT_UP):
                object.__setattr__(self, 'button', 'right')
            elif et in (MouseEventType.MIDDLE_DOWN, MouseEventType.MIDDLE_UP):
                object.__setattr__(self, 'button', 'middle')
            else:
                object.__setattr__(self, 'button', 'left')
        if self.sequence == 0:
            object.__setattr__(self, 'sequence', next(_seq_counter))

    @classmethod
    def now(
        cls,
        x: int = 0,
        y: int = 0,
        event_type: int = MouseEventType.MOVE,
        button: Optional[str] = None,
        delta: int = 0,
        tags: Tuple[str, ...] = (),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "MouseData":
        return cls(
            x=x, y=y,
            event_type=event_type,
            button=button if button is not None else "",
            delta=delta,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            sequence=next(_seq_counter),
            tags=tags,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d["timestamp"], datetime.datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MouseData":
        if isinstance(d.get("timestamp"), str):
            d["timestamp"] = datetime.datetime.fromisoformat(d["timestamp"])
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "MouseData":
        return cls.from_dict(json.loads(s))

    def to_pickle(self) -> bytes:
        return pickle.dumps(asdict(self))

    @classmethod
    def from_pickle(cls, data: bytes) -> "MouseData":
        return cls.from_dict(pickle.loads(data))

    def __repr__(self) -> str:
        return (
            f"MouseData(x={self.x}, y={self.y}, "
            f"event_type={MouseEventType(self.event_type).name!r}, "
            f"button={self.button!r}, seq={self.sequence})"
        )


if sys.platform == "win32":
    _user32 = ctypes.PyDLL("user32.dll", use_last_error=True)
    _kernel32 = ctypes.PyDLL("kernel32.dll", use_last_error=True)

    ULONG_PTR = ctypes.c_ulonglong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]
        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self for chaining.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function applied before f
                sub_f: Post-processing function (no return expected)

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


    class INPUT(ctypes.Structure):
        class _INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

            def do(self, f=print, pre_f=None, sub_f=None):
                """Apply a function for side effects, return self for chaining.

                Args:
                    f: Function to apply (default print)
                    pre_f: Pre-processing function applied before f
                    sub_f: Post-processing function (no return expected)

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

        _fields_ = [("type", ctypes.c_ulong), ("U", _INPUT_UNION)]
        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self for chaining.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function applied before f
                sub_f: Post-processing function (no return expected)

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


    INPUT_MOUSE = 0

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000

    _user32.SendInput.argtypes = [ctypes.c_ulong, ctypes.POINTER(INPUT), ctypes.c_int]
    _user32.SendInput.restype = ctypes.c_ulong
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
    _user32.GetCursorPos.restype = ctypes.c_bool
    _user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _user32.SetCursorPos.restype = ctypes.c_bool

    def _get_screen_size() -> Tuple[int, int]:
        try:
            w = _user32.GetSystemMetrics(0)
            h = _user32.GetSystemMetrics(1)
            return w, h
        except Exception:
            return 1920, 1080

    def _move_to(x: int, y: int) -> None:
        w, h = _get_screen_size()
        nx = int(x * 65535 / w)
        ny = int(y * 65535 / h)
        inp = INPUT(type=INPUT_MOUSE)
        inp.U.mi.dx = nx
        inp.U.mi.dy = ny
        inp.U.mi.mouseData = 0
        inp.U.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
        inp.U.mi.time = 0
        inp.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _click(button: str = "left") -> None:
        if button == "left":
            d, u = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        elif button == "right":
            d, u = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif button == "middle":
            d, u = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        else:
            d, u = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        inp_d = INPUT(type=INPUT_MOUSE)
        inp_d.U.mi.dx = 0; inp_d.U.mi.dy = 0
        inp_d.U.mi.mouseData = 0; inp_d.U.mi.dwFlags = d
        inp_d.U.mi.time = 0; inp_d.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp_d), ctypes.sizeof(INPUT))
        inp_u = INPUT(type=INPUT_MOUSE)
        inp_u.U.mi.dx = 0; inp_u.U.mi.dy = 0
        inp_u.U.mi.mouseData = 0; inp_u.U.mi.dwFlags = u
        inp_u.U.mi.time = 0; inp_u.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp_u), ctypes.sizeof(INPUT))

    def _double_click(button: str = "left") -> None:
        _click(button)
        _click(button)

    def _scroll(delta: int) -> None:
        inp = INPUT(type=INPUT_MOUSE)
        inp.U.mi.dx = 0; inp.U.mi.dy = 0
        inp.U.mi.mouseData = ctypes.c_ulong(delta * 120)
        inp.U.mi.dwFlags = MOUSEEVENTF_WHEEL
        inp.U.mi.time = 0; inp.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _move_relative(dx: int, dy: int) -> None:
        inp = INPUT(type=INPUT_MOUSE)
        inp.U.mi.dx = dx; inp.U.mi.dy = dy
        inp.U.mi.mouseData = 0; inp.U.mi.dwFlags = MOUSEEVENTF_MOVE
        inp.U.mi.time = 0; inp.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

else:
    def _move_to(x: int, y: int) -> None:
        log.debug("鼠标模拟不支持当前平台: %s", sys.platform)

    def _click(button: str = "left") -> None:
        log.debug("鼠标模拟不支持当前平台: %s", sys.platform)

    def _double_click(button: str = "left") -> None:
        log.debug("鼠标模拟不支持当前平台: %s", sys.platform)

    def _scroll(delta: int) -> None:
        log.debug("鼠标模拟不支持当前平台: %s", sys.platform)

    def _move_relative(dx: int, dy: int) -> None:
        log.debug("鼠标模拟不支持当前平台: %s", sys.platform)


class _BaseBackend:
    name: str = "base"

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    @property
    def is_running(self) -> bool:
        raise NotImplementedError
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



if sys.platform == "win32":
    import ctypes.wintypes as wt

    WH_MOUSE_LL = 14

    LLMHF_INJECTED = 0x10
    WM_MOUSEWHEEL = 0x020A
    WM_MOUSEHWHEEL = 0x020E

    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = wt.DWORD
    _kernel32.SetLastError.argtypes = [wt.DWORD]
    _kernel32.SetLastError.restype = None

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", wt.POINT),
            ("mouseData", wt.DWORD),
            ("flags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]
        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self for chaining.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function applied before f
                sub_f: Post-processing function (no return expected)

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


    _ms_pending: Queue = Queue()

    _HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong, ctypes.c_int, wt.WPARAM, wt.LPARAM
    )

    _ms_last_pos: Optional[Tuple[int, int]] = None
    _ms_last_left_down: Optional[Tuple[int, int]] = None

    def _low_level_mouse_proc(nCode: int, wParam: wt.WPARAM, lParam: wt.LPARAM) -> int:
        if nCode < 0:
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        try:
            p = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = p.pt.x, p.pt.y
            mouse_data = p.mouseData
            flags = p.flags

            msg = wParam & 0xFFFFFFFF
            event_type: int
            button: str = "left"
            delta: int = 0

            if msg == 0x0200:
                event_type = MouseEventType.MOVE
                if _ms_last_left_down is not None:
                    event_type = MouseEventType.DRAG
                _ms_last_pos = (x, y)
            elif msg == 0x0201:
                event_type = MouseEventType.LEFT_DOWN
                button = "left"
                _ms_last_left_down = (x, y)
            elif msg == 0x0202:
                event_type = MouseEventType.LEFT_UP
                button = "left"
                _ms_last_left_down = None
            elif msg == 0x0204:
                event_type = MouseEventType.RIGHT_DOWN
                button = "right"
            elif msg == 0x0205:
                event_type = MouseEventType.RIGHT_UP
                button = "right"
            elif msg == 0x0207:
                event_type = MouseEventType.MIDDLE_DOWN
                button = "middle"
            elif msg == 0x0208:
                event_type = MouseEventType.MIDDLE_UP
                button = "middle"
            elif msg == WM_MOUSEWHEEL:
                event_type = MouseEventType.SCROLL
                delta = ctypes.c_short(mouse_data >> 16).value
            elif msg == WM_MOUSEHWHEEL:
                event_type = MouseEventType.SCROLL
                delta = -ctypes.c_short(mouse_data >> 16).value
            else:
                return _user32.CallNextHookEx(None, nCode, wParam, lParam)

            md = MouseData(
                x=x, y=y,
                event_type=event_type,
                button=button,
                delta=delta,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                sequence=next(_seq_counter),
            )

            _ms_pending.put(md)

        except Exception:
            pass

        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    class _Win32MouseBackend(_BaseBackend):
        name = "win32"

        def __init__(
            self,
            on_change: Callable[[MouseData], None],
            interval: float = 0.05,
        ) -> None:
            self._on_change = on_change
            self._interval = interval
            self._thread: Optional[Thread] = None
            self._stop_event = Event()
            self._running = False
            self._lock = Lock()
            self._hook_handle: Optional[int] = None

        @property
        def is_running(self) -> bool:
            return self._running

        def start(self) -> None:
            with self._lock:
                if self._running:
                    return
                self._stop_event.clear()
                self._running = True
                self._thread = Thread(target=self._run, name="vools-mouse-win32", daemon=True)
                self._thread.start()

        def _run(self) -> None:
            try:
                self._hook_handle = _user32.SetWindowsHookExW(
                    WH_MOUSE_LL,
                    _HOOKPROC(_low_level_mouse_proc),
                    None,
                    0,
                )
                log.debug(f'SetWindowsHookExW mouse result: {self._hook_handle}')
                if not self._hook_handle:
                    log.debug("SetWindowsHookExW mouse failed")
                    return

                msg = ctypes.wintypes.MSG()
                while not self._stop_event.is_set():
                    while not _ms_pending.empty():
                        try:
                            md = _ms_pending.get_nowait()
                            self._on_change(md)
                        except Exception:
                            pass

                    ret = _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
                    if ret != 0:
                        _user32.TranslateMessage(ctypes.byref(msg))
                        _user32.DispatchMessageW(ctypes.byref(msg))
                    time.sleep(0.001)

            except Exception as e:
                log.debug("mouse backend exception: %s", e)
            finally:
                self._cleanup()
                self._running = False

        def _cleanup(self) -> None:
            if self._hook_handle:
                try:
                    _user32.UnhookWindowsHookEx(self._hook_handle)
                except Exception:
                    pass
                self._hook_handle = None

        def stop(self) -> None:
            self._stop_event.set()
            local_thread: Optional[Thread] = None
            with self._lock:
                if not self._running:
                    return
                self._running = False
                local_thread = self._thread
            if local_thread and local_thread.is_alive():
                local_thread.join(timeout=max(1.0, self._interval * 5 + 0.5))
            self._cleanup()
        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self for chaining.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function applied before f
                sub_f: Post-processing function (no return expected)

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
        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self for chaining.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function applied before f
                sub_f: Post-processing function (no return expected)

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



else:
    class _Win32MouseBackend(_BaseBackend):
        name = "win32"
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Win32 backend not available on this platform")
        def start(self) -> None: pass
        def stop(self) -> None: pass


class _PollingMouseBackend(_BaseBackend):
    name = "polling"

    def __init__(
        self,
        on_change: Callable[[MouseData], None],
        interval: float = 0.05,
    ) -> None:
        self._on_change = on_change
        self._interval = max(0.01, float(interval))
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._running = False
        self._lock = Lock()
        self._prev_pos: Optional[Tuple[int, int]] = None
        self._prev_left_down = False
        self._prev_right_down = False
        self._prev_middle_down = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._running = True
            self._thread = Thread(target=self._run, name="vools-mouse-polling", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        if sys.platform == "win32":
            pt = ctypes.wintypes.POINT
            _GetCursorPos = _user32.GetCursorPos
            _GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
            _GetCursorPos.restype = ctypes.c_bool
            _GetAsyncKeyState = _user32.GetAsyncKeyState
        else:
            pt = None
            _GetCursorPos = None
            _GetAsyncKeyState = None

        VK_LBUTTON = 0x01
        VK_RBUTTON = 0x02
        VK_MBUTTON = 0x04

        while not self._stop_event.is_set():
            if _GetCursorPos is not None and pt is not None:
                p = pt()
                try:
                    _GetCursorPos(ctypes.byref(p))
                except Exception as e:
                    log.debug("GetCursorPos error: %s", e)
                    time.sleep(self._interval)
                    continue

                x, y = p.x, p.y
                prev_pos = self._prev_pos

                try:
                    left_down = bool(_GetAsyncKeyState(VK_LBUTTON) & 0x8000)
                    right_down = bool(_GetAsyncKeyState(VK_RBUTTON) & 0x8000)
                    middle_down = bool(_GetAsyncKeyState(VK_MBUTTON) & 0x8000)
                except Exception:
                    left_down = right_down = middle_down = False

                if prev_pos is None or prev_pos != (x, y):
                    if prev_pos is not None:
                        if self._prev_left_down:
                            event_type = MouseEventType.DRAG
                        else:
                            event_type = MouseEventType.MOVE
                        md = MouseData(
                            x=x, y=y,
                            event_type=event_type,
                            button="left",
                            timestamp=datetime.datetime.now(datetime.timezone.utc),
                            sequence=next(_seq_counter),
                        )
                        try:
                            self._on_change(md)
                        except Exception as e:
                            log.debug("on_change error: %s", e)
                    self._prev_pos = (x, y)

                if left_down and not self._prev_left_down:
                    md = MouseData(x=x, y=y, event_type=MouseEventType.LEFT_DOWN, button="left",
                                   timestamp=datetime.datetime.now(datetime.timezone.utc),
                                   sequence=next(_seq_counter))
                    try:
                        self._on_change(md)
                    except Exception as e:
                        log.debug("on_change error: %s", e)
                elif not left_down and self._prev_left_down:
                    md = MouseData(x=x, y=y, event_type=MouseEventType.LEFT_UP, button="left",
                                   timestamp=datetime.datetime.now(datetime.timezone.utc),
                                   sequence=next(_seq_counter))
                    try:
                        self._on_change(md)
                    except Exception as e:
                        log.debug("on_change error: %s", e)
                self._prev_left_down = left_down

                if right_down and not self._prev_right_down:
                    md = MouseData(x=x, y=y, event_type=MouseEventType.RIGHT_DOWN, button="right",
                                   timestamp=datetime.datetime.now(datetime.timezone.utc),
                                   sequence=next(_seq_counter))
                    try:
                        self._on_change(md)
                    except Exception as e:
                        log.debug("on_change error: %s", e)
                elif not right_down and self._prev_right_down:
                    md = MouseData(x=x, y=y, event_type=MouseEventType.RIGHT_UP, button="right",
                                   timestamp=datetime.datetime.now(datetime.timezone.utc),
                                   sequence=next(_seq_counter))
                    try:
                        self._on_change(md)
                    except Exception as e:
                        log.debug("on_change error: %s", e)
                self._prev_right_down = right_down

                if middle_down and not self._prev_middle_down:
                    md = MouseData(x=x, y=y, event_type=MouseEventType.MIDDLE_DOWN, button="middle",
                                   timestamp=datetime.datetime.now(datetime.timezone.utc),
                                   sequence=next(_seq_counter))
                    try:
                        self._on_change(md)
                    except Exception as e:
                        log.debug("on_change error: %s", e)
                elif not middle_down and self._prev_middle_down:
                    md = MouseData(x=x, y=y, event_type=MouseEventType.MIDDLE_UP, button="middle",
                                   timestamp=datetime.datetime.now(datetime.timezone.utc),
                                   sequence=next(_seq_counter))
                    try:
                        self._on_change(md)
                    except Exception as e:
                        log.debug("on_change error: %s", e)
                self._prev_middle_down = middle_down

            time.sleep(self._interval)

        self._running = False

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self._interval * 5 + 0.5))
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



class MouseDispatcher:
    def __init__(
        self,
        *,
        backend: str = "auto",
        filter_self: bool = True,
        interval: float = 0.05,
        tags: Tuple[str, ...] = (),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        from vools.reactive.core.subject import Subject
        self._backend_name: str = ""
        self._backend: Optional[_BaseBackend] = None
        self._filter_self = bool(filter_self)
        self._interval = interval
        self._tags = tags
        self._metadata = metadata or {}
        self._subject = Subject[MouseData]()
        self._running = False
        self._lock = Lock()
        self._dispatch_count = 0
        self._error_count = 0
        self._self_filtered_count = 0
        self._pending_sigs: Dict[str, float] = {}

        be = backend
        if be == "auto":
            be = "win32" if sys.platform == "win32" else "polling"
        self._backend_name = be

        if be == "win32" and sys.platform == "win32":
            try:
                self._backend = _Win32MouseBackend(
                    on_change=self._on_change, interval=interval,
                )
            except Exception as e:
                log.debug("win32 mouse backend failed: %s, fallback to polling", e)
                self._backend = _PollingMouseBackend(
                    on_change=self._on_change, interval=interval,
                )
                self._backend_name = "polling"
        elif be == "polling":
            self._backend = _PollingMouseBackend(
                on_change=self._on_change, interval=interval,
            )
        else:
            self._backend = _PollingMouseBackend(
                on_change=self._on_change, interval=interval,
            )
            self._backend_name = "polling"

    @property
    def subject(self) -> "Subject[MouseData]":
        return self._subject

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def dispatch_count(self) -> int:
        return self._dispatch_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def self_filtered_count(self) -> int:
        return self._self_filtered_count

    def _on_change(self, md: MouseData) -> None:
        if self._filter_self:
            sig = _make_mouse_signature(md.x, md.y, md.event_type)
            now = time.monotonic()
            if sig in self._pending_sigs and self._pending_sigs[sig] > now:
                self._self_filtered_count += 1
                return
            expired = [k for k, v in list(self._pending_sigs.items()) if v <= now]
            for k in expired:
                del self._pending_sigs[k]

        self._dispatch_count += 1
        try:
            self._subject.on_next(md)
        except Exception:
            self._error_count += 1
            raise

    def _dispatch_once(self, md: MouseData) -> None:
        self._on_change(md)

    def _register_self_signature(self, md: MouseData) -> None:
        sig = _make_mouse_signature(md.x, md.y, md.event_type)
        self._pending_sigs[sig] = time.monotonic() + MAX_SIGNATURE_AGE

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            if self._backend:
                self._backend.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._backend:
            self._backend.stop()

    def __enter__(self) -> "MouseDispatcher":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    def move_to(self, x: int, y: int) -> "MouseDispatcher":
        _move_to(x, y)
        md = MouseData.now(x=x, y=y, event_type=MouseEventType.MOVE)
        if self._filter_self:
            self._register_self_signature(md)
        return self

    def click(self, button: str = "left") -> "MouseDispatcher":
        _click(button)
        md = MouseData.now(x=0, y=0,
                            event_type=MouseEventType.LEFT_DOWN if button == "left" else MouseEventType.RIGHT_DOWN,
                            button=button)
        if self._filter_self:
            self._register_self_signature(md)
        return self

    def double_click(self, button: str = "left") -> "MouseDispatcher":
        _double_click(button)
        return self

    def scroll(self, delta: int) -> "MouseDispatcher":
        _scroll(delta)
        md = MouseData.now(x=0, y=0, event_type=MouseEventType.SCROLL, delta=delta)
        if self._filter_self:
            self._register_self_signature(md)
        return self

    def move_relative(self, dx: int, dy: int) -> "MouseDispatcher":
        _move_relative(dx, dy)
        return self

    def drag_to(self, x: int, y: int, button: str = "left") -> "MouseDispatcher":
        _move_to(x, y)
        return self

    def press_button(self, button: str = "left") -> "MouseDispatcher":
        if button == "left":
            d = MOUSEEVENTF_LEFTDOWN
        elif button == "right":
            d = MOUSEEVENTF_RIGHTDOWN
        elif button == "middle":
            d = MOUSEEVENTF_MIDDLEDOWN
        else:
            d = MOUSEEVENTF_LEFTDOWN
        inp = INPUT(type=INPUT_MOUSE)
        inp.U.mi.dx = 0; inp.U.mi.dy = 0
        inp.U.mi.mouseData = 0; inp.U.mi.dwFlags = d
        inp.U.mi.time = 0; inp.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return self


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
    def release_button(self, button: str = "left") -> "MouseDispatcher":
        if button == "left":
            u = MOUSEEVENTF_LEFTUP
        elif button == "right":
            u = MOUSEEVENTF_RIGHTUP
        elif button == "middle":
            u = MOUSEEVENTF_MIDDLEUP
        else:
            u = MOUSEEVENTF_LEFTUP
        inp = INPUT(type=INPUT_MOUSE)
        inp.U.mi.dx = 0; inp.U.mi.dy = 0
        inp.U.mi.mouseData = 0; inp.U.mi.dwFlags = u
        inp.U.mi.time = 0; inp.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return self


class MouseSubject(MonitorSubject):
    def __init__(
        self,
        *,
        backend: str = "auto",
        filter_self: bool = True,
        interval: float = 0.05,
        tags: Tuple[str, ...] = (),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._backend = backend
        self._filter_self = filter_self
        self._interval = interval
        self._tags = tags
        self._metadata = metadata
        super().__init__()

    def _create_dispatcher(self) -> "MouseDispatcher":
        return MouseDispatcher(
            backend=self._backend,
            filter_self=self._filter_self,
            interval=self._interval,
            tags=self._tags,
            metadata=self._metadata,
        )

    def _connect_dispatcher(self) -> None:
        self._conn_sub = self._dispatcher.subject.subscribe(
            on_next=self.on_next,
            on_error=self.on_error,
            on_completed=self.on_completed,
        )

    @property
    def dispatcher(self) -> "MouseDispatcher":
        return self._dispatcher

    @property
    def subject(self) -> "Subject[MouseData]":
        return self

    @property
    def backend_name(self) -> str:
        return self._dispatcher.backend_name

    @property
    def dispatch_count(self) -> int:
        return self._dispatcher.dispatch_count

    @property
    def self_filtered_count(self) -> int:
        return self._dispatcher.self_filtered_count

    def move_to(self, x: int, y: int) -> "MouseSubject":
        self._dispatcher.move_to(x, y)
        return self

    def click(self, button: str = "left") -> "MouseSubject":
        self._dispatcher.click(button)
        return self

    def double_click(self, button: str = "left") -> "MouseSubject":
        self._dispatcher.double_click(button)
        return self

    def scroll(self, delta: int) -> "MouseSubject":
        self._dispatcher.scroll(delta)
        return self

    def move_relative(self, dx: int, dy: int) -> "MouseSubject":
        self._dispatcher.move_relative(dx, dy)
        return self

    def drag_to(self, x: int, y: int, button: str = "left") -> "MouseSubject":
        self._dispatcher.drag_to(x, y, button)
        return self

    def press_button(self, button: str = "left") -> "MouseSubject":
        self._dispatcher.press_button(button)
        return self

    def release_button(self, button: str = "left") -> "MouseSubject":
        self._dispatcher.release_button(button)
        return self

    def __enter__(self) -> "MouseSubject":
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


class MouseObserver(MonitorObserver):
    def __init__(
        self,
        *,
        on_move: Optional[Callable[[MouseData], Any]] = None,
        on_click: Optional[Callable[[MouseData], Any]] = None,
        on_scroll: Optional[Callable[[MouseData], Any]] = None,
        on_drag: Optional[Callable[[MouseData], Any]] = None,
        on_any: Optional[Callable[[MouseData], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            on_any=on_any, on_error=on_error, on_completed=on_completed,
        )
        self._on_move = on_move
        self._on_click = on_click
        self._on_scroll = on_scroll
        self._on_drag = on_drag

    def _event_type_of(self, value: Any) -> Any:
        return MouseEventType(value.event_type)

    def _handler_for(self, event_type: Any) -> Optional[Callable[[Any], Any]]:
        if event_type == MouseEventType.MOVE:
            return self._on_move
        if event_type == MouseEventType.SCROLL:
            return self._on_scroll
        if event_type == MouseEventType.DRAG:
            return self._on_drag
        return self._on_click

    def _on_next(self, md: "MouseData") -> None:
        self.on_next(md)

    def __enter__(self) -> "MouseObserver":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.unsubscribe()
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



def from_mouse(
    *,
    backend: str = "auto",
    filter_self: bool = True,
    auto_start: bool = True,
    interval: float = 0.05,
    tags: Tuple[str, ...] = (),
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, MouseDispatcher]:
    disp = MouseDispatcher(
        backend=backend,
        filter_self=filter_self,
        interval=interval,
        tags=tags,
        metadata=metadata,
    )
    if auto_start:
        disp.start()
    return disp.subject, disp


class _WriteMouseOperator:
    def __init__(self, dispatcher: MouseDispatcher) -> None:
        self._dispatcher = dispatcher

    def __call__(self, source: Any) -> Any:
        def on_next(item: Any) -> None:
            if isinstance(item, MouseData):
                if item.event_type == MouseEventType.MOVE:
                    self._dispatcher.move_to(item.x, item.y)
                elif item.event_type == MouseEventType.DRAG:
                    self._dispatcher.drag_to(item.x, item.y, item.button)
                elif item.event_type in (MouseEventType.LEFT_DOWN, MouseEventType.RIGHT_DOWN, MouseEventType.MIDDLE_DOWN):
                    self._dispatcher.press_button(item.button)
                elif item.event_type in (MouseEventType.LEFT_UP, MouseEventType.RIGHT_UP, MouseEventType.MIDDLE_UP):
                    self._dispatcher.release_button(item.button)
                elif item.event_type == MouseEventType.SCROLL:
                    self._dispatcher.scroll(item.delta)
                else:
                    self._dispatcher.click(item.button)
            elif isinstance(item, tuple) and len(item) == 2:
                self._dispatcher.move_to(item[0], item[1])
            elif isinstance(item, dict):
                x = item.get("x", 0)
                y = item.get("y", 0)
                et = item.get("event_type", "move")
                btn = item.get("button", "left")
                if et in ("move", "MOVE", MouseEventType.MOVE):
                    self._dispatcher.move_to(x, y)
                elif et in ("click", "CLICK"):
                    self._dispatcher.click(btn)
                elif et in ("scroll", "SCROLL"):
                    self._dispatcher.scroll(item.get("delta", 1))

        from vools.reactive import operators as _ops
        return source.pipe(
            _ops.map(lambda x: (on_next(x) or x))
        )
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



def write_to_mouse(
    dispatcher: MouseDispatcher,
) -> Callable[[Any], Any]:
    return _WriteMouseOperator(dispatcher)