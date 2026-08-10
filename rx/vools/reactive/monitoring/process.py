"""
vools/reactive/monitoring/process.py - 进程监控模块

仅支持 Windows 平台，使用轮询快照对比方式检测进程启动/退出事件。

核心公共 API:
    ProcessChangeType(IntEnum): 进程事件类型枚举
    ProcessData: 结构化进程事件数据（支持 JSON 序列化）
    ProcessDispatcher: 进程监控与分发器
    ProcessSubject: 自包含 Dispatcher 的 Subject
    ProcessObserver: 按事件类型路由的观察者
    from_process(...): 顶层工厂函数
    write_to_process(...): 响应式操作符
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime
import itertools
import json
import logging
import sys
import threading
import time
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    TYPE_CHECKING,
)
from threading import Thread, Lock, Event

from ...core.dataclass_compat import dataclass, field
from enum import IntEnum

from .monitor_subject import MonitorSubject
from .monitor_observer import MonitorObserver

if TYPE_CHECKING:
    from vools.reactive.core.observable import Observable, Observer, Subscription
    from vools.reactive.core.subject import Subject

__all__ = [
    "log",
    "ProcessChangeType",
    "ProcessData",
    "ProcessDispatcher",
    "ProcessSubject",
    "ProcessObserver",
    "from_process",
    "write_to_process",
]

log = logging.getLogger(__name__)

# 全局序号计数器
_seq_counter = itertools.count(1)


# ═══════════════════════════════════════════════════════════
#   进程事件类型枚举
# ═══════════════════════════════════════════════════════════


class ProcessChangeType(IntEnum):
    """进程事件类型枚举。"""

    STARTED = 0   # 进程启动
    EXITED = 1    # 进程退出
    MODIFIED = 2  # 进程状态变化（暂未实现）
    OTHER = 3     # 其它事件

    def __str__(self) -> str:
        return self.name


# ═══════════════════════════════════════════════════════════
#   进程数据结构
# ═══════════════════════════════════════════════════════════


@dataclass(slots=True)
class ProcessData:
    """进程事件数据。

    字段:
        pid: 进程 ID
        ppid: 父进程 ID
        name: 进程名（可执行文件名）
        path: 进程完整路径
        cmdline: 命令行参数列表
        status: 运行状态（running/suspended 等）
        event_type: 事件类型（ProcessChangeType）
        timestamp: 事件时间戳
        sequence: 全局序号（单调递增）
        tags: 用户自定义标签
        metadata: 扩展元信息
    """

    pid: int = 0
    ppid: int = 0
    name: str = ""
    path: str = ""
    cmdline: List[str] = field(default_factory=list)
    status: str = "running"
    event_type: ProcessChangeType = ProcessChangeType.STARTED
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    sequence: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence == 0:
            object.__setattr__(self, "sequence", next(_seq_counter))

    # ---- 工厂方法 ----------------------------------------------------
    @classmethod
    def now(
        cls,
        pid: int,
        ppid: int = 0,
        name: str = "",
        path: str = "",
        cmdline: Optional[List[str]] = None,
        status: str = "running",
        event_type: ProcessChangeType = ProcessChangeType.STARTED,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ProcessData":
        """创建当前时间戳的 ProcessData 实例。"""
        return cls(
            pid=pid,
            ppid=ppid,
            name=name,
            path=path,
            cmdline=cmdline or [],
            status=status,
            event_type=event_type,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            sequence=next(_seq_counter),
            tags=tags or [],
            metadata=metadata or {},
        )

    # ---- 序列化 -------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        d = {
            "pid": self.pid,
            "ppid": self.ppid,
            "name": self.name,
            "path": self.path,
            "cmdline": list(self.cmdline),
            "status": self.status,
            "event_type": int(self.event_type),
            "event_type_name": self.event_type.name,
            "timestamp": self.timestamp.isoformat() if isinstance(
                self.timestamp, datetime.datetime
            ) else str(self.timestamp),
            "sequence": self.sequence,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProcessData":
        """从字典创建实例。"""
        data = dict(d)
        # 处理 event_type
        et_raw = data.pop("event_type", None)
        et_name = data.pop("event_type_name", None)
        if et_raw is not None:
            try:
                data["event_type"] = ProcessChangeType(int(et_raw))
            except (TypeError, ValueError):
                if et_name:
                    try:
                        data["event_type"] = ProcessChangeType[et_name]
                    except KeyError:
                        data["event_type"] = ProcessChangeType.OTHER
                else:
                    data["event_type"] = ProcessChangeType.OTHER
        # 处理 timestamp
        ts = data.get("timestamp")
        if isinstance(ts, str):
            try:
                data["timestamp"] = datetime.datetime.fromisoformat(ts)
            except ValueError:
                data["timestamp"] = datetime.datetime.now(datetime.timezone.utc)
        elif not isinstance(ts, datetime.datetime):
            data["timestamp"] = datetime.datetime.now(datetime.timezone.utc)
        # 处理列表字段
        data["cmdline"] = list(data.get("cmdline") or [])
        data["tags"] = list(data.get("tags") or [])
        data["metadata"] = dict(data.get("metadata") or {})
        return cls(**data)

    def to_json(self, **kwargs: Any) -> str:
        """转换为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    @classmethod
    def from_json(cls, s: str, **kwargs: Any) -> "ProcessData":
        """从 JSON 字符串创建实例。"""
        return cls.from_dict(json.loads(s, **kwargs))

    # ---- 表示 ---------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"ProcessData(pid={self.pid}, name={self.name!r}, "
            f"event_type={self.event_type.name}, seq={self.sequence})"
        )


