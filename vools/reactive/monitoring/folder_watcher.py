"""vools-reactive.folder_watcher - 文件夹级监控与分发器

核心公共 API:
    FolderChangeType(IntEnum):       目录变更类型枚举
    FolderData:                      结构化目录事件数据（支持 JSON/Pickle 往返）
    FolderDispatcher:                目录监控与分发器（Windows win32 / macOS FSEvents / Linux inotify）
    FolderSubject:                   带目录监控的 Subject（继承 Subject[FolderData]）
    FolderObserver:                  按 FolderChangeType 路由回调的观察者
    from_foldersystem(...):          顶层工厂：返回 (Observable[FolderData], FolderDispatcher)
    write_to_foldersystem(...):      响应式操作符：把流内容写入文件系统，并产生 FolderData 事件

事件驱动，非轮询:
    Windows: ReadDirectoryChangesW + I/O Completion Port + 后台线程（过滤目录事件）
    macOS:   FSEvents API + 后台线程（过滤 itemIsDir 标志）
    Linux:   inotify_init / inotify_add_watch + select.epoll（过滤 IN_ISDIR 标志）
    其他平台: polling 保底路径
"""

import base64
import ctypes
import hashlib
import itertools
import json
import logging
import os
import pickle
import struct
import sys
import threading
import time
from collections import deque
from ctypes import wintypes as wt
from vools.core.dataclass_compat import dataclass
from datetime import datetime
from enum import IntEnum
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from ..core.subject import Subject
from ..core.observable import Observable
from .monitor_subject import MonitorSubject
from .monitor_observer import MonitorObserver


log = logging.getLogger("vools.folder_watcher")

T = TypeVar("T")
R = TypeVar("R")


# ====================================================================
# 数据类型: FolderChangeType / FolderData
# ====================================================================


class FolderChangeType(IntEnum):
    """目录变更类型枚举。"""

    FOLDER_CREATED = 0      # 目录被创建
    FOLDER_DELETED = 1      # 目录被删除
    FOLDER_RENAMED = 2      # 目录被重命名（old_path → new_path）
    FOLDER_MOVED_IN = 3     # 目录从外部移入监控范围
    FOLDER_MOVED_OUT = 4    # 目录从监控范围中移出
    FOLDER_ATTRIB = 5       # 目录属性变化（权限/时间戳）
    FOLDER_CONTENT = 6      # 目录内容变化（新增/删除文件/子目录，未触发以上具体类型）

    def __str__(self) -> str:
        return self.name
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



# FolderData 用的全局单调序号
_seq_counter = itertools.count(1)


