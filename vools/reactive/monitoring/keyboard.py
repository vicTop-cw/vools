"""
vools/reactive/monitoring/keyboard.py
仅支持 Windows 平台。
"""

import ctypes
import ctypes.wintypes as wt
import datetime
import itertools
import json
import logging
import pickle
import sys
import time
from dataclasses import dataclass, field, asdict
from enum import IntEnum, IntFlag
from typing import (
    Any, Callable, Dict, List, Optional, Tuple,
    Union, TYPE_CHECKING,
)
from threading import Thread, Lock, Event
from collections import defaultdict
from queue import Queue

from .monitor_subject import MonitorSubject
from .monitor_observer import MonitorObserver
__all__ = ['log', 'MAX_SIGNATURE_AGE', 'KeyEventType', 'KeyModifier', 'KeyData', 'KeyboardDispatcher', 'KeySubject', 'KeyObserver', 'from_keyboard', 'write_to_keyboard']

if TYPE_CHECKING:
    from vools.reactive.core.observable import Observable, Observer, Subscription
    from vools.reactive.core.subject import Subject

log = logging.getLogger(__name__)

_seq_counter = itertools.count(1)
MAX_SIGNATURE_AGE = 0.5


class KeyEventType(IntEnum):
    KEY_DOWN = 0
    KEY_UP = 1
    KEY_HOLD = 2
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



class KeyModifier(IntFlag):
    NONE = 0
    SHIFT = 1
    CTRL = 2
    ALT = 4
    WIN = 8
    CAPSLOCK = 16
    CTRL_SHIFT = CTRL | SHIFT
    CTRL_ALT = CTRL | ALT
    ALT_SHIFT = ALT | SHIFT
    ALL = SHIFT | CTRL | ALT | WIN

    def __str__(self) -> str:
        if self == KeyModifier.NONE:
            return "NONE"
        parts = []
        for flag, name in [
            (KeyModifier.SHIFT, "SHIFT"),
            (KeyModifier.CTRL, "CTRL"),
            (KeyModifier.ALT, "ALT"),
            (KeyModifier.WIN, "WIN"),
            (KeyModifier.CAPSLOCK, "CAPSLOCK"),
        ]:
            if self & flag:
                parts.append(name)
        return "+".join(parts) if parts else "NONE"
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



_VK_TO_NAME: Dict[int, str] = {
    0x01: "LBUTTON", 0x02: "RBUTTON", 0x03: "CANCEL",
    0x08: "BACK", 0x09: "TAB", 0x0C: "CLEAR", 0x0D: "ENTER",
    0x10: "SHIFT", 0x11: "CTRL", 0x12: "ALT", 0x13: "PAUSE",
    0x14: "CAPSLOCK", 0x15: "KANA", 0x17: "JUNJA", 0x18: "FINAL",
    0x19: "KANJI", 0x1B: "ESCAPE",
    0x20: "SPACE", 0x21: "PAGEUP", 0x22: "PAGEDOWN", 0x23: "END",
    0x24: "HOME", 0x25: "LEFT", 0x26: "UP", 0x27: "RIGHT",
    0x28: "DOWN", 0x29: "SELECT", 0x2A: "PRINT", 0x2B: "EXECUTE",
    0x2C: "SNAPSHOT", 0x2D: "INSERT", 0x2E: "DELETE", 0x2F: "HELP",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x41: "A", 0x42: "B", 0x43: "C", 0x44: "D", 0x45: "E",
    0x46: "F", 0x47: "G", 0x48: "H", 0x49: "I", 0x4A: "J",
    0x4B: "K", 0x4C: "L", 0x4D: "M", 0x4E: "N", 0x4F: "O",
    0x50: "P", 0x51: "Q", 0x52: "R", 0x53: "S", 0x54: "T",
    0x55: "U", 0x56: "V", 0x57: "W", 0x58: "X", 0x59: "Y",
    0x5A: "Z",
    0x60: "NUMPAD0", 0x61: "NUMPAD1", 0x62: "NUMPAD2", 0x63: "NUMPAD3",
    0x64: "NUMPAD4", 0x65: "NUMPAD5", 0x66: "NUMPAD6", 0x67: "NUMPAD7",
    0x68: "NUMPAD8", 0x69: "NUMPAD9", 0x6A: "MULTIPLY", 0x6B: "ADD",
    0x6C: "SEPARATOR", 0x6D: "SUBTRACT", 0x6E: "DECIMAL", 0x6F: "DIVIDE",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5",
    0x75: "F6", 0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10",
    0x7A: "F11", 0x7B: "F12", 0x7C: "F13", 0x7D: "F14", 0x7E: "F15",
    0x7F: "F16", 0x80: "F17", 0x81: "F18", 0x82: "F19", 0x83: "F20",
    0x84: "F21", 0x85: "F22", 0x86: "F23", 0x87: "F24",
    0x90: "NUMLOCK", 0x91: "SCROLL",
    0xA0: "LSHIFT", 0xA1: "RSHIFT", 0xA2: "LCTRL", 0xA3: "RCTRL",
    0xA4: "LMENU", 0xA5: "RMENU",
}