# ═══════════════════════════════════════════════════════════
#   Win32 API 定义
# ═══════════════════════════════════════════════════════════

# 常量定义
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MAX_PATH = 260

# Windows API 函数设置（仅在 Windows 上初始化）
if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)

    # PROCESSENTRY32 结构体
    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),  # ULONG_PTR
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", wt.LONG),
            ("dwFlags", wt.DWORD),
            ("szExeFile", wt.CHAR * MAX_PATH),
        ]

    # 设置函数签名
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE

    _kernel32.Process32First.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    _kernel32.Process32First.restype = wt.BOOL

    _kernel32.Process32Next.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    _kernel32.Process32Next.restype = wt.BOOL

    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32.CloseHandle.restype = wt.BOOL

    _kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _kernel32.OpenProcess.restype = wt.HANDLE

    _psapi.GetModuleFileNameExW.argtypes = [
        wt.HANDLE, wt.HMODULE, ctypes.c_wchar_p, wt.DWORD
    ]
    _psapi.GetModuleFileNameExW.restype = wt.DWORD

    _kernel32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
    _kernel32.TerminateProcess.restype = wt.BOOL

else:
    _kernel32 = None  # type: ignore[assignment]
    _psapi = None  # type: ignore[assignment]
    PROCESSENTRY32 = None  # type: ignore[misc,assignment]


# ═══════════════════════════════════════════════════════════
#   进程快照函数
# ═══════════════════════════════════════════════════════════


def _get_process_path(pid: int) -> str:
    """获取进程完整路径（仅 Windows）。"""
    if sys.platform != "win32":
        return ""
    try:
        h_process = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h_process:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(MAX_PATH * 2)
            if _psapi.GetModuleFileNameExW(h_process, 0, buf, len(buf)):
                return buf.value
            return ""
        finally:
            _kernel32.CloseHandle(h_process)
    except Exception:
        return ""


def _snapshot_processes() -> Dict[int, ProcessData]:
    """获取当前所有进程的快照（仅 Windows）。

    返回:
        Dict[int, ProcessData]: 以 pid 为键的进程数据字典
    """
    if sys.platform != "win32":
        return {}

    processes: Dict[int, ProcessData] = {}
    h_snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not h_snapshot or h_snapshot == -1:
        return processes

    try:
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)

        if not _kernel32.Process32First(h_snapshot, ctypes.byref(pe)):
            return processes

        while True:
            pid = pe.th32ProcessID
            ppid = pe.th32ParentProcessID
            # 进程名（ANSI）
            name = pe.szExeFile.decode("mbcs", errors="replace")
            # 获取完整路径
            path = _get_process_path(pid) if pid > 0 else ""

            processes[pid] = ProcessData(
                pid=pid,
                ppid=ppid,
                name=name,
                path=path,
                cmdline=[],
                status="running",
                event_type=ProcessChangeType.STARTED,
                sequence=next(_seq_counter),
            )

            if not _kernel32.Process32Next(h_snapshot, ctypes.byref(pe)):
                break
    except Exception as e:
        log.debug("_snapshot_processes 异常: %s", e)
    finally:
        _kernel32.CloseHandle(h_snapshot)

    return processes


