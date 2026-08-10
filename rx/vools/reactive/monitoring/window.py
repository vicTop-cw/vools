"""
vools/reactive/monitoring/window.py - 窗口监控模块

仅支持 Windows 平台。使用 SetWinEventHook (Win32) 或 EnumWindows (Polling) 监控窗口事件。

核心公共 API:
    WindowChangeType(IntEnum):  窗口事件类型枚举
    WindowData:                 结构化窗口数据
    WindowDispatcher:           监控与分发器
    WindowSubject:              带生命周期的 Subject
    WindowObserver:             按事件类型路由的观察者
    from_window(...):           顶层工厂函数
    write_to_window(...):       响应式操作符
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime
import itertools
import json
import logging
import sys
import time
from threading import Thread, Lock, Event
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
)

from ...core.dataclass_compat import dataclass, field, asdict
from enum import IntEnum
from .monitor_subject import MonitorSubject
from .monitor_observer import MonitorObserver

if TYPE_CHECKING:
    from vools.reactive.core.observable import Observable, Observer, Subscription
    from vools.reactive.core.subject import Subject

__all__ = [
    "log",
    "WindowChangeType",
    "WindowData",
    "WindowDispatcher",
    "WindowSubject",
    "WindowObserver",
    "from_window",
    "write_to_window",
]

log = logging.getLogger(__name__)

# ── 全局序号计数器 ─────────────────────────────────────────────
_seq_counter = itertools.count(1)


# ═══════════════════════════════════════════════════════════════
#   枚举类型
# ═══════════════════════════════════════════════════════════════

class WindowChangeType(IntEnum):
    """窗口事件类型枚举。"""

    FOCUSED = 0          # 窗口获得焦点
    CREATED = 1          # 窗口创建
    DESTROYED = 2        # 窗口销毁
    TITLE_CHANGED = 3    # 标题变化
    MOVED = 4            # 窗口移动
    SIZED = 5            # 窗口大小变化
    OTHER = 6            # 其他事件

    def __str__(self) -> str:
        return self.name

    def do(self, f=print, pre_f=None, sub_f=None):
        """应用函数并返回 self（链式调用）。"""
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


# ═══════════════════════════════════════════════════════════════
#   数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass(slots=True)
class WindowData:
    """窗口事件数据。

    字段:
        hwnd: 窗口句柄
        title: 窗口标题
        class_name: 窗口类名
        pid: 进程 ID
        path: 进程路径
        rect: 窗口矩形 (left, top, right, bottom)
        event_type: 事件类型 (WindowChangeType)
        timestamp: 事件时间戳
        sequence: 全局序号（单调递增）
        tags: 用户自定义标签
        metadata: 扩展元信息
    """

    hwnd: int = 0
    title: str = ""
    class_name: str = ""
    pid: int = 0
    path: str = ""
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
    event_type: int = WindowChangeType.OTHER
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    sequence: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence == 0:
            object.__setattr__(self, "sequence", next(_seq_counter))

    @classmethod
    def now(
        cls,
        hwnd: int,
        title: str = "",
        class_name: str = "",
        pid: int = 0,
        path: str = "",
        rect: Tuple[int, int, int, int] = (0, 0, 0, 0),
        event_type: WindowChangeType = WindowChangeType.OTHER,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "WindowData":
        """工厂方法：创建当前时间的 WindowData。"""
        return cls(
            hwnd=hwnd,
            title=title,
            class_name=class_name,
            pid=pid,
            path=path,
            rect=rect,
            event_type=int(event_type),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            sequence=next(_seq_counter),
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        d = asdict(self)
        if isinstance(d["timestamp"], datetime.datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WindowData":
        """从字典创建。"""
        d = dict(d)
        if isinstance(d.get("timestamp"), str):
            d["timestamp"] = datetime.datetime.fromisoformat(d["timestamp"])
        return cls(**d)

    def to_json(self) -> str:
        """转换为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "WindowData":
        """从 JSON 字符串创建。"""
        return cls.from_dict(json.loads(s))

    def __repr__(self) -> str:
        return (
            f"WindowData(hwnd={self.hwnd:#08x}, title={self.title!r}, "
            f"event={WindowChangeType(self.event_type).name!r}, "
            f"pid={self.pid}, seq={self.sequence})"
        )

    def do(self, f=print, pre_f=None, sub_f=None):
        """应用函数并返回 self（链式调用）。"""
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


