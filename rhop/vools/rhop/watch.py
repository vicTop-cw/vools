"""vools.rhop.watch - MVP-2 接收方触发器监控（vools-rx 触发器 API）

监控方使用 vools-rx 触发器 API（from_filesystem → Observable[FileData]），
监听 shared path 出现新文件（创建 / 移入），读取并用本地固定密钥解密验证。

典型用法:
    >>> crypto = RhopCrypto.from_env()
    >>> shared = LocalSharedPath(r"<share_dir>")
    >>> watcher = RhopWatcher(shared, crypto, on_packet=my_callback)
    >>> watcher.start()
    ... 发送方写入 <share_dir>\\pkg.rhop ...
    >>> watcher.stop()
"""

import logging
import os
import threading
import time
import uuid
from typing import Callable, Iterable, Optional

from .crypto import RhopCrypto, VerifyResult
from .transport.base import SharedPath

log = logging.getLogger("vools.rhop.watch")

#: 就绪哨兵文件名前缀/后缀：**绝不能命中 DEFAULT_EXTENSIONS**（.rhop），
#: 否则握手会在业务回调里冒出一个假包
_READY_TOKEN_PREFIX = ".rhop-ready-"
_READY_TOKEN_SUFFIX = ".tmp"

# vools-rx 触发器导入（延迟导入，便于在未安装 rx 时给出清晰错误）
try:
    from vools.reactive.monitoring.file_watcher import (
        FileChangeType,
        from_filesystem,
    )
except Exception:  # pragma: no cover
    # vools-rx 未安装或平台不兼容（如 py3.6 非 Windows 下 ctypes.wintypes 崩溃）→ 降级为不可用
    FileChangeType = None
    from_filesystem = None

# 默认监听的文件后缀
DEFAULT_EXTENSIONS = (".rhop",)