# ═══════════════════════════════════════════════════════════
#   ProcessDispatcher
# ═══════════════════════════════════════════════════════════


class ProcessDispatcher:
    """进程监控与分发器。

    使用轮询快照对比方式检测进程启动/退出事件。

    参数:
        interval: 轮询间隔（秒），默认 1.0
        include_system: 是否包含系统进程（pid <= 4），默认 False
        name_filter: 进程名过滤函数，返回 True 的进程才会被监控
    """

    __slots__ = (
        "_interval",
        "_include_system",
        "_name_filter",
        "_subject",
        "_running",
        "_lock",
        "_thread",
        "_stop_event",
        "_dispatch_count",
        "_error_count",
        "_backend_name",
        "_last_snapshot",
    )

    def __init__(
        self,
        *,
        interval: float = 1.0,
        include_system: bool = False,
        name_filter: Optional[Callable[[str], bool]] = None,
    ) -> None:
        from ..core.subject import Subject

        self._interval = max(0.1, float(interval))
        self._include_system = include_system
        self._name_filter = name_filter
        self._subject: Subject[ProcessData] = Subject()
        self._running = False
        self._lock = Lock()
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._dispatch_count = 0
        self._error_count = 0
        self._backend_name = "polling" if sys.platform == "win32" else "none"
        self._last_snapshot: Dict[int, ProcessData] = {}

    # ---- 属性 ---------------------------------------------------------
    @property
    def subject(self) -> "Subject[ProcessData]":
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

    # ---- 生命周期 -----------------------------------------------------
    def start(self) -> None:
        """启动进程监控。"""
        with self._lock:
            if self._running:
                return
            if sys.platform != "win32":
                log.warning("进程监控仅支持 Windows 平台")
                return
            self._stop_event.clear()
            self._running = True
            self._thread = Thread(
                target=self._run, name="vools-process-monitor", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """停止进程监控。"""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval * 3 + 1.0)
        self._thread = None

    def __enter__(self) -> "ProcessDispatcher":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # ---- 核心监控逻辑 --------------------------------------------------
    def _run(self) -> None:
        """监控线程主循环。"""
        try:
            # 初始快照
            self._last_snapshot = _snapshot_processes()

            while not self._stop_event.is_set():
                try:
                    self._poll()
                except Exception as e:
                    log.debug("进程监控轮询异常: %s", e)
                    self._error_count += 1

                if self._stop_event.wait(self._interval):
                    break
        except Exception as e:
            log.debug("进程监控线程异常: %s", e)
        finally:
            self._running = False

    def _poll(self) -> None:
        """执行一次快照对比，检测进程变化。"""
        current = _snapshot_processes()
        last = self._last_snapshot

        # 检测新启动的进程
        started_pids = set(current.keys()) - set(last.keys())
        for pid in started_pids:
            pdata = current[pid]
            if not self._should_track(pdata):
                continue
            # 更新事件类型为 STARTED
            event_data = ProcessData(
                pid=pdata.pid,
                ppid=pdata.ppid,
                name=pdata.name,
                path=pdata.path,
                cmdline=pdata.cmdline,
                status=pdata.status,
                event_type=ProcessChangeType.STARTED,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                sequence=next(_seq_counter),
            )
            self._dispatch(event_data)

        # 检测退出的进程
        exited_pids = set(last.keys()) - set(current.keys())
        for pid in exited_pids:
            pdata = last[pid]
            if not self._should_track(pdata):
                continue
            # 更新事件类型为 EXITED
            event_data = ProcessData(
                pid=pdata.pid,
                ppid=pdata.ppid,
                name=pdata.name,
                path=pdata.path,
                cmdline=pdata.cmdline,
                status="exited",
                event_type=ProcessChangeType.EXITED,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                sequence=next(_seq_counter),
            )
            self._dispatch(event_data)

        # 更新快照
        self._last_snapshot = current

    def _should_track(self, pdata: ProcessData) -> bool:
        """判断进程是否应该被跟踪。"""
        # 系统进程过滤
        if not self._include_system and pdata.pid <= 4:
            return False
        # 名称过滤
        if self._name_filter is not None:
            try:
                if not self._name_filter(pdata.name):
                    return False
            except Exception:
                pass
        return True

    def _dispatch(self, pdata: ProcessData) -> None:
        """分发进程事件。"""
        try:
            self._subject.on_next(pdata)
            self._dispatch_count += 1
        except Exception as e:
            log.debug("分发进程事件异常: %s", e)
            self._error_count += 1

    # ---- 公共方法 -----------------------------------------------------
    def snapshot(self) -> List[ProcessData]:
        """返回当前所有进程的快照列表。"""
        return list(_snapshot_processes().values())

    def terminate(self, pid: int, exit_code: int = 0) -> bool:
        """终止指定进程。

        参数:
            pid: 进程 ID
            exit_code: 退出码

        返回:
            bool: 是否成功
        """
        if sys.platform != "win32":
            return False
        try:
            h_process = _kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
            if not h_process:
                return False
            try:
                return bool(_kernel32.TerminateProcess(h_process, exit_code))
            finally:
                _kernel32.CloseHandle(h_process)
        except Exception as e:
            log.debug("terminate(%d) 异常: %s", pid, e)
            return False


