"""
keyboard_mouse - Keyboard and Mouse input monitoring and simulation.
"""
from __future__ import annotations

import ctypes
import datetime
import itertools
import json
import logging
import pickle
import struct
import sys
import time
import weakref
from dataclasses import dataclass, field, asdict
from enum import IntEnum, IntFlag
from typing import (
    Any, Callable, Dict, List, Optional, Tuple,
    Union, TYPE_CHECKING,
)
from threading import Thread, Lock, Event
from collections import defaultdict

if TYPE_CHECKING:
    from vools.reactive.observable import Observable, Subject
    from vools.reactive.observer import Observer, Subscription

log = logging.getLogger(__name__)

# ── 全局序列号计数器 ──────────────────────────────────────────────
_seq_counter = itertools.count(1)
MAX_SIGNATURE_AGE = 0.5  # 自我过滤签名有效期（秒）

# ══════════════════════════════════════════════════════════════════
#   枚举：事件类型 & 修饰键
# ══════════════════════════════════════════════════════════════════


class KeyEventType(IntEnum):
    """键盘事件类型。"""
    KEY_DOWN = 0
    KEY_UP = 1
    KEY_HOLD = 2


class MouseEventType(IntEnum):
    """鼠标事件类型。"""
    MOVE = 0
    LEFT_DOWN = 1
    LEFT_UP = 2
    RIGHT_DOWN = 3
    RIGHT_UP = 4
    MIDDLE_DOWN = 5
    MIDDLE_UP = 6
    SCROLL = 7
    DRAG = 8


class KeyModifier(IntFlag):
    """键盘修饰键位标志（可组合）。"""
    NONE = 0
    SHIFT = 1          # 0x01
    CTRL = 2           # 0x02
    ALT = 4            # 0x04
    WIN = 8            # 0x08
    CAPSLOCK = 16      # 0x10
    # 常用组合
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


# ══════════════════════════════════════════════════════════════════
#   键码映射
# ══════════════════════════════════════════════════════════════════

# Windows VK_CODE → 可读名称
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
    # 数字键
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    # 字母键
    0x41: "A", 0x42: "B", 0x43: "C", 0x44: "D", 0x45: "E",
    0x46: "F", 0x47: "G", 0x48: "H", 0x49: "I", 0x4A: "J",
    0x4B: "K", 0x4C: "L", 0x4D: "M", 0x4E: "N", 0x4F: "O",
    0x50: "P", 0x51: "Q", 0x52: "R", 0x53: "S", 0x54: "T",
    0x55: "U", 0x56: "V", 0x57: "W", 0x58: "X", 0x59: "Y",
    0x5A: "Z",
    # 功能键
    0x60: "NUMPAD0", 0x61: "NUMPAD1", 0x62: "NUMPAD2", 0x63: "NUMPAD3",
    0x64: "NUMPAD4", 0x65: "NUMPAD5", 0x66: "NUMPAD6", 0x67: "NUMPAD7",
    0x68: "NUMPAD8", 0x69: "NUMPAD9", 0x6A: "MULTIPLY", 0x6B: "ADD",
    0x6C: "SEPARATOR", 0x6D: "SUBTRACT", 0x6E: "DECIMAL", 0x6F: "DIVIDE",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5",
    0x75: "F6", 0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10",
    0x7A: "F11", 0x7B: "F12", 0x7C: "F13", 0x7D: "F14", 0x7E: "F15",
    0x7F: "F16", 0x80: "F17", 0x81: "F18", 0x82: "F19", 0x83: "F20",
    0x84: "F21", 0x85: "F22", 0x86: "F23", 0x87: "F24",
    # 其他
    0x90: "NUMLOCK", 0x91: "SCROLL",
    0xA0: "LSHIFT", 0xA1: "RSHIFT", 0xA2: "LCTRL", 0xA3: "RCTRL",
    0xA4: "LMENU", 0xA5: "RMENU",
}

# 名称 → VK_CODE（统一小写后匹配）
_NAME_TO_VK: Dict[str, int] = {
    name.lower(): vk for vk, name in _VK_TO_NAME.items()
}
# 别名
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
    """将 Windows VK_CODE 转换为可读名称。"""
    return _VK_TO_NAME.get(vk_code, f"VK{vk_code:02X}")


def _name_to_vk_code(name: str) -> int:
    """将可读名称转换为 Windows VK_CODE，未知返回 0。"""
    key = name.strip().lower()
    return _NAME_TO_VK.get(key, 0)


# ══════════════════════════════════════════════════════════════════
#   签名（自我过滤用）
# ══════════════════════════════════════════════════════════════════

def _make_key_signature(key_code: int, is_press: bool) -> Tuple[int, bool]:
    return (key_code, is_press)


def _make_mouse_signature(x: int, y: int, event_type: int) -> Tuple[int, int, int]:
    return (x, y, event_type)


# ══════════════════════════════════════════════════════════════════
#   KeyData
# ══════════════════════════════════════════════════════════════════


