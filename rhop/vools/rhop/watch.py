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
from typing import Callable, Iterable, Optional

from .crypto import RhopCrypto, VerifyResult
from .transport.base import SharedPath

log = logging.getLogger("vools.rhop.watch")

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
        self._subject = None
        self._dispatcher = None
        self._started = False

    def _is_target(self, path: str) -> bool:
        """判断文件是否为本 watcher 关心的包文件。"""
        if os.path.isdir(path):
            return False
        return path.lower().endswith(self.extensions)

    def _handle(self, fd) -> None:
        """vools-rx 事件回调：读文件 → 解密验证 → 回调。"""
        path = getattr(fd, "path", "") or ""
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

    def start(self) -> None:
        """启动触发器监控（幂等）。"""
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

    def stop(self) -> None:
        """停止触发器监控。"""
        if self._started and self._dispatcher is not None:
            self._dispatcher.stop()
        self._started = False