# ═══════════════════════════════════════════════════════════
#   ProcessSubject
# ═══════════════════════════════════════════════════════════


class ProcessSubject(MonitorSubject):
    """进程事件主题（Subject），继承 MonitorSubject。

    内部持有 ProcessDispatcher，提供进程启动/退出事件流。
    """

    __slots__ = ("_interval", "_include_system", "_name_filter")

    def __init__(
        self,
        *,
        interval: float = 1.0,
        include_system: bool = False,
        name_filter: Optional[Callable[[str], bool]] = None,
    ) -> None:
        """初始化进程监控主题。

        参数:
            interval: 轮询间隔（秒）
            include_system: 是否包含系统进程（pid <= 4）
            name_filter: 进程名过滤函数
        """
        self._interval = interval
        self._include_system = include_system
        self._name_filter = name_filter
        super().__init__()

    def _create_dispatcher(self) -> ProcessDispatcher:
        return ProcessDispatcher(
            interval=self._interval,
            include_system=self._include_system,
            name_filter=self._name_filter,
        )

    def _connect_dispatcher(self) -> None:
        self._conn_sub = self._dispatcher.subject.subscribe(
            on_next=self.on_next,
            on_error=self.on_error,
            on_completed=self.on_completed,
        )

    @property
    def dispatcher(self) -> ProcessDispatcher:
        return self._dispatcher

    @property
    def subject(self) -> "Subject[ProcessData]":
        return self

    @property
    def backend_name(self) -> str:
        return self._dispatcher.backend_name

    @property
    def dispatch_count(self) -> int:
        return self._dispatcher.dispatch_count

    def snapshot(self) -> List[ProcessData]:
        """返回当前所有进程的快照列表。"""
        return self._dispatcher.snapshot()

    def terminate(self, pid: int, exit_code: int = 0) -> bool:
        """终止指定进程。"""
        return self._dispatcher.terminate(pid, exit_code)

    def __enter__(self) -> "ProcessSubject":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()


# ═══════════════════════════════════════════════════════════
#   ProcessObserver
# ═══════════════════════════════════════════════════════════


