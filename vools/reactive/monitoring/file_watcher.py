"""
vools-reactive.file_watcher - 文件系统监控与分发器

核心公共 API:
    FileChangeType(IntEnum):       文件变更类型枚举
    FileData:                      结构化文件事件数据（支持 JSON/Pickle 往返）
    FileDispatcher:                文件系统监控与分发器（Windows Win32 / macOS FSEvents / Linux inotify）
    FileSubject:                   带文件监控的 Subject（继承 Subject[FileData]）
    FileObserver:                  按 FileChangeType 路由回调的观察者
    from_filesystem(...):          顶层工厂：返回 (Observable[FileData], FileDispatcher)
    write_to_filesystem(...):      响应式操作符：把流内容写入文件系统

Windows 下使用 ReadDirectoryChangesW + OVERLAPPED I/O + 隐藏窗口消息循环（纯 ctypes）；
macOS 下使用 FSEvents API（纯 ctypes）；
Linux 下使用 inotify_init / inotify_add_watch + epoll（纯 ctypes）；
其它平台回落到 polling 后端。
"""

from __future__ import annotations

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
from dataclasses import dataclass
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
)

from ..core.subject import Subject
from ..core.observable import Observable
from .monitor_subject import MonitorSubject
from .monitor_observer import MonitorObserver


log = logging.getLogger("vools.file_watcher")

T = TypeVar("T")
R = TypeVar("R")

# ====================================================================
# 数据类型：FileChangeType / FileData
# ====================================================================


class FileChangeType(IntEnum):
    """文件变更类型枚举。"""

    CREATED = 0      # 文件/目录被创建
    MODIFIED = 1     # 文件内容被修改
    DELETED = 2      # 文件/目录被删除
    RENAMED = 3      # 文件/目录被重命名（old_path → new_path）
    MOVED_IN = 4     # 文件从监控目录外移入
    MOVED_OUT = 5    # 文件从监控目录移出
    ACCESS = 6       # 文件被读取
    ATTRIB = 7       # 文件属性/元数据变化

    def __str__(self) -> str:
        return self.name


# FileData 用的全局单调序号
_seq_counter = itertools.count(1)