# ═══════════════════════════════════════════════════════════════
#   Win32 API 封装
# ═══════════════════════════════════════════════════════════════

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)

    # WinEvent 常量
    EVENT_SYSTEM_FOREGROUND = 0x0003
    EVENT_OBJECT_CREATE = 0x8000
    EVENT_OBJECT_DESTROY = 0x8001
    EVENT_OBJECT_NAMECHANGE = 0x800C
    EVENT_OBJECT_LOCATIONCHANGE = 0x800B
    WINEVENT_OUTOFCONTEXT = 0x0000

    # WinEventProc 类型
    WINEVENTPROC = ctypes.WINFUNCTYPE(
        None,
        ctypes.c_void_p,  # hWinEventHook
        ctypes.c_uint,    # event
        wt.HWND,          # hwnd
        ctypes.c_long,    # idObject
        ctypes.c_long,    # idChild
        ctypes.c_ulong,   # dwEventThread
        ctypes.c_ulong,   # dwmsEventTime
    )

    # RECT 结构
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    # 函数原型设置
    _user32.SetWinEventHook.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
        WINEVENTPROC,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    _user32.SetWinEventHook.restype = ctypes.c_void_p

    _user32.UnhookWinEvent.argtypes = [ctypes.c_void_p]
    _user32.UnhookWinEvent.restype = ctypes.c_int

    _user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_long]
    _user32.EnumWindows.restype = ctypes.c_int

    _user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int

    _user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int

    _user32.GetClassNameW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int

    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(ctypes.c_ulong)]
    _user32.GetWindowThreadProcessId.restype = ctypes.c_ulong

    _user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
    _user32.GetWindowRect.restype = ctypes.c_int

    _user32.IsWindowVisible.argtypes = [wt.HWND]
    _user32.IsWindowVisible.restype = ctypes.c_int

    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wt.HWND

    _user32.SetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p]
    _user32.SetWindowTextW.restype = ctypes.c_int

    _kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    _kernel32.OpenProcess.restype = ctypes.c_void_p

    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_int

    _psapi.GetModuleFileNameExW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_ulong,
    ]
    _psapi.GetModuleFileNameExW.restype = ctypes.c_ulong

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010

    def _get_window_info(hwnd: int) -> Tuple[str, str, int, str, Tuple[int, int, int, int]]:
        """获取窗口基本信息（标题、类名、进程ID、进程路径、矩形）。"""
        title = ""
        class_name = ""
        pid = 0
        path = ""
        rect = (0, 0, 0, 0)

        try:
            # 窗口标题
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value

            # 窗口类名
            buf2 = ctypes.create_unicode_buffer(256)
            if _user32.GetClassNameW(hwnd, buf2, 256):
                class_name = buf2.value

            # 进程 ID
            pid_buf = ctypes.c_ulong()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
            pid = pid_buf.value

            # 进程路径
            if pid > 0:
                h_proc = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, 0, pid)
                if h_proc:
                    try:
                        path_buf = ctypes.create_unicode_buffer(260)
                        if _psapi.GetModuleFileNameExW(h_proc, None, path_buf, 260):
                            path = path_buf.value
                    finally:
                        _kernel32.CloseHandle(h_proc)

            # 窗口矩形
            rect_struct = RECT()
            if _user32.GetWindowRect(hwnd, ctypes.byref(rect_struct)):
                rect = (rect_struct.left, rect_struct.top, rect_struct.right, rect_struct.bottom)

        except Exception as e:
            log.debug("_get_window_info 异常: %s", e)

        return title, class_name, pid, path, rect

    # EnumWindows 回调类型
    ENUMWINDOWSPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HWND, ctypes.c_long)

    def _enum_visible_windows() -> List[int]:
        """枚举所有可见窗口。"""
        windows: List[int] = []

        def callback(hwnd: int, _lParam: int) -> int:
            if _user32.IsWindowVisible(hwnd):
                windows.append(hwnd)
            return 1  # 继续枚举

        _user32.EnumWindows(ENUMWINDOWSPROC(callback), 0)
        return windows

