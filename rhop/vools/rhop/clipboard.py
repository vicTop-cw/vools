"""vools.rhop.clipboard - 剪贴板共享（对标 p0/p1 monitorclip 协议）

两块能力：

**1. 本机剪贴板读写**（探测链降级，零硬依赖）::

    pyperclip  →  PowerShell (Get-Clipboard / Set-Clipboard, stdin 传文本避免转义)

    read_clipboard()  -> str   读不到返回 ""（并记 reason 可查）
    write_clipboard(text) -> bool

**2. 文件交换协议**（RDP 断开时 p0 ↔ 共享盘 ↔ p1 的无感共享通道）::

    ClipboardFileSync(directory, role="push"|"pull")

    role="push"（p0 侧）：本机剪贴板 → 共享盘 clipboard.txt（内容变化才写）
    role="pull"（p1 侧）：共享盘 clipboard.txt → 本机剪贴板（内容变化才设）

    文件格式：JSON {"text", "updated_at", "writer"}——不存明文直接写 txt 是为了让
    p1 端能区分「文件还没人写过」和「写入了空剪贴板」。

方向只有 push / pull 两种：本机剪贴板没有时间戳，"both 双向收敛"无法可靠判新旧，
强行做会震荡（文件旧内容覆盖本机新复制）——monitorclip 的实际语义也是 p0 推 / p1 拉。

backend 参数可注入（测试用假剪贴板；缺省自动探测）。
"""

from __future__ import absolute_import

import json
import os
import subprocess
import threading
from typing import Any, Callable, Dict, Optional, Tuple

#: 交换文件缺省名
CLIP_FILE = "clipboard.txt"

_last_read_reason = {"reason": ""}


# ---------------------------------------------------------------------------
# 本机剪贴板后端探测
# ---------------------------------------------------------------------------

def _pyperclip_backend() -> Optional[Tuple[Callable[[], str], Callable[[str], bool]]]:
    try:
        import pyperclip  # type: ignore
    except Exception:
        return None
    return (lambda: pyperclip.paste() or "",
            lambda text: _safe_call(lambda: pyperclip.copy(text)))


def _powershell_backend() -> Optional[Tuple[Callable[[], str], Callable[[str], bool]]]:
    exe = "powershell.exe" if os.name != "nt" else "powershell"
    from shutil import which
    if which(exe) is None:
        return None

    def read() -> str:
        cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
               "Get-Clipboard -Raw")
        result = subprocess.run([exe, "-NoProfile", "-Command", cmd],
                                capture_output=True, timeout=10)
        # Get-Clipboard 在部分 Windows 版本会附带尾部 \r\n：剥掉它做协议归一化
        # （保留文本内换行与故意尾随空格，只剥最尾部的连续换行）
        return result.stdout.decode("utf-8", errors="replace").rstrip("\r\n")

    def write(text: str) -> bool:
        # 文本走 stdin，杜绝命令行转义/长度坑。
        # PS 5.1 的 `$input | Set-Clipboard` 按**默认控制台编码(GBK)**读 stdin，
        # 而这里喂的是 UTF-8 字节 → 中文被按 GBK 误解码、写进剪贴板的已是乱码
        # （实测 "中文" 读回变 mojibake）。先显式 InputEncoding=UTF8 再从
        # [Console]::In.ReadToEnd() 读取，与发送侧 UTF-8 对齐。
        cmd = ("[Console]::InputEncoding=[Text.Encoding]::UTF8; "
               "$t=[Console]::In.ReadToEnd(); Set-Clipboard -Value $t")
        result = subprocess.run([exe, "-NoProfile", "-Command", cmd],
                                input=text.encode("utf-8"),
                                capture_output=True, timeout=10)
        return result.returncode == 0

    return (read, write)


def _safe_call(fn: Callable[[], Any]) -> bool:
    try:
        fn()
        return True
    except Exception:
        return False


def get_clipboard_backend() -> Optional[Tuple[Callable[[], str], Callable[[str], bool], str]]:
    """探测可用的剪贴板后端，返回 (read_fn, write_fn, name)；全不可用返回 None。"""
    for maker, name in ((_pyperclip_backend, "pyperclip"),
                        (_powershell_backend, "powershell")):
        try:
            pair = maker()
        except Exception:
            pair = None
        if pair is not None:
            return (pair[0], pair[1], name)
    return None


def read_clipboard(backend: Optional[Tuple] = None) -> str:
    """读本机剪贴板；失败返回 ""（原因记在 last_read_reason()）。"""
    global _last_read_reason
    pair = backend or get_clipboard_backend()
    if pair is None:
        _last_read_reason["reason"] = "无可用剪贴板后端"
        return ""
    try:
        text = pair[0]() or ""
        _last_read_reason["reason"] = ""
        return text
    except Exception as exc:
        _last_read_reason["reason"] = "读取失败: %s" % exc
        return ""