@dataclass
class KeyData:
    """
    键盘事件数据。

    Attributes:
        key_code: Windows VK_CODE (0-255)。
        key_name: 可读键名（如 "A", "ENTER", "F1"）。
        is_press: True = 按下, False = 释放。
        modifiers: 修饰键状态（KeyModifier 位标志）。
        event_type: 事件类型（KeyEventType），从 is_press 自动推导。
        timestamp: UTC 时间戳（datetime）。
        sequence: 全局递增序号。
        window_title: 事件发生时前台窗口标题。
        tags: 自定义标签元组。
        metadata: 自定义扩展字典。
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
        # 自动推导 event_type: 优先尊重显式传入的值，否则根据 is_press 推断
        if self.event_type != KeyEventType.KEY_DOWN and not (
            self.event_type == 0 and self.is_press
        ):
            pass  # event_type 已被显式设置
        else:
            object.__setattr__(
                self, 'event_type',
                KeyEventType.KEY_DOWN if self.is_press else KeyEventType.KEY_UP
            )
        # 自动填充 key_name
        if not self.key_name and self.key_code:
            object.__setattr__(self, 'key_name', _vk_code_to_name(self.key_code))
        # 自动填充 sequence
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
        """工厂方法：创建带自动填充时间的 KeyData。"""
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
        """转换为普通字典（用于 JSON / pickle）。"""
        d = asdict(self)
        # datetime → ISO string
        if isinstance(d["timestamp"], datetime.datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KeyData":
        """从普通字典恢复。"""
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


# ══════════════════════════════════════════════════════════════════
#   MouseData
# ══════════════════════════════════════════════════════════════════


@dataclass
class MouseData:
    """
    鼠标事件数据。

    Attributes:
        x: 绝对 X 坐标（屏幕像素）。
        y: 绝对 Y 坐标（屏幕像素）。
        event_type: 事件类型（MouseEventType）。
        button: 触发按钮名（"left"/"right"/"middle"），从 event_type 自动推导。
        delta: 滚轮增量（SCROLL 时有效，正=向前）。
        timestamp: UTC 时间戳。
        sequence: 全局递增序号。
        tags: 自定义标签元组。
        metadata: 自定义扩展字典。
    """
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
        # 自动推导 button（仅当 button 未被显式设置时，即为空字符串）
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
        # 自动填充 sequence
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
        """工厂方法：创建带自动填充时间的 MouseData。"""
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


# ══════════════════════════════════════════════════════════════════
#   键盘/鼠标模拟 I/O（Windows SendInput / 非 Windows 空实现）
# ══════════════════════════════════════════════════════════════════

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    # ── ctypes 类型定义 ────────────────────────────────────────────
    ULONG_PTR = ctypes.c_ulonglong
    LPDWORD = ctypes.POINTER(ctypes.c_ulong)

    # INPUT 结构体
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class UNION_INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("U", UNION_INPUT)]

    INPUT_KEYBOARD = 1
    INPUT_MOUSE = 0

    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_EXTENDEDKEY = 0x0001

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

    # SendInput 原型
    _user32.SendInput.argtypes = [ctypes.c_ulong, ctypes.POINTER(INPUT), ctypes.c_int]
    _user32.SendInput.restype = ctypes.c_ulong
    _user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
    _user32.VkKeyScanW.restype = ctypes.c_short
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.SetCursorPos.argtypes = [ctypes.POINTER(ctypes.c_long)]
    _user32.SetCursorPos.restype = ctypes.c_bool
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.c_long)]
    _user32.GetCursorPos.restype = ctypes.c_bool
    _user32.mouse_event.argtypes = [ctypes.c_ulong] * 5
    _user32.mouse_event.restype = None

    def _get_screen_size() -> Tuple[int, int]:
        """获取屏幕分辨率。"""
        try:
            w = _user32.GetSystemMetrics(0)  # SM_CXSCREEN
            h = _user32.GetSystemMetrics(1)   # SM_CYSCREEN
            return w, h
        except Exception:
            return 1920, 1080

    # ── 键盘模拟 ───────────────────────────────────────────────────

    def _press_key(vk_code: int) -> None:
        """按下指定虚拟键码。"""
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.U.ki.wVk = ctypes.c_ushort(vk_code)
        inp.U.ki.wScan = 0
        inp.U.ki.dwFlags = 0
        inp.U.ki.time = 0
        inp.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _release_key(vk_code: int) -> None:
        """释放指定虚拟键码。"""
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.U.ki.wVk = ctypes.c_ushort(vk_code)
        inp.U.ki.wScan = 0
        inp.U.ki.dwFlags = KEYEVENTF_KEYUP
        inp.U.ki.time = 0
        inp.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _type_char(ch: str) -> None:
        """模拟输入单个字符（Unicode）。"""
        scan = ord(ch)
        # Key down
        inp_d = INPUT(type=INPUT_KEYBOARD)
        inp_d.U.ki.wVk = 0
        inp_d.U.ki.wScan = ctypes.c_ushort(scan)
        inp_d.U.ki.dwFlags = KEYEVENTF_UNICODE
        inp_d.U.ki.time = 0
        inp_d.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp_d), ctypes.sizeof(INPUT))
        # Key up
        inp_u = INPUT(type=INPUT_KEYBOARD)
        inp_u.U.ki.wVk = 0
        inp_u.U.ki.wScan = ctypes.c_ushort(scan)
        inp_u.U.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        inp_u.U.ki.time = 0
        inp_u.U.ki.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp_u), ctypes.sizeof(INPUT))

    # ── 鼠标模拟 ───────────────────────────────────────────────────

    def _move_to(x: int, y: int) -> None:
        """移动鼠标到绝对坐标（屏幕像素）。"""
        w, h = _get_screen_size()
        # 归一化到 (0..65535)
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
        """点击指定鼠标按钮。"""
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
        """滚轮滚动。delta > 0 向前（远离用户），< 0 向后。"""
        inp = INPUT(type=INPUT_MOUSE)
        inp.U.mi.dx = 0; inp.U.mi.dy = 0
        inp.U.mi.mouseData = ctypes.c_ulong(delta * 120)
        inp.U.mi.dwFlags = MOUSEEVENTF_WHEEL
        inp.U.mi.time = 0; inp.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _move_relative(dx: int, dy: int) -> None:
        """相对移动鼠标（屏幕像素）。"""
        inp = INPUT(type=INPUT_MOUSE)
        inp.U.mi.dx = dx; inp.U.mi.dy = dy
        inp.U.mi.mouseData = 0; inp.U.mi.dwFlags = MOUSEEVENTF_MOVE
        inp.U.mi.time = 0; inp.U.mi.dwExtraInfo = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _press(key: Union[str, int]) -> None:
        """Python 入口：按下键（支持名称或 VK code）。"""
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
        """模拟输入一串文本（Unicode）。"""
        for ch in text:
            _type_char(ch)

    def _hotkey(*keys: str) -> None:
        """热键：依次按下所有键，然后依次释放。"""
        vk_list = [_name_to_vk_code(k) for k in keys]
        for vk in vk_list:
            if vk:
                _press_key(vk)
        for vk in reversed(vk_list):
            if vk:
                _release_key(vk)

else:
    # 非 Windows 平台：空实现
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

# ══════════════════════════════════════════════════════════════════
#   后端基类
# ══════════════════════════════════════════════════════════════════


class _BaseBackend:
    """所有后端的公共接口。"""

    name: str = "base"

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    @property
    def is_running(self) -> bool:
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════
#   Windows Hook 后端（键盘 + 鼠标）
# ══════════════════════════════════════════════════════════════════

if sys.platform == "win32":

    # ── 隐藏窗口 + 消息循环（用于接收 Hook 回调） ──────────────────

    import ctypes.wintypes as wt

    # 窗口类名
    _KM_WINDOW_CLASS = "vools_km_cls"

    # 消息类型
    WM_USER = 0x0400
    WM_KEYBOARD_EVENT = WM_USER + 1
    WM_MOUSE_EVENT = WM_USER + 2

    # Hook 类型
    WH_KEYBOARD_LL = 13
    WH_MOUSE_LL = 14

    # 键盘事件标志
    LLKHF_EXTENDED = 0x01
    LLKHF_INJECTED = 0x10
    LLKHF_UP = 0x80

    # 鼠标事件标志
    LLMHF_INJECTED = 0x10
    WM_XBUTTONDOWN = 0x020B
    WM_XBUTTONUP = 0x020C
    WM_MOUSEWHEEL = 0x020A
    WM_MOUSEHWHEEL = 0x020E
    XBUTTON1 = 0x0001
    XBUTTON2 = 0x0002

    # 键盘修饰键
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12    # ALT
    VK_LSHIFT = 0xA0
    VK_RSHIFT = 0xA1
    VK_LCONTROL = 0xA2
    VK_RCONTROL = 0xA3
    VK_LMENU = 0xA4   # LEFT ALT
    VK_RMENU = 0xA5   # RIGHT ALT

    # GetLastError / SetLastError
    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = wt.DWORD
    _kernel32.SetLastError.argtypes = [wt.DWORD]
    _kernel32.SetLastError.restype = None

    # ── KBDLLHOOKSTRUCT ─────────────────────────────────────────────
    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wt.DWORD),
            ("scanCode", wt.DWORD),
            ("flags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    # ── MSLLHOOKSTRUCT ─────────────────────────────────────────────
    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", wt.POINT),
            ("mouseData", wt.DWORD),
            ("flags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    # ── 窗口过程（使用全局变量存储回调）─────────────────────────────

    _km_wndproc_map: Dict[int, Callable[[int, int, int], int]] = {}
    _km_hwnd_to_kb_callback: Dict[int, Callable[["KeyData"], None]] = {}
    _km_hwnd_to_ms_callback: Dict[int, Callable[["MouseData"], None]] = {}

    def _km_wndproc_wrapper(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """窗口过程，处理自定义消息。"""
        if msg == WM_KEYBOARD_EVENT:
            cb = _km_hwnd_to_kb_callback.get(hwnd)
            if cb:
                data = ctypes.cast(lparam, ctypes.POINTER(KeyData)).contents
                cb(data)
            return 0
        elif msg == WM_MOUSE_EVENT:
            cb = _km_hwnd_to_ms_callback.get(hwnd)
            if cb:
                data = ctypes.cast(lparam, ctypes.POINTER(MouseData)).contents
                cb(data)
            return 0
        else:
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ctypes 转换
    _WNDPROC = ctypes.WINFUNCTYPE(
        wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM
    )
    _km_wndproc_cfunc = _WNDPROC(_km_wndproc_wrapper)

    GWLP_WNDPROC = -4
    GWL_STYLE = -16
    WS_DISABLED = 0x08000000

    def _get_modifiers() -> int:
        """获取当前修饰键状态。"""
        mods = 0
        if _user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
            mods |= KeyModifier.SHIFT
        if _user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
            mods |= KeyModifier.CTRL
        if _user32.GetAsyncKeyState(VK_MENU) & 0x8000:
            mods |= KeyModifier.ALT
        if _user32.GetAsyncKeyState(VK_LWIN) & 0x8000 or _user32.GetAsyncKeyState(0x5B) & 0x8000:
            mods |= KeyModifier.WIN
        if _user32.GetAsyncKeyState(VK_CAPITAL) & 0x0001:
            mods |= KeyModifier.CAPSLOCK
        return mods

    def _get_window_title() -> str:
        """获取前台窗口标题。"""
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

    # ── 键盘 Hook 回调 ──────────────────────────────────────────────

    _kb_last_key_state: Dict[int, bool] = {}  # vk_code -> 是否处于按下状态

    def _low_level_keyboard_proc(nCode: int, wParam: int, lParam: int) -> int:
        """LowLevelKeyboardProc 回调。"""
        if nCode < 0:
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        p = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = p.vkCode
        flags = p.flags

        is_injected = bool(flags & LLKHF_INJECTED)
        is_extended = bool(flags & LLKHF_EXTENDED)
        is_up = bool(flags & LLKHF_UP)

        # 判断按下/释放
        was_down = _kb_last_key_state.get(vk, False)
        if not was_down and not is_up:
            event_type = KeyEventType.KEY_DOWN
        elif was_down and is_up:
            event_type = KeyEventType.KEY_UP
        else:
            # 忽略重复的 KEY_DOWN 或系统重复的 KEY_UP
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        _kb_last_key_state[vk] = not is_up

        if is_injected:
            # 跳过注入事件（来自我们自己的 SendInput）
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

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

        # 广播给所有注册了键盘回调的窗口
        for hwnd, cb in list(_km_hwnd_to_kb_callback.items()):
            try:
                # 用 WM_COPYDATA 或直接 PostMessage 传 KeyData
                # 这里用 WM_COPYDATA 更安全
                pData = ctypes.byref(kd)
                _user32.PostMessageW(hwnd, WM_KEYBOARD_EVENT, 0, ctypes.cast(pData, wt.LPARAM))
            except Exception:
                pass

        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    # ── 鼠标 Hook 回调 ─────────────────────────────────────────────

    _ms_last_pos: Optional[Tuple[int, int]] = None
    _ms_last_left_down: Optional[Tuple[int, int]] = None

    def _low_level_mouse_proc(nCode: int, wParam: int, lParam: int) -> int:
        """LowLevelMouseProc 回调。"""
        if nCode < 0:
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        p = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        x, y = p.pt.x, p.pt.y
        mouse_data = p.mouseData
        flags = p.flags
        is_injected = bool(flags & LLMHF_INJECTED)

        if is_injected:
            return _user32.CallNextHookEx(None, nCode, wParam, lParam)

        # 解析消息类型
        msg = wParam & 0xFFFFFFFF  # 确保是 32 位
        event_type: int
        button: str = "left"
        delta: int = 0

        if msg == 0x0200:  # WM_MOUSEMOVE
            global _ms_last_pos, _ms_last_left_down
            event_type = MouseEventType.MOVE
            if _ms_last_left_down is not None:
                event_type = MouseEventType.DRAG
            _ms_last_pos = (x, y)
        elif msg == 0x0201:  # WM_LBUTTONDOWN
            event_type = MouseEventType.LEFT_DOWN
            button = "left"
            _ms_last_left_down = (x, y)
        elif msg == 0x0202:  # WM_LBUTTONUP
            event_type = MouseEventType.LEFT_UP
            button = "left"
            _ms_last_left_down = None
        elif msg == 0x0204:  # WM_RBUTTONDOWN
            event_type = MouseEventType.RIGHT_DOWN
            button = "right"
        elif msg == 0x0205:  # WM_RBUTTONUP
            event_type = MouseEventType.RIGHT_UP
            button = "right"
        elif msg == 0x0207:  # WM_MBUTTONDOWN
            event_type = MouseEventType.MIDDLE_DOWN
            button = "middle"
        elif msg == 0x0208:  # WM_MBUTTONUP
            event_type = MouseEventType.MIDDLE_UP
            button = "middle"
        elif msg == WM_MOUSEWHEEL:
            event_type = MouseEventType.SCROLL
            delta = ctypes.c_short(mouse_data >> 16).value
        elif msg == WM_MOUSEHWHEEL:
            event_type = MouseEventType.SCROLL
            delta = -ctypes.c_short(mouse_data >> 16).value
        elif msg == WM_XBUTTONDOWN:
            event_type = MouseEventType.LEFT_DOWN
            button = "xbutton1" if (mouse_data & 0xFF == XBUTTON1) else "xbutton2"
        elif msg == WM_XBUTTONUP:
            event_type = MouseEventType.LEFT_UP
            button = "xbutton1" if (mouse_data & 0xFF == XBUTTON1) else "xbutton2"
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

        for hwnd, cb in list(_km_hwnd_to_ms_callback.items()):
            try:
                pData = ctypes.byref(md)
                _user32.PostMessageW(hwnd, WM_MOUSE_EVENT, 0, ctypes.cast(pData, wt.LPARAM))
            except Exception:
                pass

        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    # ── 隐藏窗口创建 ────────────────────────────────────────────────

    _user32.RegisterClassW.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    _user32.RegisterClassW.restype = wt.ATOM
    _user32.CreateWindowExW.argtypes = [
        wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
        wt.INT, wt.INT, wt.INT, wt.INT,
        wt.HWND, wt.HANDLE, wt.HINSTANCE, wt.LPVOID
    ]
    _user32.CreateWindowExW.restype = wt.HWND
    _user32.GetMessageW.argtypes = [ctypes.POINTER(ctypes.c_void_p), wt.HWND, wt.UINT, wt.UINT]
    _user32.GetMessageW.restype = wt.BOOL
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    _user32.TranslateMessage.restype = wt.BOOL
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    _user32.DispatchMessageW.restype = wt.LPARAM
    _user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
    _user32.PostThreadMessageW.restype = wt.BOOL
    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = wt.DWORD
    _user32.SetWindowLongPtrW.argtypes = [wt.HWND, wt.INT, wt.LPARAM]
    _user32.SetWindowLongPtrW.restype = wt.LPARAM
    _user32.SetForegroundWindow.argtypes = [wt.HWND]
    _user32.SetForegroundWindow.restype = wt.BOOL
    _user32.ShowWindow.argtypes = [wt.HWND, wt.INT]
    _user32.ShowWindow.restype = wt.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, wt.LPDWORD]
    _user32.GetWindowThreadProcessId.restype = wt.DWORD

    def _create_km_hidden_window(
        wndclass_atom: int,
        thread_id: int,
    ) -> Optional[int]:
        """创建隐藏窗口（STATIC 类）。"""
        try:
            hwnd = _user32.CreateWindowExW(
                0,  # dwExStyle
                ctypes.cast(wndclass_atom, wt.LPCWSTR),  # lpClassName
                "vools_km",  # lpWindowName
                0,  # dwStyle (overlapped)
                0, 0, 1, 1,  # x, y, w, h
                None,  # hWndParent
                None,  # hMenu
                None,  # hInstance
                None,  # lpParam
            )
            if not hwnd:
                return None
            # 子类化窗口过程
            old_wndproc = _user32.SetWindowLongPtrW(
                hwnd, GWLP_WNDPROC, _km_wndproc_cfunc
            )
            _km_wndproc_map[hwnd] = old_wndproc
            return hwnd
        except Exception:
            return None

    def _post_quit_message(thread_id: int) -> None:
        """通知线程退出。"""
        WM_QUIT = 0x0012
        _user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)

    # ── Windows 键盘后端 ─────────────────────────────────────────────

    class _Win32KeyboardBackend(_BaseBackend):
        """
        Windows 低级键盘钩子后端（WH_KEYBOARD_LL）。
        线程安全：start/stop 可在任意线程调用。
        """

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
            self._hwnd: Optional[int] = None
            self._thread_id: Optional[int] = None
            self._hook_handle: Optional[int] = None

            # 注册窗口类
            wnd_class = ctypes.Structure
            wnd_class._fields_ = [
                ("style", wt.UINT),
                ("lpfnWndProc", _WNDPROC),
                ("cbClsExtra", wt.INT),
                ("cbWndExtra", wt.INT),
                ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HANDLE),
                ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR),
                ("hIconSm", wt.HANDLE),
            ]
            self._wnd_class = wnd_class(
                style=0,
                lpfnWndProc=_km_wndproc_cfunc,
                cbClsExtra=0, cbWndExtra=0,
                hInstance=None,
                hIcon=None,
                hCursor=None,
                hbrBackground=None,
                lpszMenuName=None,
                lpszClassName=_KM_WINDOW_CLASS,
                hIconSm=None,
            )
            self._wnd_class_atom: int = 0

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
                self._wnd_class_atom = _user32.RegisterClassW(ctypes.byref(self._wnd_class))
                if self._wnd_class_atom == 0:
                    log.debug("RegisterClassW failed for keyboard")
                    return

                self._thread_id = _kernel32.GetCurrentThreadId()
                self._hwnd = _create_km_hidden_window(self._wnd_class_atom, self._thread_id)
                if not self._hwnd:
                    log.debug("_create_km_hidden_window failed")
                    return

                # 注册回调
                _km_hwnd_to_kb_callback[self._hwnd] = self._on_change

                # 安装键盘钩子
                self._hook_handle = _user32.SetWindowsHookExW(
                    WH_KEYBOARD_LL,
                    _WNDPROC(_low_level_keyboard_proc),
                    None,
                    0,  # 全局钩子（thread_id=0）
                )
                if not self._hook_handle:
                    log.debug("SetWindowsHookExW keyboard failed")
                    return

                # 消息循环
                msg = ctypes.create_string_buffer(48)
                while not self._stop_event.is_set():
                    ret = _user32.GetMessageW(ctypes.byref(msg), self._hwnd, 0, 0)
                    if ret == 0 or ret == -1:
                        break
                    _user32.TranslateMessage(ctypes.byref(msg))
                    _user32.DispatchMessageW(ctypes.byref(msg))
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
            if self._hwnd and self._hwnd in _km_hwnd_to_kb_callback:
                del _km_hwnd_to_kb_callback[self._hwnd]
                try:
                    if self._thread_id:
                        _post_quit_message(self._thread_id)
                    _user32.DestroyWindow(self._hwnd)
                except Exception:
                    pass
                self._hwnd = None

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

    # ── Windows 鼠标后端 ─────────────────────────────────────────────

    class _Win32MouseBackend(_BaseBackend):
        """Windows 低级鼠标钩子后端（WH_MOUSE_LL）。"""

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
            self._hwnd: Optional[int] = None
            self._thread_id: Optional[int] = None
            self._hook_handle: Optional[int] = None

            wnd_class = ctypes.Structure
            wnd_class._fields_ = [
                ("style", wt.UINT),
                ("lpfnWndProc", _WNDPROC),
                ("cbClsExtra", wt.INT),
                ("cbWndExtra", wt.INT),
                ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HANDLE),
                ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR),
                ("hIconSm", wt.HANDLE),
            ]
            self._wnd_class = wnd_class(
                style=0,
                lpfnWndProc=_km_wndproc_cfunc,
                cbClsExtra=0, cbWndExtra=0,
                hInstance=None,
                hIcon=None,
                hCursor=None,
                hbrBackground=None,
                lpszMenuName=None,
                lpszClassName="vools_ms_cls",
                hIconSm=None,
            )
            self._wnd_class_atom: int = 0

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
                self._wnd_class_atom = _user32.RegisterClassW(ctypes.byref(self._wnd_class))
                if self._wnd_class_atom == 0:
                    log.debug("RegisterClassW failed for mouse")
                    return

                self._thread_id = _kernel32.GetCurrentThreadId()
                self._hwnd = _create_km_hidden_window(self._wnd_class_atom, self._thread_id)
                if not self._hwnd:
                    log.debug("_create_km_hidden_window failed for mouse")
                    return

                _km_hwnd_to_ms_callback[self._hwnd] = self._on_change

                self._hook_handle = _user32.SetWindowsHookExW(
                    WH_MOUSE_LL,
                    _WNDPROC(_low_level_mouse_proc),
                    None,
                    0,
                )
                if not self._hook_handle:
                    log.debug("SetWindowsHookExW mouse failed")
                    return

                msg = ctypes.create_string_buffer(48)
                while not self._stop_event.is_set():
                    ret = _user32.GetMessageW(ctypes.byref(msg), self._hwnd, 0, 0)
                    if ret == 0 or ret == -1:
                        break
                    _user32.TranslateMessage(ctypes.byref(msg))
                    _user32.DispatchMessageW(ctypes.byref(msg))
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
            if self._hwnd and self._hwnd in _km_hwnd_to_ms_callback:
                del _km_hwnd_to_ms_callback[self._hwnd]
                try:
                    if self._thread_id:
                        _post_quit_message(self._thread_id)
                    _user32.DestroyWindow(self._hwnd)
                except Exception:
                    pass
                self._hwnd = None

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

else:
    # 非 Windows：无 Win32 后端
    class _Win32KeyboardBackend(_BaseBackend):
        name = "win32"
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Win32 backend not available on this platform")
        def start(self) -> None: pass
        def stop(self) -> None: pass

    class _Win32MouseBackend(_BaseBackend):
        name = "win32"
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Win32 backend not available on this platform")
        def start(self) -> None: pass
        def stop(self) -> None: pass


# ══════════════════════════════════════════════════════════════════
#   Polling 后端（跨平台）
# ══════════════════════════════════════════════════════════════════


class _PollingKeyboardBackend(_BaseBackend):
    """
    轮询键盘状态后端（跨平台通用）。
    轮询 GetAsyncKeyState(0..255)，对比上次状态，检测按下/释放。
    """

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
        # 上次状态：vk_code -> is_down
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
        import ctypes.wintypes as wt_
        if sys.platform == "win32":
            _GetAsyncKeyState = _user32.GetAsyncKeyState
        else:
            _GetAsyncKeyState = None  # 非 Windows 简化

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
                        # 按下
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
                        # 释放
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


class _PollingMouseBackend(_BaseBackend):
    """
    轮询鼠标状态后端（跨平台通用）。
    轮询 GetCursorPos，对比上次坐标和按钮状态。
    """

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
                except Exception:
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

                # 鼠标移动
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

                # 左键
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

                # 右键
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

                # 中键
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

# ══════════════════════════════════════════════════════════════════
#   KeyboardDispatcher
# ══════════════════════════════════════════════════════════════════


class KeyboardDispatcher:
    """
    键盘事件分发器。

    使用响应式 Subject 模式：内部持有 Subject[KeyData]，
    后端捕获系统键盘事件后通过 subject 分发给所有订阅者。

    Args:
        backend: 后端类型，"auto" | "win32" | "polling"
        filter_self: 是否启用自我过滤（模拟的按键事件被丢弃）
        interval: 轮询间隔（秒）
        tags: 全局标签元组
        metadata: 全局元数据字典
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
        from vools.reactive.subject import Subject
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
        self._pending_sigs: Dict[str, float] = {}  # signature -> expiry_time

        # 选择后端
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
        """后端回调：检查自我过滤 → 派发给 subject。"""
        # 自我过滤
        if self._filter_self:
            sig = _make_key_signature(kd.key_code, kd.is_press)
            now = time.monotonic()
            if sig in self._pending_sigs and self._pending_sigs[sig] > now:
                self._self_filtered_count += 1
                return
            # 清理过期签名
            expired = [k for k, v in list(self._pending_sigs.items()) if v <= now]
            for k in expired:
                del self._pending_sigs[k]

        # 派发
        self._dispatch_count += 1
        try:
            self._subject._on_next(kd)
        except Exception:
            self._error_count += 1
            raise

    def _dispatch_once(self, kd: KeyData) -> None:
        """直接派发（绕过后端）。"""
        self._on_change(kd)

    def _register_self_signature(self, kd: KeyData) -> None:
        """登记自我过滤签名。"""
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

    # ── 键盘模拟 API ──────────────────────────────────────────────

    def press(self, key: Union[str, int]) -> "KeyboardDispatcher":
        """按下键（可链式）。"""
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
        """按键（按下+释放）。"""
        self.press(key).release(key)
        return self

    def type_text(self, text: str) -> "KeyboardDispatcher":
        """输入文本。"""
        _type_text(text)
        return self

    def hotkey(self, *keys: str) -> "KeyboardDispatcher":
        """热键组合。"""
        _hotkey(*keys)
        return self