else:
    # 非 Windows 平台的 stub
    def _get_window_info(hwnd: int) -> Tuple[str, str, int, str, Tuple[int, int, int, int]]:
        return "", "", 0, "", (0, 0, 0, 0)

    def _enum_visible_windows() -> List[int]:
        return []


# ═══════════════════════════════════════════════════════════════
#   后端基类
# ═══════════════════════════════════════════════════════════════

class _BaseBackend:
    """后端基类。"""

    name: str = "base"

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    @property
    def is_running(self) -> bool:
        raise NotImplementedError

    def snapshot(self) -> List[WindowData]:
        """返回当前所有可见窗口的快照。"""
        raise NotImplementedError

    def do(self, f=print, pre_f=None, sub_f=None):
        """应用函数并返回 self（链式调用）。"""
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


# ═══════════════════════════════════════════════════════════════
#   Win32 Hook 后端
# ═══════════════════════════════════════════════════════════════

if sys.platform == "win32":

    class _Win32HookBackend(_BaseBackend):
        """Windows 下基于 SetWinEventHook 的后端。"""

        name = "win32"

        def __init__(self, on_change: Callable[[WindowData], None]) -> None:
            self._on_change = on_change
            self._thread: Optional[Thread] = None
            self._stop_event = Event()
            self._running = False
            self._lock = Lock()
            self._hook_handles: List[int] = []
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
                self._thread = Thread(target=self._run, name="vools-window-win32", daemon=True)
                self._thread.start()

        def stop(self) -> None:
            with self._lock:
                if not self._running:
                    return
                self._running = False
                self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)

        def snapshot(self) -> List[WindowData]:
            """返回当前所有可见窗口的快照。"""
            result: List[WindowData] = []
            try:
                hwnds = _enum_visible_windows()
                for hwnd in hwnds:
                    title, class_name, pid, path, rect = _get_window_info(hwnd)
                    if title or class_name:  # 至少有一个有效信息
                        wd = WindowData.now(
                            hwnd=hwnd,
                            title=title,
                            class_name=class_name,
                            pid=pid,
                            path=path,
                            rect=rect,
                            event_type=WindowChangeType.OTHER,
                        )
                        result.append(wd)
            except Exception as e:
                log.debug("snapshot 异常: %s", e)
            return result

        def _run(self) -> None:
            try:
                # 创建事件回调
                def win_event_proc(
                    hHook: int,
                    event: int,
                    hwnd: int,
                    idObject: int,
                    idChild: int,
                    dwEventThread: int,
                    dwmsEventTime: int,
                ) -> None:
                    try:
                        # 仅处理窗口本身的事件 (OBJID_WINDOW = 0)
                        if idObject != 0:
                            return

                        # 映射事件类型
                        event_type = WindowChangeType.OTHER
                        if event == EVENT_SYSTEM_FOREGROUND:
                            event_type = WindowChangeType.FOCUSED
                        elif event == EVENT_OBJECT_CREATE:
                            event_type = WindowChangeType.CREATED
                        elif event == EVENT_OBJECT_DESTROY:
                            event_type = WindowChangeType.DESTROYED
                        elif event == EVENT_OBJECT_NAMECHANGE:
                            event_type = WindowChangeType.TITLE_CHANGED
                        elif event == EVENT_OBJECT_LOCATIONCHANGE:
                            # 需要进一步判断是移动还是大小变化
                            event_type = WindowChangeType.MOVED

                        title, class_name, pid, path, rect = _get_window_info(hwnd)
                        wd = WindowData.now(
                            hwnd=hwnd,
                            title=title,
                            class_name=class_name,
                            pid=pid,
                            path=path,
                            rect=rect,
                            event_type=event_type,
                        )

                        try:
                            self._on_change(wd)
                        except Exception as e:
                            log.debug("win_event_proc on_change 异常: %s", e)

                    except Exception as e:
                        log.debug("win_event_proc 异常: %s", e)

                self._hook_proc = WINEVENTPROC(win_event_proc)

                # 注册多个事件钩子
                events_to_hook = [
                    EVENT_SYSTEM_FOREGROUND,
                    EVENT_OBJECT_CREATE,
                    EVENT_OBJECT_DESTROY,
                    EVENT_OBJECT_NAMECHANGE,
                    EVENT_OBJECT_LOCATIONCHANGE,
                ]

                for event in events_to_hook:
                    hook = _user32.SetWinEventHook(
                        event,
                        event,
                        None,
                        self._hook_proc,
                        0,
                        0,
                        WINEVENT_OUTOFCONTEXT,
                    )
                    if hook:
                        self._hook_handles.append(hook)
                    else:
                        log.debug("SetWinEventHook(event=%#x) 失败", event)

                # 消息循环
                msg = wt.MSG()
                while not self._stop_event.is_set():
                    ret = _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
                    if ret != 0:
                        _user32.TranslateMessage(ctypes.byref(msg))
                        _user32.DispatchMessageW(ctypes.byref(msg))
                    time.sleep(0.01)

            except Exception as e:
                log.debug("_Win32HookBackend._run 异常: %s", e)
            finally:
                self._cleanup()
                self._running = False

        def _cleanup(self) -> None:
            for hook in self._hook_handles:
                try:
                    _user32.UnhookWinEvent(hook)
                except Exception:
                    pass
            self._hook_handles.clear()
            self._hook_proc = None