_NAME_TO_VK: Dict[str, int] = {
    name.lower(): vk for vk, name in _VK_TO_NAME.items()
}
_NAME_TO_VK.update({
    "left button": 0x01, "right button": 0x02,
    "escape": 0x1B, "space": 0x20, " ": 0x20,
    "page up": 0x21, "page down": 0x22,
    "pgup": 0x21, "pgdn": 0x22,
    "left arrow": 0x25, "right arrow": 0x27, "up arrow": 0x26, "down arrow": 0x28,
    "arrowleft": 0x25, "arrowright": 0x27, "arrowup": 0x26, "arrowdown": 0x28,
    "backspace": 0x08, "bs": 0x08,
    "numlock": 0x90, "scrolllock": 0x91,
})


def _vk_code_to_name(vk_code: int) -> str:
    return _VK_TO_NAME.get(vk_code, f"VK{vk_code:02X}")


def _name_to_vk_code(name: str) -> int:
    key = name.strip().lower()
    return _NAME_TO_VK.get(key, 0)


def _make_key_signature(key_code: int, is_press: bool) -> Tuple[int, bool]:
    return (key_code, is_press)


@dataclass
class KeyData:
    """键盘事件数据。

    字段:
        key_code: 按键代码（虚拟键码）
        key_name: 按键名称（如 "A", "SPACE", "ENTER"）
        is_press: 是否为按下事件（True=按下，False=释放）
        modifiers: 修饰键状态（KeyModifier 组合）
        event_type: 事件类型（KeyEventType）
        timestamp: 事件时间戳
        sequence: 全局序号（单调递增）
        window_title: 当时焦点窗口标题
        tags: 用户自定义标签
        metadata: 扩展元信息
    """
    key_code: int = 0
    key_name: str = ""
    is_press: bool = True
    modifiers: int = 0
    event_type: int = KeyEventType.KEY_DOWN
    timestamp: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    sequence: int = 0
    window_title: str = ""
    tags: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type != KeyEventType.KEY_DOWN and not (
            self.event_type == 0 and self.is_press
        ):
            pass
        else:
            object.__setattr__(
                self, 'event_type',
                KeyEventType.KEY_DOWN if self.is_press else KeyEventType.KEY_UP
            )
        if not self.key_name and self.key_code:
            object.__setattr__(self, 'key_name', _vk_code_to_name(self.key_code))
        if self.sequence == 0:
            object.__setattr__(self, 'sequence', next(_seq_counter))

    @classmethod
    def now(
        cls,
        key_code: int,
        is_press: bool = True,
        modifiers: int = KeyModifier.NONE,
        window_title: str = "",
        tags: Tuple[str, ...] = (),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "KeyData":
        return cls(
            key_code=key_code,
            is_press=is_press,
            modifiers=modifiers,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            sequence=next(_seq_counter),
            window_title=window_title,
            tags=tags,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d["timestamp"], datetime.datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KeyData":
        if isinstance(d.get("timestamp"), str):
            d["timestamp"] = datetime.datetime.fromisoformat(d["timestamp"])
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "KeyData":
        return cls.from_dict(json.loads(s))

    def to_pickle(self) -> bytes:
        return pickle.dumps(asdict(self))

    @classmethod
    def from_pickle(cls, data: bytes) -> "KeyData":
        return cls.from_dict(pickle.loads(data))

    def __repr__(self) -> str:
        return (
            f"KeyData(key_name={self.key_name!r}, "
            f"key_code={self.key_code:#04x}, "
            f"event_type={KeyEventType(self.event_type).name!r}, "
            f"modifiers={KeyModifier(self.modifiers)!r}, "
            f"seq={self.sequence})"
        )


if sys.platform == "win32":
    _user32 = ctypes.PyDLL("user32.dll", use_last_error=True)
    _kernel32 = ctypes.PyDLL("kernel32.dll", use_last_error=True)

    ULONG_PTR = ctypes.c_ulonglong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
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
            _fields_ = [("ki", KEYBDINPUT)]

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


    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_EXTENDEDKEY = 0x0001

    _user32.SendInput.argtypes = [ctypes.c_ulong, ctypes.POINTER(INPUT), ctypes.c_int]
    _user32.SendInput.restype = ctypes.c_ulong
    _user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
    _user32.VkKeyScanW.restype = ctypes.c_short
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.CallNextHookEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        wt.WPARAM,
        wt.LPARAM,
    ]
    _user32.CallNextHookEx.restype = ctypes.c_longlong

    def _press_key(vk_code: int) -> None:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.U.ki.wVk = ctypes.c_ushort(vk_code)
        inp.U.ki.wScan = 0
        inp.U.ki.dwFlags = 0
        inp.U.ki.time = 0
        inp.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _release_key(vk_code: int) -> None:
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.U.ki.wVk = ctypes.c_ushort(vk_code)
        inp.U.ki.wScan = 0
        inp.U.ki.dwFlags = KEYEVENTF_KEYUP
        inp.U.ki.time = 0
        inp.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _type_char(ch: str) -> None:
        scan = ord(ch)
        inp_d = INPUT(type=INPUT_KEYBOARD)
        inp_d.U.ki.wVk = 0
        inp_d.U.ki.wScan = ctypes.c_ushort(scan)
        inp_d.U.ki.dwFlags = KEYEVENTF_UNICODE
        inp_d.U.ki.time = 0
        inp_d.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp_d), ctypes.sizeof(INPUT))
        inp_u = INPUT(type=INPUT_KEYBOARD)
        inp_u.U.ki.wVk = 0
        inp_u.U.ki.wScan = ctypes.c_ushort(scan)
        inp_u.U.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inp_u.U.ki.time = 0
        inp_u.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp_u), ctypes.sizeof(INPUT))

    def _press(key: Union[str, int]) -> None:
        if isinstance(key, int):
            vk = key
        else:
            vk = _name_to_vk_code(key)
        if vk:
            _press_key(vk)

    def _release(key: Union[str, int]) -> None:
        if isinstance(key, int):
            vk = key
        else:
            vk = _name_to_vk_code(key)
        if vk:
            _release_key(vk)

    def _type_text(text: str) -> None:
        for ch in text:
            _type_char(ch)

    def _hotkey(*keys: str) -> None:
        vk_list = [_name_to_vk_code(k) for k in keys]
        for vk in vk_list:
            if vk:
                _press_key(vk)
        for vk in reversed(vk_list):
            if vk:
                _release_key(vk)