class ProcessObserver(MonitorObserver):
    """进程事件观察者，按 ProcessChangeType 路由回调。

    参数:
        on_started: 进程启动回调
        on_exited: 进程退出回调
        on_modified: 进程状态变化回调（暂未实现）
        on_any: 任意事件回调
        on_error: 错误回调
        on_completed: 完成回调
        on_start: 监控启动回调
        on_stop: 监控停止回调
    """

    __slots__ = ("_on_started", "_on_exited", "_on_modified")

    def __init__(
        self,
        *,
        on_started: Optional[Callable[[ProcessData], Any]] = None,
        on_exited: Optional[Callable[[ProcessData], Any]] = None,
        on_modified: Optional[Callable[[ProcessData], Any]] = None,
        on_any: Optional[Callable[[ProcessData], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
        on_start: Optional[Callable[[], Any]] = None,
        on_stop: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            on_any=on_any,
            on_error=on_error,
            on_completed=on_completed,
            on_start=on_start,
            on_stop=on_stop,
        )
        self._on_started = on_started
        self._on_exited = on_exited
        self._on_modified = on_modified

    def _event_type_of(self, value: ProcessData) -> ProcessChangeType:
        """从事件数据中提取事件类型。"""
        return ProcessChangeType(value.event_type)

    def _handler_for(self, event_type: ProcessChangeType) -> Optional[Callable[[ProcessData], Any]]:
        """根据事件类型返回对应的回调函数。"""
        if event_type == ProcessChangeType.STARTED:
            return self._on_started
        if event_type == ProcessChangeType.EXITED:
            return self._on_exited
        if event_type == ProcessChangeType.MODIFIED:
            return self._on_modified
        return None

    def __enter__(self) -> "ProcessObserver":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.unsubscribe()


# ═══════════════════════════════════════════════════════════
#   顶层工厂函数
# ═══════════════════════════════════════════════════════════


def from_process(
    *,
    interval: float = 1.0,
    include_system: bool = False,
    name_filter: Optional[Callable[[str], bool]] = None,
    auto_start: bool = True,
) -> Tuple["Observable[ProcessData]", ProcessDispatcher]:
    """顶层工厂函数：返回 (Observable[ProcessData], Dispatcher) 二元组。

    参数:
        interval: 轮询间隔（秒）
        include_system: 是否包含系统进程（pid <= 4）
        name_filter: 进程名过滤函数
        auto_start: 是否自动启动监控

    返回:
        Tuple[Observable[ProcessData], ProcessDispatcher]:
            事件流和分发器

    示例:
        >>> obs, disp = from_process(interval=0.5)
        >>> obs.pipe(
        ...     ops.filter(lambda x: "notepad" in x.name.lower()),
        ... ).subscribe(on_next=lambda x: print(f"{x.event_type.name}: {x.name}"))
    """
    disp = ProcessDispatcher(
        interval=interval,
        include_system=include_system,
        name_filter=name_filter,
    )
    if auto_start:
        disp.start()
    return disp.subject, disp


# ═══════════════════════════════════════════════════════════
#   响应式操作符
# ═══════════════════════════════════════════════════════════


class _WriteProcessOperator:
    """进程写入操作符。"""

    def __init__(self, dispatcher: ProcessDispatcher) -> None:
        self._dispatcher = dispatcher

    def __call__(self, source: "Observable[Any]") -> "Observable[ProcessData]":
        from ..core.observable import Observable

        def subscribe(observer: "Observer[ProcessData]") -> "Subscription":
            def on_next(item: Any) -> None:
                try:
                    result: Optional[ProcessData] = None
                    if isinstance(item, ProcessData):
                        # 根据事件类型执行操作
                        if item.event_type == ProcessChangeType.EXITED:
                            # 终止进程
                            if self._dispatcher.terminate(item.pid):
                                result = item
                        else:
                            result = item
                    elif isinstance(item, dict):
                        # 字典格式：{"action": "terminate", "pid": 123}
                        action = item.get("action")
                        pid = item.get("pid", 0)
                        if action == "terminate" and pid:
                            if self._dispatcher.terminate(pid):
                                result = ProcessData.now(
                                    pid=pid, name="", event_type=ProcessChangeType.EXITED
                                )
                    elif isinstance(item, int):
                        # 整数视为 pid，执行终止
                        if self._dispatcher.terminate(item):
                            result = ProcessData.now(
                                pid=item, name="", event_type=ProcessChangeType.EXITED
                            )

                    if result:
                        observer.on_next(result)
                except Exception as e:
                    try:
                        observer.on_error(e)
                    except Exception:
                        pass

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error if hasattr(observer, "on_error") else None,
                on_completed=(
                    observer.on_completed if hasattr(observer, "on_completed") else None
                ),
            )

        return Observable(subscribe)


def write_to_process(
    dispatcher: ProcessDispatcher,
) -> Callable[["Observable[Any]"], "Observable[ProcessData]"]:
    """响应式操作符：处理进程控制请求。

    支持的输入格式:
        ProcessData: 根据事件类型执行操作（EXITED 时终止进程）
        dict: {"action": "terminate", "pid": 123}
        int: 直接视为 pid，执行终止

    参数:
        dispatcher: ProcessDispatcher 实例

    返回:
        Operator 函数
    """
    return _WriteProcessOperator(dispatcher)