else:

    class _Win32HookBackend(_BaseBackend):  # type: ignore[no-redef]
        """非 Windows 平台的 stub。"""

        name = "win32"

        def __init__(self, on_change: Callable[[WindowData], None]) -> None:
            raise OSError("Win32 backend is only available on Windows")

        @property
        def is_running(self) -> bool:
            return False

        def start(self) -> None:
            raise OSError("Win32 backend is only available on Windows")

        def stop(self) -> None:
            pass

        def snapshot(self) -> List[WindowData]:
            return []


# ═══════════════════════════════════════════════════════════════
#   Polling 后端
# ═══════════════════════════════════════════════════════════════

class _PollingBackend(_BaseBackend):
    """基于 EnumWindows 轮询的后端。"""

    name = "polling"

    def __init__(
        self,
        on_change: Callable[[WindowData], None],
        interval: float = 0.5,
    ) -> None:
        self._on_change = on_change
        self._interval = max(0.1, float(interval))
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._running = False
        self._lock = Lock()
        self._prev_snapshot: Dict[int, Tuple[str, Tuple[int, int, int, int]]] = {}
        self._prev_focused: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._running = True
            self._thread = Thread(target=self._run, name="vools-window-polling", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self._interval * 2 + 0.5))

    def snapshot(self) -> List[WindowData]:
        """返回当前所有可见窗口的快照。"""
        result: List[WindowData] = []
        try:
            hwnds = _enum_visible_windows()
            for hwnd in hwnds:
                title, class_name, pid, path, rect = _get_window_info(hwnd)
                if title or class_name:
                    wd = WindowData.now(
                        hwnd=hwnd,
                        title=title,
                        class_name=class_name,
                        pid=pid,
                        path=path,
                        rect=rect,
                        event_type=WindowChangeType.OTHER,
                    )
                    result.append(wd)
        except Exception as e:
            log.debug("snapshot 异常: %s", e)
        return result

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    self._poll_once()
                except Exception as e:
                    log.debug("_poll_once 异常: %s", e)
                self._stop_event.wait(self._interval)
        finally:
            self._running = False

    def _poll_once(self) -> None:
        """执行一次轮询，检测窗口变化。"""
        current_hwnds: Dict[int, Tuple[str, Tuple[int, int, int, int]]] = {}

        # 获取当前所有可见窗口
        try:
            hwnds = _enum_visible_windows()
            for hwnd in hwnds:
                title, _, _, _, rect = _get_window_info(hwnd)
                current_hwnds[hwnd] = (title, rect)
        except Exception as e:
            log.debug("_poll_once 枚举窗口异常: %s", e)
            return

        # 检测前台窗口变化
        if sys.platform == "win32":
            try:
                focused_hwnd = _user32.GetForegroundWindow()
                if focused_hwnd != self._prev_focused:
                    self._prev_focused = focused_hwnd
                    title, class_name, pid, path, rect = _get_window_info(focused_hwnd)
                    wd = WindowData.now(
                        hwnd=focused_hwnd,
                        title=title,
                        class_name=class_name,
                        pid=pid,
                        path=path,
                        rect=rect,
                        event_type=WindowChangeType.FOCUSED,
                    )
                    try:
                        self._on_change(wd)
                    except Exception as e:
                        log.debug("on_change(FOCUSED) 异常: %s", e)
            except Exception as e:
                log.debug("GetForegroundWindow 异常: %s", e)

        # 检测新建窗口
        for hwnd in current_hwnds:
            if hwnd not in self._prev_snapshot:
                title, rect = current_hwnds[hwnd]
                class_name = ""
                pid = 0
                path = ""
                if sys.platform == "win32":
                    _, class_name, pid, path, rect = _get_window_info(hwnd)
                wd = WindowData.now(
                    hwnd=hwnd,
                    title=title,
                    class_name=class_name,
                    pid=pid,
                    path=path,
                    rect=rect,
                    event_type=WindowChangeType.CREATED,
                )
                try:
                    self._on_change(wd)
                except Exception as e:
                    log.debug("on_change(CREATED) 异常: %s", e)

        # 检测销毁窗口
        for hwnd in self._prev_snapshot:
            if hwnd not in current_hwnds:
                title, rect = self._prev_snapshot[hwnd]
                wd = WindowData.now(
                    hwnd=hwnd,
                    title=title,
                    class_name="",
                    pid=0,
                    path="",
                    rect=rect,
                    event_type=WindowChangeType.DESTROYED,
                )
                try:
                    self._on_change(wd)
                except Exception as e:
                    log.debug("on_change(DESTROYED) 异常: %s", e)

        # 检测标题/位置变化
        for hwnd in current_hwnds:
            curr_title, curr_rect = current_hwnds[hwnd]
            if hwnd in self._prev_snapshot:
                prev_title, prev_rect = self._prev_snapshot[hwnd]

                # 标题变化
                if curr_title != prev_title:
                    class_name = ""
                    pid = 0
                    path = ""
                    if sys.platform == "win32":
                        _, class_name, pid, path, _ = _get_window_info(hwnd)
                    wd = WindowData.now(
                        hwnd=hwnd,
                        title=curr_title,
                        class_name=class_name,
                        pid=pid,
                        path=path,
                        rect=curr_rect,
                        event_type=WindowChangeType.TITLE_CHANGED,
                    )
                    try:
                        self._on_change(wd)
                    except Exception as e:
                        log.debug("on_change(TITLE_CHANGED) 异常: %s", e)

                # 位置/大小变化
                if curr_rect != prev_rect:
                    class_name = ""
                    pid = 0
                    path = ""
                    if sys.platform == "win32":
                        _, class_name, pid, path, _ = _get_window_info(hwnd)
                    # 简化：统一作为 MOVED
                    wd = WindowData.now(
                        hwnd=hwnd,
                        title=curr_title,
                        class_name=class_name,
                        pid=pid,
                        path=path,
                        rect=curr_rect,
                        event_type=WindowChangeType.MOVED,
                    )
                    try:
                        self._on_change(wd)
                    except Exception as e:
                        log.debug("on_change(MOVED) 异常: %s", e)

        # 更新快照
        self._prev_snapshot = current_hwnds