else:
    def _press(key: Union[str, int]) -> None:
        log.debug("键盘模拟不支持当前平台: %s", sys.platform)

    def _release(key: Union[str, int]) -> None:
        log.debug("键盘模拟不支持当前平台: %s", sys.platform)

    def _type_text(text: str) -> None:
        log.debug("键盘模拟不支持当前平台: %s", sys.platform)

    def _hotkey(*keys: str) -> None:
        log.debug("键盘模拟不支持当前平台: %s", sys.platform)

    def _press_key(vk_code: int) -> None:
        pass

    def _release_key(vk_code: int) -> None:
        pass

    def _type_char(ch: str) -> None:
        pass


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

    WH_KEYBOARD_LL = 13
    LLKHF_EXTENDED = 0x01
    LLKHF_INJECTED = 0x10
    LLKHF_UP = 0x80

    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12
    VK_LWIN = 0x5B
    VK_CAPITAL = 0x14

    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = wt.DWORD
    _kernel32.SetLastError.argtypes = [wt.DWORD]
    _kernel32.SetLastError.restype = None

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wt.DWORD),
            ("scanCode", wt.DWORD),
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


    _kb_pending: Queue = Queue()

    _HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong, ctypes.c_int, wt.WPARAM, wt.LPARAM
    )

    def _get_modifiers() -> int:
        mods = 0
        if _user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
            mods |= KeyModifier.SHIFT
        if _user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
            mods |= KeyModifier.CTRL
        if _user32.GetAsyncKeyState(VK_MENU) & 0x8000:
            mods |= KeyModifier.ALT
        if _user32.GetAsyncKeyState(VK_LWIN) & 0x8000:
            mods |= KeyModifier.WIN
        if _user32.GetAsyncKeyState(VK_CAPITAL) & 0x0001:
            mods |= KeyModifier.CAPSLOCK
        return mods

    def _get_window_title() -> str:
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = _user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(length)
            _user32.GetWindowTextW(hwnd, buf, length)
            return buf.value or ""
        except Exception:
            return ""

    _kb_last_key_state: Dict[int, bool] = {}

    def _low_level_keyboard_proc(nCode: int, wParam: wt.WPARAM, lParam: wt.LPARAM) -> int:
        log.debug(f"Keyboard hook called: nCode={nCode}, wParam={wParam}, lParam={lParam}")
        if nCode < 0:
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        try:
            p = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = p.vkCode
            flags = p.flags
            is_up = bool(flags & LLKHF_UP)
            log.debug(f"Keyboard hook: vk=0x{vk:02X}, is_up={is_up}, flags={flags}")

            was_down = _kb_last_key_state.get(vk, False)
            if not was_down and not is_up:
                event_type = KeyEventType.KEY_DOWN
            elif was_down and is_up:
                event_type = KeyEventType.KEY_UP
            else:
                log.debug(f"Keyboard hook: skipping (was_down={was_down}, is_up={is_up})")
                return _user32.CallNextHookEx(None, nCode, wParam, lParam)

            _kb_last_key_state[vk] = not is_up

            key_name = _vk_code_to_name(vk)
            mods = _get_modifiers()
            title = _get_window_title()

            kd = KeyData(
                key_code=vk,
                key_name=key_name,
                is_press=(event_type == KeyEventType.KEY_DOWN),
                modifiers=mods,
                event_type=event_type,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                sequence=next(_seq_counter),
                window_title=title,
            )

            _kb_pending.put(kd)
            log.debug(f"Keyboard hook captured: {KeyEventType(event_type).name} - {key_name} (0x{vk:02X})")

        except Exception as ex:
            log.debug(f"Keyboard hook error: {ex}")

        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    class _Win32KeyboardBackend(_BaseBackend):
        name = "win32"

        def __init__(
            self,
            on_change: Callable[[KeyData], None],
            interval: float = 0.05,
        ) -> None:
            self._on_change = on_change
            self._interval = interval
            self._thread: Optional[Thread] = None
            self._stop_event = Event()
            self._running = False
            self._lock = Lock()
            self._hook_handle: Optional[int] = None
            self._hook_proc = None

        @property
        def is_running(self) -> bool:
            return self._running

        def start(self) -> None:
            with self._lock:
                if self._running:
                    return
                self._stop_event.clear()
                self._running = True
                self._thread = Thread(target=self._run, name="vools-keyboard-win32", daemon=True)
                self._thread.start()

        def _run(self) -> None:
            try:
                self._hook_proc = _HOOKPROC(_low_level_keyboard_proc)
                self._hook_handle = _user32.SetWindowsHookExW(
                    WH_KEYBOARD_LL,
                    self._hook_proc,
                    None,
                    0,
                )
                log.debug(f'SetWindowsHookExW keyboard result: {self._hook_handle}')
                if not self._hook_handle:
                    log.debug("SetWindowsHookExW keyboard failed")
                    return

                msg = ctypes.wintypes.MSG()
                msg_count = 0
                while not self._stop_event.is_set():
                    while not _kb_pending.empty():
                        try:
                            kd = _kb_pending.get_nowait()
                            self._on_change(kd)
                        except Exception:
                            pass

                    ret = _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
                    if ret != 0:
                        msg_count += 1
                        if msg_count % 100 == 0:
                            log.debug(f'Message loop processed {msg_count} messages')
                        _user32.TranslateMessage(ctypes.byref(msg))
                        _user32.DispatchMessageW(ctypes.byref(msg))
                    time.sleep(0.005)

            except Exception as e:
                log.debug("keyboard backend exception: %s", e)
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
    class _Win32KeyboardBackend(_BaseBackend):
        name = "win32"
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Win32 backend not available on this platform")
        def start(self) -> None: pass
        def stop(self) -> None: pass