class RhopWatcher(object):
    """shared path 新文件触发器监控 + 解密验证。"""

    def __init__(
        self,
        shared_path: SharedPath,
        crypto: RhopCrypto,
        on_packet: Optional[Callable[[str, VerifyResult], None]] = None,
        extensions: Iterable[str] = DEFAULT_EXTENSIONS,
        backend: str = "auto",
        interval: float = 0.5,
        ready_timeout: float = 5.0,
    ):
        if from_filesystem is None:
            raise RuntimeError(
                "vools.rhop.watch: 需要 vools-rx（vools.reactive.monitoring.file_watcher）"
                "支持；请安装 vools-rx 或把仓库 rx/ 目录加入 PYTHONPATH"
            )
        self.shared_path = shared_path
        self.crypto = crypto
        self.on_packet = on_packet or (lambda filename, result: None)
        self.extensions = tuple(extensions)
        self.backend = backend
        self.interval = interval
        self.ready_timeout = float(ready_timeout)
        self._subject = None
        self._dispatcher = None
        self._started = False
        self._ready = threading.Event()
        self._ready_token = None

    def _is_target(self, path: str) -> bool:
        """判断文件是否为本 watcher 关心的包文件。"""
        if os.path.isdir(path):
            return False
        return path.lower().endswith(self.extensions)

    def _handle(self, fd) -> None:
        """vools-rx 事件回调：读文件 → 解密验证 → 回调。"""
        path = getattr(fd, "path", "") or ""
        # 就绪哨兵：只标记「事件流已通」，绝不进业务回调（文件名带 .tmp，不匹配扩展名）
        if path and self._ready_token and os.path.basename(path) == self._ready_token:
            self._ready.set()
            return
        if not path or not self._is_target(path):
            return
        filename = os.path.basename(path)
        try:
            content = self.shared_path.read_text(filename)
        except Exception as exc:  # 读不到（可能被删/半写）则忽略
            log.debug("rhop watch: 读取 %s 失败: %s", filename, exc)
            return
        result = self.crypto.decrypt_verify(content)
        log.info("rhop watch: %s -> ok=%s reason=%s", filename, result.ok, result.reason)
        self.on_packet(filename, result)

    def wait_until_started(self, timeout: Optional[float] = None) -> bool:
        """监听是否**已真正生效**（基线已建立、事件可送达）；已生效返回 True。

        典型用法：``start()``（默认已等）之后无需再调；显式 ``start(wait_ready=False)``
        的调用方可用它自己做超时控制。
        """
        if not self._started:
            return False
        timeout = self.ready_timeout if timeout is None else float(timeout)
        return self._ready.wait(timeout)

    def _handshake(self, deadline: float) -> bool:
        """就绪握手：写一个非目标后缀的哨兵文件，**等到自己收到它的事件**再删。

        为什么不能只 sleep：rx 的三个后端（win32 / inotify / polling）的 ``start()``
        都只负责拉起后台线程，基线快照/句柄注册发生在**线程内部**；固定 sleep 只能把
        竞态变成"慢一点的竞态"。这里等的是**真实事件**，每轮有界等待、失败换文件名重试：
        若哨兵恰好在基线扫描前落盘，它会被当成「启动前已存在」而不产生事件，
        于是换名再写一次（此时基线已建立）—— 收敛靠事件，不靠猜时长。
        """
        root = getattr(self.shared_path, "root", None)
        if not root or not os.path.isdir(root):
            return False
        attempt = 0
        while time.monotonic() < deadline:
            token = "%s%s-%d%s" % (_READY_TOKEN_PREFIX, uuid.uuid4().hex[:8],
                                   attempt, _READY_TOKEN_SUFFIX)
            path = os.path.join(root, token)
            self._ready.clear()
            self._ready_token = token
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("ready")
            except OSError as exc:
                log.debug("rhop watch: 就绪哨兵写入失败（目录不可写？）: %s", exc)
                return False
            slice_s = max(0.05, min(self.interval * 2.0 + 0.2,
                                    deadline - time.monotonic()))
            try:
                ok = self._ready.wait(slice_s)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if ok:
                return True
            attempt += 1
        return False

    def start(self, wait_ready: bool = True) -> None:
        """启动触发器监控（幂等）。**默认等到监听真正生效后才返回**。

        契约（历史缺陷收口，待入账）：``start()`` 返回 ⇒ 此后写入 shared path 的新文件**一定会**
        被看到。历史缺陷是 ``start()`` 只保证「后台线程已拉起」：基线快照在 rx 后端线程
        内部完成，紧随其后写入的文件可能被当成「启动前已存在」而**整个漏掉**
        （受控实验：start() 后立刻写，8 轮漏 5 轮）。这是调用方无法从 API 看出来的
        契约模糊，所以把等待放进 ``start()``，而不是要求每个调用方自己猜。

        目录不可写 / 事件后端异常时**不放任卡死**：``ready_timeout``（默认 5s）到点后记
        warning 继续启动（best-effort，不抛错拖垮 CLI/daemon）——但那之后写入的首批文件
        可能被漏掉，此时 ``wait_until_started()`` 会返回 False，调用方据此可自检。
        """
        if self._started:
            return
        self.shared_path.available()
        watcher_types = None
        if FileChangeType is not None:
            watcher_types = (
                FileChangeType.CREATED,
                FileChangeType.MOVED_IN,
                FileChangeType.MODIFIED,
            )
        self._subject, self._dispatcher = from_filesystem(
            paths=[self.shared_path.root],
            backend=self.backend,
            change_types=watcher_types,
            interval=self.interval,
            auto_start=False,
        )
        self._subject.subscribe(on_next=self._handle)
        self._dispatcher.start()
        self._started = True
        if wait_ready:
            deadline = time.monotonic() + max(0.0, self.ready_timeout)
            if not self._handshake(deadline):
                log.warning(
                    "rhop watch: 就绪握手未在 %.1fs 内确认"
                    "（共享目录不可写 / 事件后端异常）；继续启动，"
                    "但**紧随其后写入的首批文件可能被漏掉**",
                    self.ready_timeout)
        self._ready_token = None

    def stop(self) -> None:
        """停止触发器监控。"""
        if self._started and self._dispatcher is not None:
            self._dispatcher.stop()
        self._started = False
        self._ready.clear()