# ═══════════════════════════════════════════════════════════════
#   WindowDispatcher
# ═══════════════════════════════════════════════════════════════

class WindowDispatcher:
    """窗口监控与分发器。

    支持两种后端：
        - win32: 使用 SetWinEventHook（仅 Windows）
        - polling: 使用 EnumWindows 轮询（跨平台）

    用法：
        >>> d = WindowDispatcher(backend="auto")
        >>> d.subject.subscribe(on_next=lambda x: print(x))
        >>> d.start()
        >>> # ... 监控窗口事件 ...
        >>> d.stop()
    """

    def __init__(
        self,
        *,
        backend: str = "auto",
        interval: float = 0.5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        from ..core.subject import Subject

        self._backend_name: str = ""
        self._backend: Optional[_BaseBackend] = None
        self._interval = interval
        self._tags = list(tags or [])
        self._metadata = dict(metadata or {})
        self._subject = Subject[WindowData]()
        self._running = False
        self._lock = Lock()
        self._dispatch_count = 0
        self._error_count = 0

        # 选择后端
        be = backend.lower()
        if be == "auto":
            be = "win32" if sys.platform == "win32" else "polling"

        self._backend_name = be

        if be == "win32" and sys.platform == "win32":
            try:
                self._backend = _Win32HookBackend(on_change=self._on_change)
            except Exception as e:
                log.debug("win32 backend 初始化失败: %s, 回退到 polling", e)
                self._backend = _PollingBackend(
                    on_change=self._on_change, interval=interval
                )
                self._backend_name = "polling"
        elif be == "polling":
            self._backend = _PollingBackend(
                on_change=self._on_change, interval=interval
            )
        else:
            self._backend = _PollingBackend(
                on_change=self._on_change, interval=interval
            )
            self._backend_name = "polling"

    @property
    def subject(self) -> "Subject[WindowData]":
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

    def _on_change(self, wd: WindowData) -> None:
        """事件回调：将 WindowData 分发给订阅者。"""
        self._dispatch_count += 1
        try:
            self._subject.on_next(wd)
        except Exception as e:
            self._error_count += 1
            log.debug("_on_change subject.on_next 异常: %s", e)

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

    def snapshot(self) -> List[WindowData]:
        """返回当前所有可见窗口的快照。"""
        if self._backend:
            return self._backend.snapshot()
        return []

    def __enter__(self) -> "WindowDispatcher":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    def do(self, f=print, pre_f=None, sub_f=None):
        """应用函数并返回 self（链式调用）。"""
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


# ═══════════════════════════════════════════════════════════════
#   WindowSubject
# ═══════════════════════════════════════════════════════════════

class WindowSubject(MonitorSubject):
    """窗口事件主题（Subject），继承 MonitorSubject。

    内部持有 WindowDispatcher，提供窗口事件流。

    方法:
        start(): 开始监控
        stop(): 停止监控
        snapshot(): 返回当前所有可见窗口的快照
    """

    def __init__(
        self,
        *,
        backend: str = "auto",
        interval: float = 0.5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化窗口监控主题。

        Args:
            backend: 后端类型，"auto" | "win32" | "polling"
            interval: 轮询间隔（秒），仅 polling 后端使用
            tags: 默认附加的标签
            metadata: 默认元数据
        """
        self._backend = backend
        self._interval = interval
        self._tags = tags
        self._metadata = metadata
        super().__init__()

    def _create_dispatcher(self) -> "WindowDispatcher":
        return WindowDispatcher(
            backend=self._backend,
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
    def dispatcher(self) -> "WindowDispatcher":
        return self._dispatcher

    @property
    def subject(self) -> "Subject[WindowData]":
        return self

    @property
    def backend_name(self) -> str:
        return self._dispatcher.backend_name

    @property
    def dispatch_count(self) -> int:
        return self._dispatcher.dispatch_count

    def snapshot(self) -> List[WindowData]:
        """返回当前所有可见窗口的快照。"""
        return self._dispatcher.snapshot()

    def __enter__(self) -> "WindowSubject":
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
        """应用函数并返回 self（链式调用）。"""
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


# ═══════════════════════════════════════════════════════════════
#   WindowObserver
# ═══════════════════════════════════════════════════════════════

class WindowObserver(MonitorObserver):
    """窗口事件观察者，按 WindowChangeType 路由回调。

    Args:
        on_focused: 窗口获得焦点回调
        on_created: 窗口创建回调
        on_destroyed: 窗口销毁回调
        on_title_changed: 标题变化回调
        on_moved: 窗口移动回调
        on_sized: 窗口大小变化回调
        on_any: 任意事件回调
        on_error: 错误回调
        on_completed: 完成回调
    """

    def __init__(
        self,
        *,
        on_focused: Optional[Callable[[WindowData], Any]] = None,
        on_created: Optional[Callable[[WindowData], Any]] = None,
        on_destroyed: Optional[Callable[[WindowData], Any]] = None,
        on_title_changed: Optional[Callable[[WindowData], Any]] = None,
        on_moved: Optional[Callable[[WindowData], Any]] = None,
        on_sized: Optional[Callable[[WindowData], Any]] = None,
        on_any: Optional[Callable[[WindowData], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            on_any=on_any,
            on_error=on_error,
            on_completed=on_completed,
        )
        self._on_focused = on_focused
        self._on_created = on_created
        self._on_destroyed = on_destroyed
        self._on_title_changed = on_title_changed
        self._on_moved = on_moved
        self._on_sized = on_sized

    def _event_type_of(self, value: Any) -> Any:
        """提取事件类型。"""
        return WindowChangeType(value.event_type)

    def _handler_for(self, event_type: Any) -> Optional[Callable[[Any], Any]]:
        """根据事件类型返回回调函数。"""
        if event_type == WindowChangeType.FOCUSED:
            return self._on_focused
        if event_type == WindowChangeType.CREATED:
            return self._on_created
        if event_type == WindowChangeType.DESTROYED:
            return self._on_destroyed
        if event_type == WindowChangeType.TITLE_CHANGED:
            return self._on_title_changed
        if event_type == WindowChangeType.MOVED:
            return self._on_moved
        if event_type == WindowChangeType.SIZED:
            return self._on_sized
        return None

    def _on_next(self, wd: "WindowData") -> None:
        self.on_next(wd)

    def __enter__(self) -> "WindowObserver":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.unsubscribe()

    def do(self, f=print, pre_f=None, sub_f=None):
        """应用函数并返回 self（链式调用）。"""
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


# ═══════════════════════════════════════════════════════════════
#   顶层工厂函数
# ═══════════════════════════════════════════════════════════════

def from_window(
    *,
    backend: str = "auto",
    auto_start: bool = True,
    interval: float = 0.5,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, WindowDispatcher]:
    """顶层工厂函数：返回 (Observable[WindowData], Dispatcher) 二元组。

    用法：
        >>> obs, d = from_window()
        >>> obs.subscribe(on_next=lambda x: print(x))
        >>> d.stop()
    """
    disp = WindowDispatcher(
        backend=backend,
        interval=interval,
        tags=tags,
        metadata=metadata,
    )
    if auto_start:
        disp.start()
    return disp.subject, disp


# ═══════════════════════════════════════════════════════════════
#   写入操作符
# ═══════════════════════════════════════════════════════════════

class _WriteWindowOperator:
    """写入窗口的操作符。"""

    def __init__(self, dispatcher: WindowDispatcher) -> None:
        self._dispatcher = dispatcher

    def __call__(self, source: Any) -> Any:
        def on_next(item: Any) -> None:
            # 注意：写入窗口标题、移动窗口等操作需要通过 Win32 API
            # 这里提供简化的实现，实际应用中可能需要扩展
            if sys.platform == "win32":
                if isinstance(item, WindowData):
                    # 示例：设置窗口标题
                    if item.title:
                        try:
                            _user32.SetWindowTextW(item.hwnd, item.title)
                        except Exception as e:
                            log.debug("SetWindowTextW 异常: %s", e)
                elif isinstance(item, dict):
                    hwnd = item.get("hwnd", 0)
                    title = item.get("title", "")
                    if hwnd and title:
                        try:
                            _user32.SetWindowTextW(hwnd, title)
                        except Exception as e:
                            log.debug("SetWindowTextW 异常: %s", e)

        from ..core import operators as _ops
        return source.pipe(_ops.map(lambda x: (on_next(x) or x)))

    def do(self, f=print, pre_f=None, sub_f=None):
        """应用函数并返回 self（链式调用）。"""
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


def write_to_window(
    dispatcher: WindowDispatcher,
) -> Callable[[Any], Any]:
    """响应式操作符：写入窗口标题、移动窗口等。

    用法：
        >>> obs, d = from_window()
        >>> obs.pipe(
        ...     write_to_window(d)
        ... ).subscribe(on_next=print)
    """
    return _WriteWindowOperator(dispatcher)