@dataclass(slots=True)  # type: ignore[call-overload]
class FileData:
    """结构化的文件事件数据。

    字段:
        path:           触发变更的完整路径
        old_path:       重命名时旧路径；其它情况 None
        change_type:    变更类型（FileChangeType）
        is_directory:   是否为目录
        size:           变更后文件大小（删除时 None）
        timestamp:      检测到变更的时间
        sequence:       全局序号（单调递增）
        tags:           用户自定义标签
        metadata:       扩展元信息
    """

    path: str
    old_path: str | None
    change_type: FileChangeType
    is_directory: bool
    size: int | None
    timestamp: datetime
    sequence: int
    tags: List[str]
    metadata: Dict[str, Any]

    # ---- 工厂 --------------------------------------------------------
    @classmethod
    def now(
        cls,
        path: str,
        old_path: str | None = None,
        change_type: FileChangeType = FileChangeType.MODIFIED,
        is_directory: bool = False,
        size: int | None = None,
        tags: Iterable[str] = (),
        metadata: Dict[str, Any] | None = None,
    ) -> "FileData":
        return cls(
            path=path,
            old_path=old_path,
            change_type=change_type,
            is_directory=is_directory,
            size=size,
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
        data: Dict[str, Any] = {
            "path": self.path,
            "old_path": self.old_path,
            "change_type": int(self.change_type),
            "change_type_name": str(self.change_type),
            "is_directory": self.is_directory,
            "size": self.size,
            "timestamp": ts_str,
            "sequence": self.sequence,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileData":
        d = dict(data or {})

        ct_raw = d.get("change_type", FileChangeType.MODIFIED.value)
        try:
            ct = FileChangeType(int(ct_raw))
        except (TypeError, ValueError):
            try:
                ct = FileChangeType[str(ct_raw).upper()]
            except KeyError:
                ct = FileChangeType.MODIFIED

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
            is_directory=bool(d.get("is_directory", False)),
            size=d.get("size"),
            timestamp=ts,
            sequence=int(d.get("sequence", next(_seq_counter))),
            tags=list(d.get("tags") or []),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self, **kw: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kw)

    @classmethod
    def from_json(cls, s: str, **kw: Any) -> "FileData":
        return cls.from_dict(json.loads(s, **kw))

    def to_pickle(self) -> bytes:
        return pickle.dumps(self)

    @classmethod
    def from_pickle(cls, b: bytes) -> "FileData":
        return pickle.loads(b)

    # ---- 表示 --------------------------------------------------------
    def __str__(self) -> str:
        return (
            f"FileData(path={self.path!r}, change_type={self.change_type.name}, "
            f"is_directory={self.is_directory}, size={self.size}, "
            f"seq={self.sequence})"
        )


# ====================================================================
# 签名计算：用于去重与自过滤
# ====================================================================


def _make_signature(
    change_type: FileChangeType,
    path: str,
) -> Tuple[int, str]:
    """计算文件事件的稳定签名（用于去重）。"""
    key = (int(change_type), os.path.normpath(path))
    return hashlib.md5(repr(key).encode("utf-8")).hexdigest(), int(change_type)


# ====================================================================
# 后端：Windows Win32 / macOS FSEvents / Linux inotify / Polling
# ====================================================================


class _Win32WatchBackend:
    """Windows 下基于 ReadDirectoryChangesW + 隐藏窗口消息循环的文件监控后端。

    在一个单独的后台线程内：
      1) 为每个监控路径创建独立的 OVERLAPPED + 隐藏窗口
      2) 调用 ReadDirectoryChangesW 发起异步监控
      3) GetQueuedCompletionStatus 接收 I/O 完成事件
      4) 解析 FILE_NOTIFY_INFORMATION 结构，映射到 FileChangeType
      5) 回调 on_change(path, old_path, change_type, is_dir)

    （后续阶段填充实现细节。）
    """

    name = "win32"

    def __init__(
        self,
        on_change: Callable[[str, str | None, FileChangeType, bool], None],
        paths: Iterable[str] | None = None,
        change_types: Iterable[FileChangeType] | None = None,
        interval: float = 0.2,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types: Optional[set] = (
            set(change_types) if change_types else None
        )
        self._interval = max(0.02, float(interval))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        # 缓存 ctypes DLL 引用（供 _run 使用）
        self._kernel32 = ctypes.windll.kernel32
        self._user32 = ctypes.windll.user32
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
                target=self._run, name="vools-file-win32", daemon=True,
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
        # Windows Win32 实现: 同步 ReadDirectoryChangesW + 每个目录一个线程
        kernel32 = self._kernel32

        FILE_ACTION_ADDED = 1
        FILE_ACTION_REMOVED = 2
        FILE_ACTION_MODIFIED = 3
        FILE_ACTION_RENAMED_OLD_NAME = 4
        FILE_ACTION_RENAMED_NEW_NAME = 5
        INVALID_HANDLE_VALUE = -1

        FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
        FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
        FILE_NOTIFY_CHANGE_SIZE = 0x00000008
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
            | FILE_NOTIFY_CHANGE_SIZE
            | FILE_NOTIFY_CHANGE_LAST_WRITE
        )

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

        inner_stop = threading.Event()
        threads: List[threading.Thread] = []

        def _watch_one(hDir: int, base_path: str) -> None:
            # 重命名配对: old_name 事件后紧跟 new_name 事件
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

                raw_bytes = bytes(buffer.raw)
                pos = 0
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
                    fname = ""
                    try:
                        fname = raw_bytes[pos + 12:pos + 12 + fname_len].decode(
                            'utf-16-le', errors='replace'
                        )
                    except Exception:
                        pass

                    full_path = os.path.join(base_path, fname)

                    # 确定是否为目录
                    is_dir = False
                    try:
                        is_dir = os.path.isdir(full_path)
                    except OSError:
                        is_dir = False

                    if action == FILE_ACTION_ADDED:
                        try:
                            self._on_change(full_path, None, FileChangeType.CREATED, is_dir)
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)

                    elif action == FILE_ACTION_REMOVED:
                        try:
                            self._on_change(full_path, None, FileChangeType.DELETED, is_dir)
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)

                    elif action == FILE_ACTION_MODIFIED:
                        try:
                            self._on_change(full_path, None, FileChangeType.MODIFIED, is_dir)
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)

                    elif action == FILE_ACTION_RENAMED_OLD_NAME:
                        pending_old = full_path

                    elif action == FILE_ACTION_RENAMED_NEW_NAME:
                        try:
                            self._on_change(
                                full_path, pending_old, FileChangeType.RENAMED, is_dir
                            )
                        except Exception as e:
                            log.debug("on_change 异常: %s", e)
                        pending_old = None

                    if next_offset == 0:
                        break
                    pos += next_offset

        for hDir, abs_path in per_dir_handles:
            t = threading.Thread(
                target=_watch_one, args=(hDir, abs_path), daemon=True,
            )
            t.start()
            threads.append(t)

        try:
            while not self._stop.is_set():
                time.sleep(0.1)
        finally:
            inner_stop.set()
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