# ══════════════════════════════════════════════════════════════════
#   MouseDispatcher
# ══════════════════════════════════════════════════════════════════


class MouseDispatcher:
    """
    鼠标事件分发器。

    使用响应式 Subject 模式：内部持有 Subject[MouseData]，
    后端捕获系统鼠标事件后通过 subject 分发给所有订阅者。
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
        from vools.reactive.subject import Subject
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
            self._subject._on_next(md)
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

    # ── 鼠标模拟 API ──────────────────────────────────────────────

    def move_to(self, x: int, y: int) -> "MouseDispatcher":
        """移动鼠标到绝对坐标。"""
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


# ══════════════════════════════════════════════════════════════════
#   KeySubject
# ══════════════════════════════════════════════════════════════════


class KeySubject:
    """
    键盘事件主题（Subject），继承响应式 Subject。

    内部持有 KeyboardDispatcher，提供键盘事件流 + 模拟操作。

    Args:
        backend: 后端类型
        filter_self: 是否启用自我过滤
        interval: 轮询间隔
        tags: 全局标签
        metadata: 全局元数据
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
        self._dispatcher = KeyboardDispatcher(
            backend=backend,
            filter_self=filter_self,
            interval=interval,
            tags=tags,
            metadata=metadata,
        )

    # ── Subject 代理 ───────────────────────────────────────────────

    @property
    def dispatcher(self) -> KeyboardDispatcher:
        return self._dispatcher

    @property
    def subject(self) -> "Subject[KeyData]":
        return self._dispatcher.subject

    @property
    def backend_name(self) -> str:
        return self._dispatcher.backend_name

    @property
    def is_running(self) -> bool:
        return self._dispatcher.is_running

    @property
    def dispatch_count(self) -> int:
        return self._dispatcher.dispatch_count

    @property
    def self_filtered_count(self) -> int:
        return self._dispatcher.self_filtered_count

    def subscribe(
        self,
        on_next: Optional[Callable[[KeyData], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
    ) -> "Subscription":
        return self._dispatcher.subject.subscribe(
            on_next=on_next, on_error=on_error, on_completed=on_completed,
        )

    def pipe(self, *ops: Any) -> Any:
        """支持 pipe 链式操作。"""
        from vools.reactive import ops as _ops
        return self._dispatcher.subject.pipe(*ops)

    def start(self) -> None:
        self._dispatcher.start()

    def stop(self) -> None:
        self._dispatcher.stop()

    def __enter__(self) -> "KeySubject":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self._dispatcher.stop()
        except Exception:
            pass

    # ── 键盘模拟代理 ──────────────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════
#   MouseSubject
# ══════════════════════════════════════════════════════════════════


class MouseSubject:
    """
    鼠标事件主题（Subject），继承响应式 Subject。

    内部持有 MouseDispatcher，提供鼠标事件流 + 模拟操作。
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
        self._dispatcher = MouseDispatcher(
            backend=backend,
            filter_self=filter_self,
            interval=interval,
            tags=tags,
            metadata=metadata,
        )

    @property
    def dispatcher(self) -> MouseDispatcher:
        return self._dispatcher

    @property
    def subject(self) -> "Subject[MouseData]":
        return self._dispatcher.subject

    @property
    def backend_name(self) -> str:
        return self._dispatcher.backend_name

    @property
    def is_running(self) -> bool:
        return self._dispatcher.is_running

    @property
    def dispatch_count(self) -> int:
        return self._dispatcher.dispatch_count

    @property
    def self_filtered_count(self) -> int:
        return self._dispatcher.self_filtered_count

    def subscribe(
        self,
        on_next: Optional[Callable[[MouseData], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
    ) -> "Subscription":
        return self._dispatcher.subject.subscribe(
            on_next=on_next, on_error=on_error, on_completed=on_completed,
        )

    def pipe(self, *ops: Any) -> Any:
        from vools.reactive import ops as _ops
        return self._dispatcher.subject.pipe(*ops)

    def start(self) -> None:
        self._dispatcher.start()

    def stop(self) -> None:
        self._dispatcher.stop()

    def __enter__(self) -> "MouseSubject":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self._dispatcher.stop()
        except Exception:
            pass

    # ── 鼠标模拟代理 ──────────────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════
#   KeyObserver
# ══════════════════════════════════════════════════════════════════


class KeyObserver:
    """
    键盘事件观察者，按 KeyEventType 路由回调。

    Args:
        on_press: KEY_DOWN 回调
        on_release: KEY_UP 回调
        on_hold: KEY_HOLD 回调（预留）
        on_any: 任意事件回调
        on_error: 错误回调
        on_completed: 完成回调
    """

    def __init__(
        self,
        *,
        on_press: Optional[Callable[[KeyData], None]] = None,
        on_release: Optional[Callable[[KeyData], None]] = None,
        on_hold: Optional[Callable[[KeyData], None]] = None,
        on_any: Optional[Callable[[KeyData], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._on_hold = on_hold
        self._on_any = on_any
        self._on_error = on_error
        self._on_completed = on_completed
        self._sub: Optional["Subscription"] = None
        self._source: Optional[Any] = None

    def _on_next(self, kd: KeyData) -> None:
        et = KeyEventType(kd.event_type)
        if et == KeyEventType.KEY_DOWN:
            if self._on_press:
                self._on_press(kd)
        elif et == KeyEventType.KEY_UP:
            if self._on_release:
                self._on_release(kd)
        elif et == KeyEventType.KEY_HOLD:
            if self._on_hold:
                self._on_hold(kd)
        if self._on_any:
            self._on_any(kd)

    def subscribe(self, source: Any) -> "Subscription":
        """从 Observable 订阅。"""
        self._source = source
        self._sub = source.subscribe(
            on_next=self._on_next,
            on_error=self._on_error,
            on_completed=self._on_completed,
        )
        return self._sub

    def attach(self, source: Any) -> "KeyObserver":
        """链式 attach（支持 with 语法）。"""
        self.subscribe(source)
        return self

    def unsubscribe(self) -> None:
        if self._sub:
            self._sub.unsubscribe()
            self._sub = None

    @property
    def is_subscribed(self) -> bool:
        return self._sub is not None and self._sub.is_active

    def __enter__(self) -> "KeyObserver":
        return self

    def __exit__(self, *_: Any) -> None:
        self.unsubscribe()


# ══════════════════════════════════════════════════════════════════
#   MouseObserver
# ══════════════════════════════════════════════════════════════════


class MouseObserver:
    """
    鼠标事件观察者，按 MouseEventType 路由回调。

    Args:
        on_move: MOVE 回调
        on_click: 任意鼠标按键按下回调（LEFT/RIGHT/MIDDLE_DOWN）
        on_scroll: SCROLL 回调
        on_drag: DRAG 回调
        on_any: 任意事件回调
        on_error: 错误回调
        on_completed: 完成回调
    """

    def __init__(
        self,
        *,
        on_move: Optional[Callable[[MouseData], None]] = None,
        on_click: Optional[Callable[[MouseData], None]] = None,
        on_scroll: Optional[Callable[[MouseData], None]] = None,
        on_drag: Optional[Callable[[MouseData], None]] = None,
        on_any: Optional[Callable[[MouseData], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_move = on_move
        self._on_click = on_click
        self._on_scroll = on_scroll
        self._on_drag = on_drag
        self._on_any = on_any
        self._on_error = on_error
        self._on_completed = on_completed
        self._sub: Optional["Subscription"] = None
        self._source: Optional[Any] = None

    def _on_next(self, md: MouseData) -> None:
        et = MouseEventType(md.event_type)
        if et == MouseEventType.MOVE:
            if self._on_move:
                self._on_move(md)
        elif et == MouseEventType.SCROLL:
            if self._on_scroll:
                self._on_scroll(md)
        elif et == MouseEventType.DRAG:
            if self._on_drag:
                self._on_drag(md)
        else:
            # 鼠标按键按下/释放 → click
            if self._on_click:
                self._on_click(md)
        if self._on_any:
            self._on_any(md)

    def subscribe(self, source: Any) -> "Subscription":
        self._source = source
        self._sub = source.subscribe(
            on_next=self._on_next,
            on_error=self._on_error,
            on_completed=self._on_completed,
        )
        return self._sub

    def attach(self, source: Any) -> "MouseObserver":
        self.subscribe(source)
        return self

    def unsubscribe(self) -> None:
        if self._sub:
            self._sub.unsubscribe()
            self._sub = None

    @property
    def is_subscribed(self) -> bool:
        return self._sub is not None and self._sub.is_active

    def __enter__(self) -> "MouseObserver":
        return self

    def __exit__(self, *_: Any) -> None:
        self.unsubscribe()


# ══════════════════════════════════════════════════════════════════
#   工厂函数
# ══════════════════════════════════════════════════════════════════


def from_keyboard(
    *,
    backend: str = "auto",
    filter_self: bool = True,
    auto_start: bool = True,
    interval: float = 0.05,
    tags: Tuple[str, ...] = (),
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, KeyboardDispatcher]:
    """
    工厂函数：创建键盘事件 Observable + KeyboardDispatcher。

    Returns:
        (observable, dispatcher) 二元组
    """
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


def from_mouse(
    *,
    backend: str = "auto",
    filter_self: bool = True,
    auto_start: bool = True,
    interval: float = 0.05,
    tags: Tuple[str, ...] = (),
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, MouseDispatcher]:
    """
    工厂函数：创建鼠标事件 Observable + MouseDispatcher。

    Returns:
        (observable, dispatcher) 二元组
    """
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


# ══════════════════════════════════════════════════════════════════
#   write_to_keyboard 操作符
# ══════════════════════════════════════════════════════════════════


class _WriteKeyboardOperator:
    """write_to_keyboard 操作符实现。"""

    def __init__(self, dispatcher: KeyboardDispatcher) -> None:
        self._dispatcher = dispatcher

    def __call__(self, source: Any) -> Any:
        def on_next(item: Any) -> None:
            if isinstance(item, KeyData):
                # 直接使用 item 中的 is_press 决定行为
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


def write_to_keyboard(
    dispatcher: KeyboardDispatcher,
) -> Callable[[Any], Any]:
    """
    操作符：将上游数据映射为系统键盘操作。

    Args:
        dispatcher: KeyboardDispatcher 实例

    上游数据支持:
        - str: type_text(text)
        - int: tap(vk_code)
        - KeyData: press/release
        - dict: {"key": "A"} / {"key_code": 65, "is_press": True}
    """
    return _WriteKeyboardOperator(dispatcher)


# ══════════════════════════════════════════════════════════════════
#   write_to_mouse 操作符
# ══════════════════════════════════════════════════════════════════


class _WriteMouseOperator:
    """write_to_mouse 操作符实现。"""

    def __init__(self, dispatcher: MouseDispatcher) -> None:
        self._dispatcher = dispatcher

    def __call__(self, source: Any) -> Any:
        def on_next(item: Any) -> None:
            if isinstance(item, MouseData):
                self._dispatcher.move_to(item.x, item.y)
            elif isinstance(item, dict):
                x = item.get("x", 0)
                y = item.get("y", 0)
                event = item.get("event", "move")
                if event == "move":
                    self._dispatcher.move_to(x, y)
                elif event == "click":
                    self._dispatcher.click(item.get("button", "left"))
                elif event == "scroll":
                    self._dispatcher.scroll(item.get("delta", 1))

        from vools.reactive import operators as _ops
        return source.pipe(
            _ops.map(lambda x: (on_next(x) or x))
        )


def write_to_mouse(
    dispatcher: MouseDispatcher,
) -> Callable[[Any], Any]:
    """
    操作符：将上游数据映射为系统鼠标操作。

    Args:
        dispatcher: MouseDispatcher 实例

    上游数据支持:
        - MouseData: move_to(x, y)
        - dict: {"x": 100, "y": 200, "event": "move"}
              {"event": "click", "button": "left"}
              {"event": "scroll", "delta": 3}
    """
    return _WriteMouseOperator(dispatcher)