@dataclass(slots=True)  # type: ignore[call-overload]
class FolderData:
    """目录变化事件数据。

    字段:
        path: 触发变更的目录的完整路径
        old_path: 重命名时旧目录路径；其他情况 None
        change_type: 变更类型（FolderChangeType）
        file_count: 目录下的文件数量（统计快照，若无则 None）
        child_folder_count: 目录下的子目录数量（统计快照，若无则 None）
        timestamp: 检测到变更的时间
        sequence: 全局序号（单调递增）
        tags: 用户自定义标签
        metadata: 扩展元信息
    """

    path: str
    old_path: Optional[str]
    change_type: FolderChangeType
    file_count: Optional[int]
    child_folder_count: Optional[int]
    timestamp: datetime
    sequence: int
    tags: List[str]
    metadata: Dict[str, Any]

    # ---- 工厂 --------------------------------------------------------
    @classmethod
    def now(
        cls,
        path: str,
        old_path: Optional[str] = None,
        change_type: FolderChangeType = FolderChangeType.FOLDER_CONTENT,
        file_count: Optional[int] = None,
        child_folder_count: Optional[int] = None,
        tags: Iterable[str] = (),
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "FolderData":
        return cls(
            path=path,
            old_path=old_path,
            change_type=change_type,
            file_count=file_count,
            child_folder_count=child_folder_count,
            timestamp=datetime.now(),
            sequence=next(_seq_counter),
            tags=list(tags or ()),
            metadata=dict(metadata or {}),
        )

    # ---- 序列化 ------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        ts = self.timestamp
        if isinstance(ts, datetime):
            ts_str = ts.isoformat()
        elif isinstance(ts, (int, float)):
            ts_str = datetime.fromtimestamp(float(ts)).isoformat()
        else:
            ts_str = datetime.now().isoformat()
        return {
            "path": self.path,
            "old_path": self.old_path,
            "change_type": int(self.change_type),
            "change_type_name": str(self.change_type),
            "file_count": self.file_count,
            "child_folder_count": self.child_folder_count,
            "timestamp": ts_str,
            "sequence": self.sequence,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FolderData":
        d = dict(data or {})

        ct_raw = d.get("change_type", FolderChangeType.FOLDER_CONTENT.value)
        try:
            ct = FolderChangeType(int(ct_raw))
        except (TypeError, ValueError):
            try:
                ct = FolderChangeType[str(ct_raw).upper()]
            except KeyError:
                ct = FolderChangeType.FOLDER_CONTENT

        for k in ("change_type_name",):
            d.pop(k, None)

        ts = d.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = datetime.now()
        elif isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(float(ts))
        elif not isinstance(ts, datetime):
            ts = datetime.now()

        return cls(
            path=d.get("path", ""),
            old_path=d.get("old_path"),
            change_type=ct,
            file_count=d.get("file_count"),
            child_folder_count=d.get("child_folder_count"),
            timestamp=ts,
            sequence=int(d.get("sequence", next(_seq_counter))),
            tags=list(d.get("tags") or []),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, **kw: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kw)

    @classmethod
    def from_json(cls, s: str, **kw: Any) -> "FolderData":
        return cls.from_dict(json.loads(s, **kw))

    def to_pickle(self) -> bytes:
        return pickle.dumps(self)

    @classmethod
    def from_pickle(cls, b: bytes) -> "FolderData":
        return pickle.loads(b)

    # ---- 表示 --------------------------------------------------------

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
    def __str__(self) -> str:
        parts = [f"FolderData(path={self.path!r}"]
        if self.old_path:
            parts.append(f"old_path={self.old_path!r}")
        parts.append(f"change_type={self.change_type.name}")
        if self.file_count is not None:
            parts.append(f"file_count={self.file_count}")
        if self.child_folder_count is not None:
            parts.append(f"child_folders={self.child_folder_count}")
        parts.append(f"seq={self.sequence})")
        return " ".join(parts)


# ====================================================================
# 签名计算：用于去重
# ====================================================================


def _make_signature(
    change_type: FolderChangeType,
    path: str,
) -> Tuple[int, str]:
    key = (int(change_type), os.path.normpath(path))
    return hashlib.md5(repr(key).encode("utf-8")).hexdigest(), int(change_type)


# ====================================================================
# 后端: Windows Win32 / macOS FSEvents / Linux inotify / Polling
# ====================================================================


class _Win32WatchBackend:
    """Windows 下基于 ReadDirectoryChangesW + I/O Completion Port 的目录监控后端。

    仅分发目录相关事件（通过 FILE_NOTIFY_CHANGE_DIR_NAME + os.path.isdir 二次确认）。
    """

    name = "win32"

    def __init__(
        self,
        on_change: Callable[[str, Optional[str], FolderChangeType, bool], None],
        paths: Optional[Iterable[str]] = None,
        change_types: Optional[Iterable[FolderChangeType]] = None,
        interval: float = 0.2,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types_allowed: Optional[set] = (
            set(change_types) if change_types else None
        )
        self._interval = max(0.02, float(interval))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        self._kernel32 = ctypes.windll.kernel32
        # 保存已打开的目录句柄，供 CancelIoEx 取消挂起的 ReadDirectoryChangesW
        self._open_handles: List[int] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._open_handles = []
            self._running = True
            self._thread = threading.Thread(
                target=self._run, name="vools-folder-win32", daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        local_thread: Optional[threading.Thread] = None
        local_handles: List[int] = []
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop.set()
            local_thread = self._thread
            local_handles = list(self._open_handles)

        # 取消挂起的同步 ReadDirectoryChangesW（它阻塞在工作线程里）
        if local_handles:
            try:
                kernel32 = self._kernel32
                # 设置 argtypes/restype，避免 64-bit 指针截断
                if not hasattr(kernel32, "__CancelIoExSetupDone"):
                    kernel32.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                    kernel32.CancelIoEx.restype = wt.BOOL
                    kernel32.__CancelIoExSetupDone = True  # type: ignore[attr-defined]
                for h in local_handles:
                    try:
                        kernel32.CancelIoEx(h, None)
                    except Exception:
                        pass
            except Exception:
                pass

        if local_thread and local_thread.is_alive():
            local_thread.join(timeout=max(1.5, self._interval * 3 + 0.5))

    def _run(self) -> None:
        kernel32 = self._kernel32

        # ---- 常量 ----
        FILE_ACTION_ADDED = 1
        FILE_ACTION_REMOVED = 2
        FILE_ACTION_MODIFIED = 3
        FILE_ACTION_RENAMED_OLD_NAME = 4
        FILE_ACTION_RENAMED_NEW_NAME = 5
        INVALID_HANDLE_VALUE = -1

        FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
        FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
        FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x00000004
        FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010

        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 1
        FILE_SHARE_WRITE = 2
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

        BUFFER_SIZE = 65536
        FILTER = (
            FILE_NOTIFY_CHANGE_FILE_NAME
            | FILE_NOTIFY_CHANGE_DIR_NAME
            | FILE_NOTIFY_CHANGE_ATTRIBUTES
            | FILE_NOTIFY_CHANGE_LAST_WRITE
        )

        # ---- ctypes setup ----
        kernel32.CreateFileW.argtypes = [
            wt.LPCWSTR, wt.DWORD, wt.DWORD,
            ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p,
        ]
        kernel32.CreateFileW.restype = ctypes.c_void_p

        kernel32.ReadDirectoryChangesW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, wt.BOOL,
            wt.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        kernel32.ReadDirectoryChangesW.restype = wt.BOOL

        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = wt.BOOL

        try:
            kernel32.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            kernel32.CancelIoEx.restype = wt.BOOL
        except Exception:
            pass

        ERROR_OPERATION_ABORTED = 995

        # ---- 打开所有目录句柄 ----
        per_dir_handles: List[Tuple[int, str]] = []
        for path_str in self._paths:
            abs_path = os.path.abspath(path_str)
            hDir = kernel32.CreateFileW(
                abs_path,
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )
            if hDir == INVALID_HANDLE_VALUE:
                log.debug("无法打开目录 %s", abs_path)
                continue
            per_dir_handles.append((hDir, abs_path))

        # 原子写入 self._open_handles（外部 stop 可能并发访问）
        with self._lock:
            self._open_handles = [h for h, _ in per_dir_handles]

        if not per_dir_handles:
            self._running = False
            return

        # ---- 为每个目录启动一个监听线程 ----
        threads: List[threading.Thread] = []
        inner_stop = threading.Event()

        def _watch_one(hDir: int, base_path: str) -> None:
            # 跟踪已知的目录名（用 basename 跟踪删除/重命名事件）
            known_dirs: set = set()
            # 初始化：扫描一次现有子目录
            try:
                for name in os.listdir(base_path):
                    try:
                        if os.path.isdir(os.path.join(base_path, name)):
                            known_dirs.add(name)
                    except OSError:
                        pass
            except OSError:
                pass

            pending_old: Optional[str] = None

            while not inner_stop.is_set():
                buffer = ctypes.create_string_buffer(BUFFER_SIZE)
                bytes_returned = wt.DWORD()

                result = kernel32.ReadDirectoryChangesW(
                    hDir,
                    ctypes.byref(buffer),
                    BUFFER_SIZE,
                    True,
                    FILTER,
                    ctypes.byref(bytes_returned),
                    None,
                    None,
                )

                if inner_stop.is_set():
                    break

                if result == 0:
                    # I/O 被取消或失败 → 退出
                    last_err = 0
                    try:
                        last_err = kernel32.GetLastError()
                    except Exception:
                        last_err = 0
                    if last_err != ERROR_OPERATION_ABORTED:
                        log.debug(
                            "ReadDirectoryChangesW 返回 0 for %s (err=%s)",
                            base_path, last_err,
                        )
                    break

                # 解析 FILE_NOTIFY_INFORMATION 记录
                pos = 0
                raw_bytes = bytes(buffer.raw)
                while pos < bytes_returned.value:
                    next_offset = int.from_bytes(
                        raw_bytes[pos:pos + 4], 'little', signed=False
                    )
                    action = int.from_bytes(
                        raw_bytes[pos + 4:pos + 8], 'little', signed=False
                    )
                    fname_len = int.from_bytes(
                        raw_bytes[pos + 8:pos + 12], 'little', signed=False
                    )
                    fname_bytes = raw_bytes[pos + 12:pos + 12 + fname_len]
                    try:
                        fname = fname_bytes.decode('utf-16-le', errors='replace')
                    except Exception:
                        fname = ""

                    full_path = os.path.join(base_path, fname)

                    # 过滤：仅目录事件
                    # - action==1 (ADD): os.path.isdir 返回 True => 新目录创建
                    # - action==2 (REMOVE): 检查 known_dirs 中是否存在
                    # - action==3 (MODIFIED): 检查 is_dir
                    # - action==4 (OLD_NAME): 检查 known_dirs
                    # - action==5 (NEW_NAME): 检查 is_dir

                    is_dir = False
                    try:
                        is_dir = os.path.isdir(full_path)
                    except OSError:
                        is_dir = False

                    # 处理删除/重命名的跟踪
                    if action == FILE_ACTION_ADDED and is_dir:
                        known_dirs.add(fname)
                        try:
                            self._on_change(full_path, None, FolderChangeType.FOLDER_CREATED, True)
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)

                    elif action == FILE_ACTION_REMOVED and fname in known_dirs:
                        known_dirs.discard(fname)
                        try:
                            self._on_change(full_path, None, FolderChangeType.FOLDER_DELETED, True)
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)

                    elif action == FILE_ACTION_RENAMED_OLD_NAME and fname in known_dirs:
                        pending_old = full_path
                        known_dirs.discard(fname)

                    elif action == FILE_ACTION_RENAMED_NEW_NAME and is_dir:
                        known_dirs.add(fname)
                        try:
                            self._on_change(full_path, pending_old, FolderChangeType.FOLDER_RENAMED, True)
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)
                        pending_old = None

                    elif action == FILE_ACTION_MODIFIED and is_dir:
                        try:
                            self._on_change(full_path, None, FolderChangeType.FOLDER_CONTENT, True)
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)

                    if next_offset == 0:
                        break
                    pos += next_offset

        for hDir, abs_path in per_dir_handles:
            t = threading.Thread(
                target=_watch_one, args=(hDir, abs_path), daemon=True,
            )
            t.start()
            threads.append(t)

        # 等待所有线程
        try:
            while not self._stop.is_set():
                time.sleep(0.1)
        finally:
            inner_stop.set()
            # 清理句柄 - 先 CloseHandle 让线程退出
            for hDir, _ in per_dir_handles:
                try:
                    kernel32.CloseHandle(hDir)
                except Exception:
                    pass
            for t in threads:
                t.join(timeout=2)
            with self._lock:
                self._open_handles = []
            self._running = False
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