class _PollingKeyboardBackend(_BaseBackend):
    name = "polling"

    def __init__(
        self,
        on_change: Callable[[KeyData], None],
        interval: float = 0.05,
    ) -> None:
        self._on_change = on_change
        self._interval = max(0.01, float(interval))
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._running = False
        self._lock = Lock()
        self._prev_state: Dict[int, bool] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._running = True
            self._thread = Thread(target=self._run, name="vools-keyboard-polling", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        if sys.platform == "win32":
            _GetAsyncKeyState = _user32.GetAsyncKeyState
        else:
            _GetAsyncKeyState = None

        while not self._stop_event.is_set():
            if _GetAsyncKeyState is not None:
                for vk in range(256):
                    try:
                        state = _GetAsyncKeyState(vk) & 0x8000
                    except Exception:
                        continue
                    is_down = bool(state)
                    prev = self._prev_state.get(vk, False)
                    if is_down and not prev:
                        key_name = _vk_code_to_name(vk)
                        mods = 0
                        for mod_vk, mod_flag in [
                            (VK_SHIFT, KeyModifier.SHIFT),
                            (VK_CONTROL, KeyModifier.CTRL),
                            (VK_MENU, KeyModifier.ALT),
                        ]:
                            try:
                                if _GetAsyncKeyState(mod_vk) & 0x8000:
                                    mods |= mod_flag
                            except Exception:
                                pass
                        kd = KeyData(
                            key_code=vk,
                            key_name=key_name,
                            is_press=True,
                            modifiers=mods,
                            event_type=KeyEventType.KEY_DOWN,
                            timestamp=datetime.datetime.now(datetime.timezone.utc),
                            sequence=next(_seq_counter),
                            window_title="",
                        )
                        try:
                            self._on_change(kd)
                        except Exception as e:
                            log.debug("on_change error: %s", e)
                    elif not is_down and prev:
                        key_name = _vk_code_to_name(vk)
                        kd = KeyData(
                            key_code=vk,
                            key_name=key_name,
                            is_press=False,
                            modifiers=0,
                            event_type=KeyEventType.KEY_UP,
                            timestamp=datetime.datetime.now(datetime.timezone.utc),
                            sequence=next(_seq_counter),
                            window_title="",
                        )
                        try:
                            self._on_change(kd)
                        except Exception as e:
                            log.debug("on_change error: %s", e)
                    self._prev_state[vk] = is_down
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



class KeyboardDispatcher:
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
        self._subject = Subject[KeyData]()
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
                self._backend = _Win32KeyboardBackend(
                    on_change=self._on_change, interval=interval,
                )
            except Exception as e:
                log.debug("win32 keyboard backend failed: %s, fallback to polling", e)
                self._backend = _PollingKeyboardBackend(
                    on_change=self._on_change, interval=interval,
                )
                self._backend_name = "polling"
        elif be == "polling":
            self._backend = _PollingKeyboardBackend(
                on_change=self._on_change, interval=interval,
            )
        else:
            self._backend = _PollingKeyboardBackend(
                on_change=self._on_change, interval=interval,
            )
            self._backend_name = "polling"

    @property
    def subject(self) -> "Subject[KeyData]":
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

    def _on_change(self, kd: KeyData) -> None:
        if self._filter_self:
            sig = _make_key_signature(kd.key_code, kd.is_press)
            now = time.monotonic()
            if sig in self._pending_sigs and self._pending_sigs[sig] > now:
                self._self_filtered_count += 1
                return
            expired = [k for k, v in list(self._pending_sigs.items()) if v <= now]
            for k in expired:
                del self._pending_sigs[k]

        self._dispatch_count += 1
        try:
            self._subject.on_next(kd)
        except Exception:
            self._error_count += 1
            raise

    def _dispatch_once(self, kd: KeyData) -> None:
        self._on_change(kd)

    def _register_self_signature(self, kd: KeyData) -> None:
        sig = _make_key_signature(kd.key_code, kd.is_press)
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

    def __enter__(self) -> "KeyboardDispatcher":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    def press(self, key: Union[str, int]) -> "KeyboardDispatcher":
        kd = KeyData.now(key_code=_name_to_vk_code(key) if isinstance(key, str) else key,
                          is_press=True)
        if self._filter_self:
            self._register_self_signature(kd)
        _press(key)
        return self

    def release(self, key: Union[str, int]) -> "KeyboardDispatcher":
        _release(key)
        kd = KeyData.now(key_code=_name_to_vk_code(key) if isinstance(key, str) else key,
                          is_press=False)
        if self._filter_self:
            self._register_self_signature(kd)
        return self

    def tap(self, key: Union[str, int]) -> "KeyboardDispatcher":
        self.press(key).release(key)
        return self

    def type_text(self, text: str) -> "KeyboardDispatcher":
        _type_text(text)
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
    def hotkey(self, *keys: str) -> "KeyboardDispatcher":
        _hotkey(*keys)
        return self


class KeySubject(MonitorSubject):
    """键盘事件主题（Subject），继承 MonitorSubject。

    内部持有 KeyboardDispatcher，提供键盘事件流。

    方法:
        press(key): 模拟按下按键
        release(key): 模拟释放按键
        tap(key): 模拟一次按键（按下+释放）
        type_text(text): 模拟输入文本
        hotkey(*keys): 模拟组合键
    """
    def __init__(
        self,
        *,
        backend: str = "auto",
        filter_self: bool = True,
        interval: float = 0.05,
        tags: Tuple[str, ...] = (),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化键盘监控主题。

        Args:
            backend: 后端类型，"auto" | "win32" | "polling"
            filter_self: 是否过滤自模拟的键盘事件
            interval: 轮询间隔（秒）
            tags: 默认附加的标签
            metadata: 默认元数据
        """
        self._backend = backend
        self._filter_self = filter_self
        self._interval = interval
        self._tags = tags
        self._metadata = metadata
        super().__init__()

    def _create_dispatcher(self) -> "KeyboardDispatcher":
        return KeyboardDispatcher(
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
    def dispatcher(self) -> "KeyboardDispatcher":
        return self._dispatcher

    @property
    def subject(self) -> "Subject[KeyData]":
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

    def press(self, key: Union[str, int]) -> "KeySubject":
        self._dispatcher.press(key)
        return self

    def release(self, key: Union[str, int]) -> "KeySubject":
        self._dispatcher.release(key)
        return self

    def tap(self, key: Union[str, int]) -> "KeySubject":
        self._dispatcher.tap(key)
        return self

    def type_text(self, text: str) -> "KeySubject":
        self._dispatcher.type_text(text)
        return self

    def hotkey(self, *keys: str) -> "KeySubject":
        self._dispatcher.hotkey(*keys)
        return self

    def __enter__(self) -> "KeySubject":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
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



class KeyObserver(MonitorObserver):
    def __init__(
        self,
        *,
        on_press: Optional[Callable[[KeyData], Any]] = None,
        on_release: Optional[Callable[[KeyData], Any]] = None,
        on_hold: Optional[Callable[[KeyData], Any]] = None,
        on_any: Optional[Callable[[KeyData], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            on_any=on_any, on_error=on_error, on_completed=on_completed,
        )
        self._on_press = on_press
        self._on_release = on_release
        self._on_hold = on_hold

    def _event_type_of(self, value: Any) -> Any:
        return KeyEventType(value.event_type)

    def _handler_for(self, event_type: Any) -> Optional[Callable[[Any], Any]]:
        if event_type == KeyEventType.KEY_DOWN:
            return self._on_press
        if event_type == KeyEventType.KEY_UP:
            return self._on_release
        if event_type == KeyEventType.KEY_HOLD:
            return self._on_hold
        return None

    def _on_next(self, kd: "KeyData") -> None:
        self.on_next(kd)

    def __enter__(self) -> "KeyObserver":
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
    def __exit__(self, exc_type, exc, tb) -> None:
        self.unsubscribe()


def from_keyboard(
    *,
    backend: str = "auto",
    filter_self: bool = True,
    auto_start: bool = True,
    interval: float = 0.05,
    tags: Tuple[str, ...] = (),
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, KeyboardDispatcher]:
    disp = KeyboardDispatcher(
        backend=backend,
        filter_self=filter_self,
        interval=interval,
        tags=tags,
        metadata=metadata,
    )
    if auto_start:
        disp.start()
    return disp.subject, disp


class _WriteKeyboardOperator:
    def __init__(self, dispatcher: KeyboardDispatcher) -> None:
        self._dispatcher = dispatcher

    def __call__(self, source: Any) -> Any:
        def on_next(item: Any) -> None:
            if isinstance(item, KeyData):
                if item.is_press:
                    self._dispatcher.press(item.key_code)
                else:
                    self._dispatcher.release(item.key_code)
            elif isinstance(item, str):
                self._dispatcher.type_text(item)
            elif isinstance(item, int):
                self._dispatcher.tap(item)
            elif isinstance(item, dict):
                key = item.get("key") or item.get("key_name", "A")
                is_press = item.get("is_press", True)
                if is_press:
                    self._dispatcher.press(key)
                else:
                    self._dispatcher.release(key)

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



def write_to_keyboard(
    dispatcher: KeyboardDispatcher,
) -> Callable[[Any], Any]:
    return _WriteKeyboardOperator(dispatcher)