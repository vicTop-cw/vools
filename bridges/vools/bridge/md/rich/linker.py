"""
vools.bridge.md.rich.linker — 文件链接路由（计划 P2/P4）

FileLinkRouter 将正文中的文件链接安全地路由到本机打开：
- 路径解析一律复用 RichPathResolver（相对路径 / @artifacts 产物 / realpath 校验，
  计划 §5.3 安全模型），不自行拼路径；
- 类型检测（detect_link_kind）按扩展名分类；
- 默认 opener 按平台选择：Windows os.startfile / macOS open / Linux xdg-open；
  无关联程序或解析失败返回 False，绝不静默执行任意命令。
"""

import os
import platform
import subprocess
from typing import Callable, Dict, Optional

from ...core.compat.dataclass_compat import dataclass, field
from ..errors import MDRichPathError, MDRichAccessDeniedError
from .resolver import RichPathResolver, DEFAULT_ALLOWED_EXTENSIONS
from .scanner import FileLink
from .status import ok_status, error_status


# ═══════════════════════════════════════════════════════
# 类型检测（计划 D5 类型集合的超集：链接侧分类）
# ═══════════════════════════════════════════════════════

_EXT_KIND: Dict[str, str] = {
    # 文档
    "pdf": "document", "doc": "document", "docx": "document",
    "ppt": "document", "pptx": "document", "xls": "document", "xlsx": "document",
    "odt": "document", "ods": "document", "odp": "document",
    # 图片
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "webp": "image", "bmp": "image", "tiff": "image", "ico": "image",
    # svg（独立类型，计划 D5）
    "svg": "svg",
    # html
    "html": "html", "htm": "html",
    # 文本 / 代码
    "txt": "text", "md": "text", "markdown": "text", "log": "text",
    "csv": "text", "json": "json", "yaml": "text", "yml": "text",
    "py": "text", "js": "text", "ts": "text", "java": "text", "c": "text",
    "cpp": "text", "h": "text", "hpp": "text", "rs": "text", "go": "text",
    "sh": "text", "ps1": "text", "bat": "text", "toml": "text", "ini": "text",
    "xml": "text",
    # 压缩包
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive",
    "gz": "archive",
    # 音视频
    "mp4": "video", "mkv": "video", "avi": "video", "mov": "video", "webm": "video",
    "mp3": "audio", "wav": "audio", "flac": "audio", "ogg": "audio", "m4a": "audio",
}


def detect_link_kind(path: str) -> str:
    """按扩展名检测链接类型（未知 → binary）。"""
    ext = os.path.splitext(str(path))[1].lower().lstrip(".")
    return _EXT_KIND.get(ext, "binary")


# ═══════════════════════════════════════════════════════
# 默认 opener（平台相关）
# ═══════════════════════════════════════════════════════


def _default_opener(path: str) -> bool:
    """用系统关联程序打开文件。失败返回 False，不抛异常。"""
    try:
        if platform.system() == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        if platform.system() == "Darwin":
            subprocess.Popen(["open", path])
            return True
        subprocess.Popen(["xdg-open", path])
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


# ═══════════════════════════════════════════════════════
# FileLinkRouter（计划 §5.4）
# ═══════════════════════════════════════════════════════


class FileLinkRouter:
    """文件链接路由：can_open 预检 + open 安全打开。

    构造方式与 RichPathResolver 一致（root/build_dir/allow_absolute），
    由调用方（CLI / 宿主）一次性构建，避免每次 open 重建解析器。

    Args:
        root: 允许根目录（md 所在目录）
        build_dir: 产物目录（默认 root/.mdbuild）
        opener: 自定义打开函数 fn(path) -> bool；None 使用平台默认
        allow_remote: 是否放行 http(s) 远程链接（默认 False，仅记录不打开）
        allow_absolute: 是否放行绝对路径引用（默认 False，与 resolver 对齐）
    """

    def __init__(
        self,
        root: str,
        build_dir: Optional[str] = None,
        *,
        opener: Optional[Callable[[str], bool]] = None,
        allow_remote: bool = False,
        allow_absolute: bool = False,
    ):
        self.root = os.path.abspath(root)
        self.build_dir = build_dir
        self.allow_remote = allow_remote
        self.opener = opener if opener is not None else _default_opener
        self.resolver = RichPathResolver(
            self.root,
            build_dir,
            allow_absolute=allow_absolute,
            strict_dotdot=True,
            check_realpath=True,
            allowed_extensions=DEFAULT_ALLOWED_EXTENSIONS,
        )

    # ── 预检 ────────────────────────────────────────────

    def can_open(self, link: FileLink) -> bool:
        """链接是否可安全打开。

        - remote/data：需 allow_remote 才放行
        - 本地：经 resolver 解析（存在 / 白名单扩展名 / 越权校验）后放行
        """
        if not isinstance(link, FileLink):
            return False
        target = (link.target or "").strip()
        if not target:
            return False
        low = target.lower()
        if low.startswith(("http://", "https://")):
            return self.allow_remote
        if low.startswith("data:"):
            return False  # data: 链接一律不打开（浏览器语义）
        try:
            self.resolver.resolve(target)
            return True
        except (MDRichPathError, MDRichAccessDeniedError):
            return False

    # ── 打开 ────────────────────────────────────────────

    def open(self, link: FileLink) -> bool:
        """安全打开链接，成功返回 True。解析失败 / 打开失败返回 False。"""
        if not self.can_open(link):
            link.status = error_status(
                "E_ACCESS_DENIED" if link.kind != "remote" else "E_REMOTE_DISABLED",
                f"链接不可打开: {link.target}",
            )
            return False
        try:
            resolved = link.resolved_path or self.resolver.resolve(link.target)
        except (MDRichPathError, MDRichAccessDeniedError) as e:
            link.status = error_status(
                e.code if hasattr(e, "code") else "E_PATH_NOT_FOUND", str(e)
            )
            return False
        link.resolved_path = resolved
        if not os.path.exists(resolved):
            link.status = error_status("E_PATH_NOT_FOUND", f"目标不存在: {resolved}")
            return False
        try:
            ok = self.opener(resolved)
        except Exception:
            ok = False
        if ok:
            link.status = ok_status(f"已打开: {resolved}")
        else:
            link.status = error_status("E_OPEN_FAILED", f"打开失败: {resolved}")
        return ok

    # ── 批量工具 ────────────────────────────────────────

    def open_many(self, links: list, *, limit: int = 10) -> Dict[str, int]:
        """批量打开（限制并发数量，防误点潮涌）。返回统计。"""
        stats = {"ok": 0, "skipped": 0, "failed": 0}
        for link in links[:limit]:
            if self.open(link):
                stats["ok"] += 1
            elif link.status and link.status.code == "E_ACCESS_DENIED":
                stats["skipped"] += 1
            else:
                stats["failed"] += 1
        return stats