class _MacWatchBackend:
    """macOS 下基于 FSEvents API 的目录监控后端（stub）。

    不可用时将抛出异常，FolderDispatcher 会回退到 polling 后端。
    """

    name = "macos"

    def __init__(
        self,
        on_change: Callable[[str, Optional[str], FolderChangeType, bool], None],
        paths: Optional[Iterable[str]] = None,
        change_types: Optional[Iterable[FolderChangeType]] = None,
        interval: float = 0.2,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types_allowed: Optional[set] = (
            set(change_types) if change_types else None
        )
        self._interval = max(0.02, float(interval))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run, name="vools-folder-macos", daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval * 3 + 0.5)

    def _run(self) -> None:
        raise OSError("macOS FSEvents not implemented")
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



class _InotifyWatchBackend:
    """Linux 下基于 inotify + epoll 的目录监控后端。

    通过 IN_ISDIR 掩码位过滤目录事件。
    """

    name = "inotify"

    def __init__(
        self,
        on_change: Callable[[str, Optional[str], FolderChangeType, bool], None],
        paths: Optional[Iterable[str]] = None,
        change_types: Optional[Iterable[FolderChangeType]] = None,
        interval: float = 0.2,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types_allowed: Optional[set] = (
            set(change_types) if change_types else None
        )
        self._interval = max(0.02, float(interval))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run, name="vools-folder-inotify", daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval * 3 + 0.5)

    def _run(self) -> None:
        import select as _select

        try:
            _libc = ctypes.CDLL("libc.so.6", use_errno=True)
        except (OSError, AttributeError):
            try:
                _libc = ctypes.CDLL("libc.so.7", use_errno=True)
            except (OSError, AttributeError):
                log.debug("无法加载 libc")
                return

        # inotify constants
        IN_ISDIR = 0x40000000
        IN_CREATE = 0x00000100
        IN_DELETE = 0x00000200
        IN_MOVED_FROM = 0x00000040
        IN_MOVED_TO = 0x00000080
        IN_ATTRIB = 0x00000004
        IN_DELETE_SELF = 0x00000400
        IN_MOVE_SELF = 0x00000800
        IN_MODIFY = 0x00000002

        IN_ALL_EVENTS = (
            IN_CREATE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO
            | IN_ATTRIB | IN_DELETE_SELF | IN_MOVE_SELF | IN_MODIFY
        )

        # ctypes setup
        _libc.inotify_init.argtypes = []
        _libc.inotify_init.restype = ctypes.c_int
        _libc.inotify_add_watch.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32,
        ]
        _libc.inotify_add_watch.restype = ctypes.c_int
        _libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
        _libc.inotify_rm_watch.restype = ctypes.c_int
        _libc.close.argtypes = [ctypes.c_int]
        _libc.close.restype = ctypes.c_int

        fd = _libc.inotify_init()
        if fd < 0:
            log.debug("inotify_init 失败")
            return

        wd_map: Dict[int, str] = {}

        try:
            for p in self._paths:
                abs_p = os.path.abspath(p)
                if not os.path.exists(abs_p):
                    continue
                wd = _libc.inotify_add_watch(
                    fd, abs_p.encode("utf-8"), IN_ALL_EVENTS,
                )
                if wd >= 0:
                    wd_map[wd] = abs_p
                else:
                    log.debug("inotify_add_watch 失败 for %s", abs_p)

            if not wd_map:
                log.debug("没有有效监控路径")
                return

            ep = _select.epoll()
            ep.register(fd, _select.EPOLLIN)

            pending_moves: Dict[int, str] = {}

            import struct as _struct

            while not self._stop.is_set():
                try:
                    events = ep.poll(timeout=0.5)
                except OSError:
                    break

                for fd_, _event in events:
                    if fd_ != fd:
                        continue

                    buf_size = 8192
                    try:
                        data = os.read(fd, buf_size)
                    except OSError:
                        continue

                    pos = 0
                    while pos < len(data):
                        ev_size = 16
                        ev_data = data[pos:pos + ev_size]
                        if len(ev_data) < ev_size:
                            break

                        wd = _struct.unpack("i", ev_data[0:4])[0]
                        mask = _struct.unpack("I", ev_data[4:8])[0]
                        cookie = _struct.unpack("I", ev_data[8:12])[0]
                        name_len = _struct.unpack("I", ev_data[12:16])[0]

                        is_dir = bool(mask & IN_ISDIR)

                        # 只处理目录事件
                        if not is_dir:
                            if name_len > 0:
                                padded_len = ((name_len + 8) // 8) * 8
                                pos += ev_size + padded_len
                            else:
                                pos += ev_size
                            continue

                        name_bytes = b""
                        if name_len > 0:
                            name_end = pos + ev_size + name_len
                            if name_end <= len(data):
                                name_bytes = data[pos + ev_size:name_end].rstrip(b"\x00")
                            padded_len = ((name_len + 8) // 8) * 8
                            pos += ev_size + padded_len
                        else:
                            pos += ev_size

                        if wd not in wd_map:
                            continue

                        base_path = wd_map[wd]
                        file_name = (
                            name_bytes.decode("utf-8", errors="replace")
                            if name_bytes
                            else ""
                        )
                        full_path = (
                            os.path.join(base_path, file_name)
                            if file_name
                            else base_path
                        )

                        # 映射 mask -> FolderChangeType
                        if mask & IN_CREATE:
                            ct = FolderChangeType.FOLDER_CREATED
                        elif mask & IN_DELETE:
                            ct = FolderChangeType.FOLDER_DELETED
                        elif mask & IN_DELETE_SELF:
                            ct = FolderChangeType.FOLDER_DELETED
                        elif mask & IN_MOVE_SELF:
                            ct = FolderChangeType.FOLDER_MOVED_OUT
                        elif mask & IN_ATTRIB:
                            ct = FolderChangeType.FOLDER_ATTRIB
                        elif mask & IN_MOVED_FROM:
                            pending_moves[cookie] = full_path
                            # 不立即触发，等 MOVED_TO
                            continue
                        elif mask & IN_MOVED_TO:
                            if cookie in pending_moves:
                                old_path = pending_moves.pop(cookie)
                                ct = FolderChangeType.FOLDER_RENAMED
                            else:
                                ct = FolderChangeType.FOLDER_MOVED_IN
                                old_path = None
                        else:
                            ct = FolderChangeType.FOLDER_CONTENT

                        try:
                            self._on_change(
                                full_path,
                                old_path if ct == FolderChangeType.FOLDER_RENAMED else None,
                                ct,
                                True,
                            )
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)
        finally:
            try:
                ep.unregister(fd)
                ep.close()
            except Exception:
                pass
            _libc.close(fd)
            self._running = False
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



class _PollingWatchBackend:
    """其他平台的保底路径：定期扫描目录列表差异，只分发目录级事件。"""

    name = "polling"

    def __init__(
        self,
        on_change: Callable[[str, Optional[str], FolderChangeType, bool], None],
        paths: Optional[Iterable[str]] = None,
        change_types: Optional[Iterable[FolderChangeType]] = None,
        interval: float = 0.5,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types_allowed: Optional[set] = (
            set(change_types) if change_types else None
        )
        self._interval = max(0.02, float(interval))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run, name="vools-folder-polling", daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval * 3 + 0.5)

    def _run(self) -> None:
        # 状态: path -> set(子目录名称)
        state: Dict[str, set] = {}

        def _scan_dir(base_path: str) -> set:
            result: set = set()
            try:
                for name in os.listdir(base_path):
                    full = os.path.join(base_path, name)
                    try:
                        if os.path.isdir(full):
                            result.add(name)
                    except OSError:
                        continue
            except Exception:
                pass
            return result

        # 初始扫描
        for path_str in self._paths:
            abs_path = os.path.abspath(path_str)
            state[abs_path] = _scan_dir(abs_path)

        # 记录所有已知子目录路径的存在状态（用于递归监测子目录创建/删除）
        known_child_dirs: Dict[str, bool] = {}
        for parent_path, children in list(state.items()):
            for name in children:
                known_child_dirs[os.path.join(parent_path, name)] = True

        try:
            while not self._stop.is_set():
                time.sleep(self._interval)

                for path_str in list(self._paths):
                    abs_path = os.path.abspath(path_str)
                    current = _scan_dir(abs_path)
                    prev = state.get(abs_path, set())

                    # 新增子目录
                    for name in current - prev:
                        full = os.path.join(abs_path, name)
                        if full not in known_child_dirs:
                            try:
                                self._on_change(
                                    full, None, FolderChangeType.FOLDER_CREATED, True,
                                )
                            except Exception as e:
                                log.debug("on_change 异常: %s", e)
                            known_child_dirs[full] = True

                    # 删除子目录
                    for name in prev - current:
                        full = os.path.join(abs_path, name)
                        if full in known_child_dirs:
                            try:
                                self._on_change(
                                    full, None, FolderChangeType.FOLDER_DELETED, True,
                                )
                            except Exception as e:
                                log.debug("on_change 异常: %s", e)
                            del known_child_dirs[full]

                    state[abs_path] = current
        finally:
            self._running = False
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



# ====================================================================
# FolderDispatcher: 主入口
# ====================================================================


class FolderDispatcher:
    """目录级监控与分发器。

    典型用法:
        >>> d = FolderDispatcher(paths=["./src"])
        >>> d.subject.pipe(
        ...     ops.filter(lambda f: f.change_type == FolderChangeType.FOLDER_CREATED),
        ... ).subscribe(on_next=lambda f: print("新增目录:", f.path))
        >>> d.start()
        >>> d.stop()

    或作为上下文管理器:
        >>> with FolderDispatcher(paths=["./src"]) as d:
        ...     d.subject.subscribe(on_next=print)
    """

    __slots__ = (
        "_backend",
        "_subject",
        "_lock",
        "_paths",
        "_change_types_allowed",
        "_tags",
        "_interval",
        "_dispatch_count",
        "_error_count",
        "_backend_name",
        "_running",
        "filter_self",
        "_self_signatures",
        "_self_filtered_count",
        "_self_signature_capacity",
    )

    def __init__(
        self,
        *,
        paths: Optional[Iterable[str]] = None,
        backend: str = "auto",
        change_types: Optional[Iterable[FolderChangeType]] = None,
        tags: Iterable[str] = (),
        interval: float = 0.5,
        filter_self: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._paths: List[str] = list(paths) if paths else []
        self._change_types_allowed: Optional[set] = (
            set(change_types) if change_types else None
        )
        self._tags: List[str] = list(tags or ())
        self._interval = max(0.02, float(interval))
        self._dispatch_count = 0
        self._error_count = 0
        self.filter_self = bool(filter_self)
        self._self_signatures: set = set()
        self._self_filtered_count = 0
        self._self_signature_capacity = 32

        self._subject: Subject[FolderData] = Subject()

        backend = (backend or "auto").lower()
        be: Optional[Any] = None
        self._backend_name = "polling"

        if backend in ("auto", "win32") and sys.platform == "win32":
            try:
                be = _Win32WatchBackend(
                    self._dispatch_once,
                    paths=self._paths,
                    change_types=self._change_types_allowed,
                    interval=self._interval,
                )
                self._backend_name = "win32"
            except Exception as e:
                log.debug("win32 后端不可用，回退到 polling: %s", e)
                be = None

        elif backend in ("auto", "macos") and sys.platform == "darwin":
            try:
                be = _MacWatchBackend(
                    self._dispatch_once,
                    paths=self._paths,
                    change_types=self._change_types_allowed,
                    interval=self._interval,
                )
                self._backend_name = "macos"
            except Exception as e:
                log.debug("macOS 后端不可用，回退到 polling: %s", e)
                be = None

        elif backend in ("auto", "inotify") and sys.platform.startswith("linux"):
            try:
                be = _InotifyWatchBackend(
                    self._dispatch_once,
                    paths=self._paths,
                    change_types=self._change_types_allowed,
                    interval=self._interval,
                )
                self._backend_name = "inotify"
            except Exception as e:
                log.debug("inotify 后端不可用，回退到 polling: %s", e)
                be = None

        if be is None:
            be = _PollingWatchBackend(
                self._dispatch_once,
                paths=self._paths,
                change_types=self._change_types_allowed,
                interval=self._interval,
            )
            self._backend_name = "polling"

        self._backend: Any = be
        self._running = False

    # ---- 属性 --------------------------------------------------------
    @property
    def subject(self) -> Subject[FolderData]:
        return self._subject

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def dispatch_count(self) -> int:
        return self._dispatch_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def is_running(self) -> bool:
        return self._running and bool(getattr(self._backend, "is_running", False))

    # ---- 生命周期 ----------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._running and getattr(self._backend, "is_running", False):
                return
            self._backend.start()
            self._running = True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            try:
                self._backend.stop()
            except Exception:
                pass

    def __enter__(self) -> "FolderDispatcher":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    # ---- 路径增删 ----------------------------------------------------
    def add_path(self, path: str) -> None:
        """动态添加监控路径。"""
        self._paths.append(os.path.abspath(path))

    def remove_path(self, path: str) -> None:
        """动态移除监控路径。"""
        abs_path = os.path.abspath(path)
        if abs_path in self._paths:
            self._paths.remove(abs_path)

    # ---- 签名生成 ----------------------------------------------------
    def _make_signature(
        self,
        path: str,
        change_type: FolderChangeType,
    ) -> str:
        """生成目录事件的签名，用于自过滤"""
        data = f"{path}:{change_type.value}"
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    def register_self_signature(self, path: str, change_type: FolderChangeType) -> None:
        """注册自修改签名，这些签名对应的事件会被过滤"""
        sig = self._make_signature(path, change_type)
        with self._lock:
            self._self_signatures.add(sig)
            if len(self._self_signatures) > self._self_signature_capacity:
                self._self_signatures = set(list(self._self_signatures)[-self._self_signature_capacity:])

    # ---- 核心：一次分发 ----------------------------------------------
    def _dispatch_once(
        self,
        path: str,
        old_path: Optional[str],
        change_type: FolderChangeType,
        is_directory: bool,
    ) -> None:
        if (
            self._change_types_allowed is not None
            and change_type not in self._change_types_allowed
        ):
            return

        # 自过滤：命中签名 → 丢弃
        if self.filter_self:
            sig = self._make_signature(path, change_type)
            with self._lock:
                if sig in self._self_signatures:
                    self._self_signatures.discard(sig)
                    self._self_filtered_count += 1
                    log.debug("自过滤目录事件: %s %s", change_type.name, path)
                    return

        try:
            fd = FolderData.now(
                path=path,
                old_path=old_path,
                change_type=change_type,
                tags=self._tags,
            )
            self._subject.on_next(fd)
            self._dispatch_count += 1
        except Exception as e:
            log.debug("subject.on_next 异常: %s", e)
            self._error_count += 1


# ====================================================================
# 顶层工厂 & 操作符
# ====================================================================


def from_foldersystem(
    *,
    paths: Optional[Iterable[str]] = None,
    backend: str = "auto",
    change_types: Optional[Iterable[FolderChangeType]] = None,
    tags: Iterable[str] = (),
    interval: float = 0.5,
    auto_start: bool = True,
) -> Tuple[Any, FolderDispatcher]:
    """顶层工厂函数：返回 (Observable[FolderData], FolderDispatcher) 二元组。

    Usage:
        >>> obs, d = from_foldersystem(paths=["./src"])
        >>> obs.pipe(
        ...     ops.filter(lambda f: f.change_type == FolderChangeType.FOLDER_CREATED),
        ... ).subscribe(on_next=lambda f: print("新增目录:", f.path))
    """
    d = FolderDispatcher(
        paths=paths,
        backend=backend,
        change_types=change_types,
        tags=tags,
        interval=interval,
    )
    if auto_start:
        d.start()
    return d.subject, d


def write_to_foldersystem(
    dispatcher: FolderDispatcher,
    mode: str = "create",
) -> Callable[[Observable[Any]], Observable[FolderData]]:
    """响应式操作符：把上游每一项写入文件系统，并把构造的 FolderData 继续下发。

    上游可接受:
        FolderData → 用其 path/change_type/metadata 写入
        str        → 作为目录路径（会被创建）
        dict       → {"path", "content", "change_type", "tags", "metadata"}
        tuple/list → (path, content) 或 (path, content, change_type)
    """

    def operator(source_observable: Observable[Any]) -> Observable[FolderData]:
        def subscribe(observer: Any) -> Any:
            def on_next(item: Any) -> None:
                try:
                    path: str = ""
                    content: Union[str, bytes] = ""
                    ct: FolderChangeType = FolderChangeType.FOLDER_CONTENT
                    tags: List[str] = []
                    meta: Dict[str, Any] = {}

                    if isinstance(item, FolderData):
                        path = item.path
                        ct = item.change_type
                        tags = list(item.tags)
                        meta = dict(item.metadata)
                    elif isinstance(item, str):
                        path = item
                    elif isinstance(item, dict):
                        path = item.get("path", "")
                        content = item.get("content", "")
                        ct = item.get("change_type", FolderChangeType.FOLDER_CONTENT)
                        tags = list(item.get("tags") or [])
                        meta = dict(item.get("metadata") or {})
                    elif isinstance(item, (list, tuple)):
                        items = list(item)
                        path = items[0] if items else ""
                        content = items[1] if len(items) > 1 else ""
                        if len(items) > 2:
                            ct = items[2]
                    else:
                        path = str(item)

                    if path:
                        try:
                            # 创建目录
                            if mode == "create" or not os.path.exists(path):
                                os.makedirs(path, exist_ok=True)
                                ct = FolderChangeType.FOLDER_CREATED
                            else:
                                ct = FolderChangeType.FOLDER_CONTENT

                            fd = FolderData.now(
                                path=path,
                                old_path=None,
                                change_type=ct,
                                tags=tags,
                                metadata=meta,
                            )
                            observer.on_next(fd)
                        except Exception as e:
                            log.debug("write_to_foldersystem 写入异常: %s", e)
                            try:
                                observer.on_error(e)
                            except Exception:
                                pass
                            return
                except Exception as e:
                    dispatcher._error_count += 1
                    try:
                        observer.on_error(e)
                    except Exception:
                        pass

            return source_observable.subscribe_(
                on_next=on_next,
                on_error=(
                    observer.on_error if hasattr(observer, "on_error") else None
                ),
                on_completed=(
                    observer.on_completed if hasattr(observer, "on_completed") else None
                ),
            )

        return Observable(subscribe)

    return operator


# ====================================================================
# FolderSubject: 自包含 Dispatcher 的 Subject
# ====================================================================


class FolderSubject(MonitorSubject):
    """文件夹监控主题（Subject），继承 MonitorSubject。

    内部持有 FolderDispatcher，提供文件夹变更事件流。
    """
    def __init__(
        self,
        *,
        paths: Optional[Any] = None,
        backend: str = "auto",
        interval: float = 0.5,
        tags: Tuple[str, ...] = (),
        change_types: Optional[Any] = None,
        auto_start: bool = False,
        filter_self: bool = False,
    ) -> None:
        """初始化文件夹监控主题。

        Args:
            paths: 监控路径列表
            backend: 后端类型，"auto" | "win32" | "macos" | "inotify" | "polling"
            interval: 轮询间隔（秒）
            tags: 默认附加的标签
            change_types: 白名单；仅分发列出的 FolderChangeType
            auto_start: 是否在构造时自动启动
            filter_self: 是否启用自过滤
        """
        self._paths = paths
        self._backend = backend
        self._interval = interval
        self._tags = tags
        self._change_types = change_types
        self._auto_start = auto_start
        self._filter_self = filter_self
        super().__init__()
        if auto_start:
            self.start()

    def _create_dispatcher(self) -> "FolderDispatcher":
        return FolderDispatcher(
            paths=self._paths,
            backend=self._backend,
            interval=self._interval,
            tags=self._tags,
            change_types=self._change_types,
            filter_self=self._filter_self,
        )

    def _connect_dispatcher(self) -> None:
        self._conn_sub = self._dispatcher.subject.subscribe(
            on_next=self.on_next,
            on_error=self.on_error,
            on_completed=self.on_completed,
        )

    @property
    def dispatcher(self) -> "FolderDispatcher":
        return self._dispatcher

    @property
    def subject(self) -> "Subject[FolderData]":
        return self

    @property
    def dispatch_count(self) -> int:
        return self._dispatcher.dispatch_count

    @property
    def backend_name(self) -> str:
        return self._dispatcher.backend_name

    def __enter__(self) -> "FolderSubject":
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


class FolderObserver(MonitorObserver):
    """
    文件夹事件观察者，按 FolderChangeType 路由回调。

    Args:
        on_folder_created: FOLDER_CREATED 回调
        on_folder_deleted: FOLDER_DELETED 回调
        on_folder_renamed: FOLDER_RENAMED 回调
        on_folder_moved_in: FOLDER_MOVED_IN 回调
        on_folder_moved_out: FOLDER_MOVED_OUT 回调
        on_folder_attrib: FOLDER_ATTRIB 回调
        on_folder_content: FOLDER_CONTENT 回调
        on_any: 任意事件回调
        on_error: 错误回调
        on_completed: 完成回调
    """

    def __init__(
        self,
        *,
        on_folder_created: Optional[Callable[[FolderData], Any]] = None,
        on_folder_deleted: Optional[Callable[[FolderData], Any]] = None,
        on_folder_renamed: Optional[Callable[[FolderData], Any]] = None,
        on_folder_moved_in: Optional[Callable[[FolderData], Any]] = None,
        on_folder_moved_out: Optional[Callable[[FolderData], Any]] = None,
        on_folder_attrib: Optional[Callable[[FolderData], Any]] = None,
        on_folder_content: Optional[Callable[[FolderData], Any]] = None,
        on_any: Optional[Callable[[FolderData], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            on_any=on_any, on_error=on_error, on_completed=on_completed,
        )
        self._on_folder_created = on_folder_created
        self._on_folder_deleted = on_folder_deleted
        self._on_folder_renamed = on_folder_renamed
        self._on_folder_moved_in = on_folder_moved_in
        self._on_folder_moved_out = on_folder_moved_out
        self._on_folder_attrib = on_folder_attrib
        self._on_folder_content = on_folder_content

    def _event_type_of(self, value: Any) -> Any:
        return FolderChangeType(value.change_type)

    def _handler_for(self, event_type: Any) -> Optional[Callable[[Any], Any]]:
        if event_type == FolderChangeType.FOLDER_CREATED:
            return self._on_folder_created
        if event_type == FolderChangeType.FOLDER_DELETED:
            return self._on_folder_deleted
        if event_type == FolderChangeType.FOLDER_RENAMED:
            return self._on_folder_renamed
        if event_type == FolderChangeType.FOLDER_MOVED_IN:
            return self._on_folder_moved_in
        if event_type == FolderChangeType.FOLDER_MOVED_OUT:
            return self._on_folder_moved_out
        if event_type == FolderChangeType.FOLDER_ATTRIB:
            return self._on_folder_attrib
        if event_type == FolderChangeType.FOLDER_CONTENT:
            return self._on_folder_content
        return None

    def _on_next(self, fd: "FolderData") -> None:
        self.on_next(fd)

    def __enter__(self) -> "FolderObserver":
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

# ====================================================================

__all__ = [
    "FolderChangeType",
    "FolderData",
    "FolderDispatcher",
    "FolderSubject",
    "FolderObserver",
    "from_foldersystem",
    "write_to_foldersystem",
]