class _MacWatchBackend:
    """macOS 下基于 FSEvents API 的文件监控后端。

    （后续阶段填充实现细节。）
    """

    name = "macos"

    def __init__(
        self,
        on_change: Callable[[str, str | None, FileChangeType, bool], None],
        paths: Iterable[str] | None = None,
        change_types: Iterable[FileChangeType] | None = None,
        interval: float = 0.2,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types: Optional[set] = (
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
                target=self._run, name="vools-file-macos", daemon=True,
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
        # stub - macOS FSEvents requires CoreFoundation C API which needs additional ctypes binding work
        raise OSError("macOS FSEvents not implemented")


class _InotifyWatchBackend:
    """Linux 下基于 inotify_init / inotify_add_watch + epoll 的文件监控后端。

    （后续阶段填充实现细节。）
    """

    name = "inotify"

    def __init__(
        self,
        on_change: Callable[[str, str | None, FileChangeType, bool], None],
        paths: Iterable[str] | None = None,
        change_types: Iterable[FileChangeType] | None = None,
        interval: float = 0.2,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types: Optional[set] = (
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
                target=self._run, name="vools-file-inotify", daemon=True,
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

        # ctypes for libc (Linux)
        try:
            _libc = ctypes.CDLL("libc.so.6", use_errno=True)
        except (OSError, AttributeError):
            try:
                _libc = ctypes.CDLL("libc.so.7", use_errno=True)
            except (OSError, AttributeError):
                log.debug("无法加载 libc")
                return

        # inotify constants
        IN_ACCESS = 0x00000001
        IN_MODIFY = 0x00000002
        IN_ATTRIB = 0x00000004
        IN_CREATE = 0x00000100
        IN_DELETE = 0x00000200
        IN_MOVED_FROM = 0x00000040
        IN_MOVED_TO = 0x00000080
        IN_DELETE_SELF = 0x00000400
        IN_MOVE_SELF = 0x00000800
        IN_ISDIR = 0x40000000
        IN_ALL_EVENTS = (
            IN_ACCESS | IN_MODIFY | IN_ATTRIB |
            IN_CREATE | IN_DELETE |
            IN_MOVED_FROM | IN_MOVED_TO |
            IN_DELETE_SELF | IN_MOVE_SELF
        )

        # ctypes setup
        _libc.inotify_init.argtypes = []
        _libc.inotify_init.restype = ctypes.c_int

        _libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        _libc.inotify_add_watch.restype = ctypes.c_int

        _libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
        _libc.inotify_rm_watch.restype = ctypes.c_int

        _libc.close.argtypes = [ctypes.c_int]
        _libc.close.restype = ctypes.c_int

        # Init inotify
        fd = _libc.inotify_init()
        if fd < 0:
            log.debug("inotify_init 失败")
            return

        # Map wd -> (base_path, path_prefix)
        wd_map: Dict[int, str] = {}

        try:
            # Add watches for all paths
            for p in self._paths:
                abs_p = os.path.abspath(p)
                if not os.path.exists(abs_p):
                    continue
                wd = _libc.inotify_add_watch(fd, abs_p.encode("utf-8"), IN_ALL_EVENTS)
                if wd >= 0:
                    wd_map[wd] = abs_p
                else:
                    log.debug("inotify_add_watch 失败 for %s: %s", abs_p, wd)

            if not wd_map:
                log.debug("没有有效监控路径")
                return

            # Setup epoll
            ep = _select.epoll()
            ep.register(fd, _select.EPOLLIN)

            # Track pending MOVED_FROM for pairing
            pending_moves: Dict[int, Tuple[str, str]] = {}  # cookie -> (old_path, base_path)

            import struct as _struct

            while not self._stop.is_set():
                try:
                    events = ep.poll(timeout=0.5)
                except OSError:
                    break

                for fd_, _event in events:
                    if fd_ != fd:
                        continue

                    # Read inotify events
                    # We need to read enough bytes for all events in the queue
                    buf_size = 8192
                    try:
                        data = os.read(fd, buf_size)
                    except OSError:
                        continue

                    pos = 0
                    while pos < len(data):
                        # Read the fixed-size part
                        ev_size = 16  # sizeof(inotify_event) = 16 bytes (wd+mask+cookie+len)
                        ev_data = data[pos:pos+ev_size]
                        if len(ev_data) < ev_size:
                            break

                        wd = _struct.unpack("i", ev_data[0:4])[0]
                        mask = _struct.unpack("I", ev_data[4:8])[0]
                        cookie = _struct.unpack("I", ev_data[8:12])[0]
                        name_len = _struct.unpack("I", ev_data[12:16])[0]

                        is_dir = bool(mask & IN_ISDIR)

                        # Read name (if present, padded to 8 bytes)
                        name_bytes = b""
                        if name_len > 0:
                            name_end = pos + ev_size + name_len
                            if name_end <= len(data):
                                name_bytes = data[pos+ev_size:name_end].rstrip(b'\x00')
                            # Align to 8 bytes for next event
                            padded_len = ((name_len + 8) // 8) * 8
                            pos += ev_size + padded_len
                        else:
                            pos += ev_size

                        if wd not in wd_map:
                            continue

                        base_path = wd_map[wd]
                        file_name = name_bytes.decode("utf-8", errors="replace") if name_bytes else ""
                        full_path = os.path.join(base_path, file_name) if file_name else base_path

                        # Map mask to FileChangeType
                        if mask & IN_CREATE:
                            ct = FileChangeType.CREATED
                        elif mask & IN_DELETE:
                            ct = FileChangeType.DELETED
                        elif mask & IN_MODIFY:
                            ct = FileChangeType.MODIFIED
                        elif mask & IN_ATTRIB:
                            ct = FileChangeType.ATTRIB
                        elif mask & IN_ACCESS:
                            ct = FileChangeType.ACCESS
                        elif mask & IN_MOVED_FROM:
                            ct = FileChangeType.MOVED_OUT
                            pending_moves[cookie] = (full_path, base_path)
                            # Don't fire yet - wait for MOVED_TO
                            continue
                        elif mask & IN_MOVED_TO:
                            ct = FileChangeType.MOVED_IN
                            old_path = None
                            if cookie in pending_moves:
                                old_path, _ = pending_moves[cookie]
                                ct = FileChangeType.RENAMED
                                del pending_moves[cookie]
                            # Fire MOVED_TO as either MOVED_IN or RENAMED
                        else:
                            ct = FileChangeType.MODIFIED

                        try:
                            self._on_change(full_path, old_path if ct == FileChangeType.RENAMED else None, ct, is_dir)
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


class _PollingWatchBackend:
    """其它平台的保底路径：每隔 interval 秒检查一次文件状态。"""

    name = "polling"

    def __init__(
        self,
        on_change: Callable[[str, str | None, FileChangeType, bool], None],
        paths: Iterable[str] | None = None,
        change_types: Iterable[FileChangeType] | None = None,
        interval: float = 0.5,
    ) -> None:
        self._on_change = on_change
        self._paths: List[str] = list(paths) if paths else []
        self._change_types: Optional[set] = (
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
                target=self._run, name="vools-file-polling", daemon=True,
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
        # 轮询实现: 维护文件状态快照, 检测 CREATED/MODIFIED/DELETED/RENAMED
        # 状态: path -> (mtime, size, is_dir)
        state: Dict[str, Tuple[float, int, bool]] = {}

        def _scan_path(base_path: str) -> Dict[str, Tuple[float, int, bool]]:
            """扫描路径下所有文件, 返回 {rel_path: (mtime, size, is_dir)}"""
            result: Dict[str, Tuple[float, int, bool]] = {}
            try:
                for root, dirs, files in os.walk(base_path):
                    for name in itertools.chain(files, dirs):
                        full = os.path.join(root, name)
                        try:
                            mtime = os.path.getmtime(full)
                            size = (
                                os.path.getsize(full)
                                if os.path.isfile(full)
                                else 0
                            )
                            is_dir = os.path.isdir(full)
                            rel = os.path.relpath(full, base_path)
                            result[rel] = (mtime, size, is_dir)
                        except OSError:
                            continue
            except Exception:
                pass
            return result

        # 初始扫描
        for path_str in self._paths:
            abs_path = os.path.abspath(path_str)
            snapshot = _scan_path(abs_path)
            for rel, info in snapshot.items():
                full = os.path.join(abs_path, rel)
                state[full] = info

        try:
            while not self._stop.is_set():
                time.sleep(self._interval)

                for path_str in self._paths:
                    abs_path = os.path.abspath(path_str)
                    snapshot = _scan_path(abs_path)
                    current_files = set(
                        os.path.join(abs_path, rel) for rel in snapshot
                    )
                    known_files = set(state.keys())

                    # 检测删除
                    deleted = known_files - current_files
                    for full in deleted:
                        info = state.pop(full, None)
                        if info is not None:
                            _, _, is_dir = info
                            try:
                                self._on_change(full, None, FileChangeType.DELETED, is_dir)
                            except Exception as e:
                                log.debug("on_change 异常: %s", e)

                    # 检测新增和修改
                    for rel, info in snapshot.items():
                        full = os.path.join(abs_path, rel)
                        mtime, size, is_dir = info
                        prev = state.get(full)
                        if prev is None:
                            # 新增
                            state[full] = info
                            try:
                                self._on_change(full, None, FileChangeType.CREATED, is_dir)
                            except Exception as e:
                                log.debug("on_change 异常: %s", e)
                        elif prev != info:
                            # 修改
                            state[full] = info
                            try:
                                self._on_change(full, None, FileChangeType.MODIFIED, is_dir)
                            except Exception as e:
                                log.debug("on_change 异常: %s", e)

        finally:
            self._running = False


# ====================================================================
# FileDispatcher：主入口
# ====================================================================


class FileDispatcher:
    """文件系统监控与分发器。

    典型用法:
        >>> d = FileDispatcher(paths=["./src"])
        >>> d.subject.pipe(
        ...     ops.filter(lambda f: f.change_type == FileChangeType.MODIFIED),
        ... ).subscribe(on_next=lambda f: print("修改了:", f.path))
        >>> d.start()
        >>> d.stop()

    或作为上下文管理器:
        >>> with FileDispatcher(paths=["./src"]) as d:
        ...     d.subject.subscribe(on_next=print)

    构造参数:
        paths:             初始监控路径列表
        backend:           "auto" | "win32" | "macos" | "inotify" | "polling"（默认 auto）
        change_types:      白名单；仅分发列出的 FileChangeType；None 表示全部
        tags:              默认附加的标签
        interval:          polling 后端的检查间隔（秒），默认 0.5
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
        paths: Iterable[str] | None = None,
        backend: str = "auto",
        change_types: Iterable[FileChangeType] | None = None,
        tags: Iterable[str] = (),
        interval: float = 0.5,
        filter_self: bool = True,
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

        # Subject：可直接 pipe(...).subscribe(...)
        self._subject: Subject[FileData] = Subject()

        # 选择后端
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
    def subject(self) -> Subject[FileData]:
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

    def __enter__(self) -> "FileDispatcher":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    # ---- 路径增删 ----------------------------------------------------
    def add_path(self, path: str) -> None:
        """动态添加监控路径。"""
        path = os.path.abspath(path)
        if path not in self._paths:
            self._paths.append(path)
        # 后端占位：后续阶段填充 add_path 逻辑

    def remove_path(self, path: str) -> None:
        """动态移除监控路径。"""
        path = os.path.abspath(path)
        if path in self._paths:
            self._paths.remove(path)
        # 后端占位：后续阶段填充 remove_path 逻辑

    # ---- 签名生成 ----------------------------------------------------
    def _make_signature(
        self,
        path: str,
        change_type: FileChangeType,
    ) -> str:
        """生成文件事件的签名，用于自过滤"""
        data = f"{path}:{change_type.value}"
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    def register_self_signature(self, path: str, change_type: FileChangeType) -> None:
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
        old_path: str | None,
        change_type: FileChangeType,
        is_directory: bool,
    ) -> None:
        if (
            self._change_types_allowed is not None
            and change_type not in self._change_types_allowed
        ):
            return

        try:
            size: int | None = None
            if not is_directory and os.path.exists(path):
                try:
                    size = os.path.getsize(path)
                except OSError:
                    pass

            # 自过滤：命中签名 → 丢弃
            if self.filter_self:
                sig = self._make_signature(path, change_type)
                with self._lock:
                    if sig in self._self_signatures:
                        self._self_signatures.discard(sig)
                        self._self_filtered_count += 1
                        log.debug("自过滤文件事件: %s %s", change_type.name, path)
                        return

            fd = FileData.now(
                path=path,
                old_path=old_path,
                change_type=change_type,
                is_directory=is_directory,
                size=size,
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


def from_filesystem(
    *,
    paths: Iterable[str] | None = None,
    backend: str = "auto",
    change_types: Iterable[FileChangeType] | None = None,
    tags: Iterable[str] = (),
    interval: float = 0.5,
    auto_start: bool = True,
) -> Tuple[Any, FileDispatcher]:
    """顶层工厂函数：返回 (Observable[FileData], FileDispatcher) 二元组。

    Subject 拥有 pipe 方法，可直接链式组合响应式算子:
        >>> obs, d = from_filesystem(paths=["./src"])
        >>> obs.pipe(
        ...     ops.filter(lambda f: f.change_type == FileChangeType.MODIFIED),
        ... ).subscribe(on_next=lambda f: print("修改了:", f.path))
    """
    d = FileDispatcher(
        paths=paths,
        backend=backend,
        change_types=change_types,
        tags=tags,
        interval=interval,
    )
    if auto_start:
        d.start()
    return d.subject, d


def write_to_filesystem(
    dispatcher: FileDispatcher,
    mode: str = "create",
) -> Callable[[Observable[Any]], Observable[FileData]]:
    """响应式操作符：把上游每一项写入文件系统，并把构造的 FileData 继续下发。

    上游可接受:
        FileData  → 用其 path/change_type/metadata 写入
        str       → 作为文件路径
        dict      → {"path", "content", "change_type", "tags", "metadata"}
        tuple/list→ (path, content) 或 (path, content, change_type)
    """

    def operator(source_observable: Observable[Any]) -> Observable[FileData]:
        def subscribe(observer: Any) -> Any:
            def on_next(item: Any) -> None:
                try:
                    path: str = ""
                    content: str | bytes = ""
                    ct: FileChangeType = FileChangeType.MODIFIED
                    tags: List[str] = []
                    meta: Dict[str, Any] = {}

                    if isinstance(item, FileData):
                        path = item.path
                        ct = item.change_type
                        tags = list(item.tags)
                        meta = dict(item.metadata)
                    elif isinstance(item, str):
                        path = item
                    elif isinstance(item, dict):
                        path = item.get("path", "")
                        content = item.get("content", "")
                        ct = item.get("change_type", FileChangeType.MODIFIED)
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

                    # 写入文件
                    if path:
                        try:
                            if mode == "append":
                                with open(path, "ab") as f:
                                    if isinstance(content, str):
                                        f.write(content.encode("utf-8"))
                                    else:
                                        f.write(bytes(content))
                            else:
                                with open(path, "wb") as f:
                                    if isinstance(content, str):
                                        f.write(content.encode("utf-8"))
                                    else:
                                        f.write(bytes(content))

                            fd = FileData.now(
                                path=path,
                                change_type=FileChangeType.CREATED
                                if mode == "create"
                                else FileChangeType.MODIFIED,
                                is_directory=False,
                                size=len(content) if content else 0,
                                tags=tags,
                                metadata=meta,
                            )
                            observer.on_next(fd)
                        except Exception as e:
                            log.debug("write_to_filesystem 写入异常: %s", e)
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
                on_error=observer.on_error if hasattr(observer, "on_error") else None,
                on_completed=(
                    observer.on_completed if hasattr(observer, "on_completed") else None
                ),
            )

        return Observable(subscribe)

    return operator


# ====================================================================
# FileSubject: 自包含 Dispatcher 的 Subject
# ====================================================================


class FileSubject(MonitorSubject):
    """
    文件监控主题（Subject），继承 MonitorSubject。

    内部持有 FileDispatcher，提供文件变更事件流。
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
        filter_self: bool = True,
    ) -> None:
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

    def _create_dispatcher(self) -> "FileDispatcher":
        return FileDispatcher(
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
    def dispatcher(self) -> "FileDispatcher":
        return self._dispatcher

    @property
    def subject(self) -> "Subject[FileData]":
        return self

    @property
    def dispatch_count(self) -> int:
        return self._dispatcher.dispatch_count

    @property
    def backend_name(self) -> str:
        return self._dispatcher.backend_name

    def __enter__(self) -> "FileSubject":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass


class FileObserver(MonitorObserver):
    """
    文件事件观察者，按 FileChangeType 路由回调。

    Args:
        on_created: CREATED 回调
        on_modified: MODIFIED 回调
        on_deleted: DELETED 回调
        on_renamed: RENAMED 回调
        on_moved_in: MOVED_IN 回调
        on_moved_out: MOVED_OUT 回调
        on_access: ACCESS 回调
        on_attrib: ATTRIB 回调
        on_any: 任意事件回调
        on_error: 错误回调
        on_completed: 完成回调
    """

    def __init__(
        self,
        *,
        on_created: Optional[Callable[[FileData], Any]] = None,
        on_modified: Optional[Callable[[FileData], Any]] = None,
        on_deleted: Optional[Callable[[FileData], Any]] = None,
        on_renamed: Optional[Callable[[FileData], Any]] = None,
        on_moved_in: Optional[Callable[[FileData], Any]] = None,
        on_moved_out: Optional[Callable[[FileData], Any]] = None,
        on_access: Optional[Callable[[FileData], Any]] = None,
        on_attrib: Optional[Callable[[FileData], Any]] = None,
        on_any: Optional[Callable[[FileData], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(
            on_any=on_any, on_error=on_error, on_completed=on_completed,
        )
        self._on_created = on_created
        self._on_modified = on_modified
        self._on_deleted = on_deleted
        self._on_renamed = on_renamed
        self._on_moved_in = on_moved_in
        self._on_moved_out = on_moved_out
        self._on_access = on_access
        self._on_attrib = on_attrib

    def _event_type_of(self, value: Any) -> Any:
        return FileChangeType(value.change_type)

    def _handler_for(self, event_type: Any) -> Optional[Callable[[Any], Any]]:
        if event_type == FileChangeType.CREATED:
            return self._on_created
        if event_type == FileChangeType.MODIFIED:
            return self._on_modified
        if event_type == FileChangeType.DELETED:
            return self._on_deleted
        if event_type == FileChangeType.RENAMED:
            return self._on_renamed
        if event_type == FileChangeType.MOVED_IN:
            return self._on_moved_in
        if event_type == FileChangeType.MOVED_OUT:
            return self._on_moved_out
        if event_type == FileChangeType.ACCESS:
            return self._on_access
        if event_type == FileChangeType.ATTRIB:
            return self._on_attrib
        return None

    def _on_next(self, fd: "FileData") -> None:
        self.on_next(fd)

    def __enter__(self) -> "FileObserver":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.unsubscribe()
# ====================================================================

__all__ = [
    "FileChangeType",
    "FileData",
    "FileDispatcher",
    "FileSubject",
    "FileObserver",
    "from_filesystem",
    "write_to_filesystem",
]