def write_clipboard(text: str, backend: Optional[Tuple] = None) -> bool:
    """写本机剪贴板；成功 True。"""
    pair = backend or get_clipboard_backend()
    if pair is None:
        return False
    try:
        return bool(pair[1](text))
    except Exception:
        return False


def last_read_reason() -> str:
    """最近一次 read_clipboard 失败原因（诊断用）。"""
    return _last_read_reason["reason"]


# ---------------------------------------------------------------------------
# 文件交换协议
# ---------------------------------------------------------------------------

class ClipboardFileSync(object):
    """共享盘剪贴板交换（push / pull 单向，见模块 docstring）。

    Args:
        directory: 交换目录（共享盘挂载点 / 本地目录）
        role:      "push"（本机剪贴板 → 文件）| "pull"（文件 → 本机剪贴板）
        filename:  交换文件名（缺省 clipboard.txt）
        backend:   (read_fn, write_fn) 剪贴板后端；缺省自动探测（测试注入用）
        writer:    写入方标识（写进 JSON 的 writer 字段，诊断用）
    """

    def __init__(self, directory: str, role: str = "pull",
                 filename: str = CLIP_FILE,
                 backend: Optional[Tuple[Callable[[], str], Callable[[str], bool]]] = None,
                 writer: str = "rhop"):
        self.directory = str(directory)
        self.role = str(role or "pull").lower()
        if self.role not in ("push", "pull"):
            raise ValueError("role 必须是 push 或 pull（双向收敛不可靠，见模块 docstring）")
        self.filename = filename
        self.path = os.path.join(self.directory, filename)
        self.backend = backend
        self.writer = str(writer)
        self._last_text: Optional[str] = None
        os.makedirs(self.directory, exist_ok=True)

    # ------------------------------------------------------------------

    def _read_file(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _write_file(self, text: str) -> None:
        body = {"text": text, "updated_at": _utcnow_iso(), "writer": self.writer}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(body, fh, ensure_ascii=False)
        os.replace(tmp, self.path)

    def _clip_read(self) -> str:
        return read_clipboard(self.backend)

    def _clip_write(self, text: str) -> bool:
        if self.backend is not None:
            try:
                return bool(self.backend[1](text))
            except Exception:
                return False
        return write_clipboard(text)

    # ------------------------------------------------------------------

    def sync_once(self) -> Dict[str, Any]:
        """单次同步。

        push：本机剪贴板与文件内容不同 → 覆盖文件；
        pull：文件内容与本机剪贴板不同 → 设本机剪贴板。
        剪贴板后端不可用时 pull 记 errors、push 直接空转（不写坏文件）。
        """
        if self.role == "push":
            return self._sync_push()
        return self._sync_pull()

    def _sync_push(self) -> Dict[str, Any]:
        if self.backend is None and get_clipboard_backend() is None:
            return {"changed": False, "reason": "无可用剪贴板后端"}
        local = self._clip_read()
        file_doc = self._read_file()
        file_text = "" if file_doc is None else str(file_doc.get("text") or "")
        if local == file_text:
            self._last_text = local
            return {"changed": False, "reason": "内容一致"}
        try:
            self._write_file(local)
            self._last_text = local
            return {"changed": True, "text_len": len(local)}
        except OSError as exc:
            return {"changed": False, "reason": "文件写入失败: %s" % exc}

    def _sync_pull(self) -> Dict[str, Any]:
        file_doc = self._read_file()
        if file_doc is None:
            return {"changed": False, "reason": "交换文件不存在或未初始化"}
        text = str(file_doc.get("text") or "")
        if text == self._last_text:
            return {"changed": False, "reason": "内容未变化"}
        local = self._clip_read()
        if text == local:
            self._last_text = text
            return {"changed": False, "reason": "内容一致"}
        if not self._clip_write(text):
            return {"changed": False, "reason": "剪贴板写入失败"}
        self._last_text = text
        return {"changed": True, "text_len": len(text),
                "from_writer": str(file_doc.get("writer") or "")}

    # ------------------------------------------------------------------

    def run_forever(self, poll_interval: float = 2.0,
                    stop_event: Optional[threading.Event] = None) -> Dict[str, Any]:
        """守护轮询，直到 stop_event 置位。**至少跑一轮**（保证初始同步）。

        Returns:
            累计 {"rounds", "changes"}。
        """
        stop_event = stop_event or threading.Event()
        rounds = 0
        changes = 0
        while True:
            out = self.sync_once()
            rounds += 1
            if out.get("changed"):
                changes += 1
            if stop_event.is_set():
                break
            stop_event.wait(poll_interval)
        return {"rounds": rounds, "changes": changes}


def _utcnow_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "ClipboardFileSync",
    "get_clipboard_backend",
    "read_clipboard",
    "write_clipboard",
    "last_read_reason",
    "CLIP_FILE",
]
