"""
vools.md.rich.linker — 文件链接路由（BRIDGES_MD_RICH_CONTENT_PLAN P4）

从 Markdown 中提取文件链接，提供安全校验和系统打开能力。

核心功能：
- extract_file_links(): 从 Markdown 提取文件链接
- FileLink: 文件链接数据结构
- FileLinkRouter: 宿主可替换的文件链接路由
- 路径安全校验：穿越/符号链接/设备名/UNC/长度/类型白名单
"""

import os
import re
import subprocess
import platform
from typing import List, Optional, Dict, Any
from .scanner import RichDoc

__all__ = [
    'FileLink', 'FileLinkRouter', 'extract_file_links',
    'can_open_file', 'open_file',
]


# ─── 数据结构 ───

class FileLink:
    """文件链接记录。

    Attributes:
        text: 链接文本（Markdown 中的显示文本）
        url: 原始 URL/路径
        resolved_path: 解析后的绝对路径（None=未解析）
        exists: 文件是否存在
        kind: 链接类型 — 'local' / 'remote' / 'data'
    """

    def __init__(self, text: str, url: str,
                 resolved_path: Optional[str] = None,
                 exists: bool = False,
                 kind: str = 'local'):
        self.text = text
        self.url = url
        self.resolved_path = resolved_path
        self.exists = exists
        self.kind = kind

    def to_dict(self) -> Dict[str, Any]:
        return {
            'text': self.text,
            'url': self.url,
            'resolved_path': self.resolved_path,
            'exists': self.exists,
            'kind': self.kind,
        }

    def __repr__(self):
        return f'FileLink({self.text!r}, {self.url!r}, {self.kind})'


# ─── 路径安全 ───

# 允许的文件类型白名单
ALLOWED_FILE_TYPES: frozenset = frozenset({
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp',
    '.html', '.htm', '.xhtml',
    '.txt', '.md', '.json', '.xml',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
})

# Windows 设备名
WINDOWS_DEVICE_NAMES: frozenset = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5',
})

# 最大路径长度
MAX_PATH_LEN = 4096


def _is_safe_path(path: str, base_dir: str) -> bool:
    """路径安全校验。

    检查：穿越/符号链接/设备名/UNC/长度/类型白名单

    Args:
        path: 待校验的路径
        base_dir: 基准目录（md 文件所在目录）

    Returns:
        是否安全
    """
    # 长度检查
    if len(path) > MAX_PATH_LEN:
        return False

    # Windows 设备名检查
    basename = os.path.basename(path.replace('\\', '/')).upper()
    if basename in WINDOWS_DEVICE_NAMES:
        return False

    # UNC 路径检查（\\server\share）
    if path.startswith('\\\\'):
        return False

    # 解析为绝对路径
    if os.path.isabs(path):
        abs_path = os.path.normpath(path)
    else:
        abs_path = os.path.normpath(os.path.join(base_dir, path))

    # 路径穿越检查：realpath 必须在 base_dir 内
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(abs_path)
    if not (real_path == real_base or real_path.startswith(real_base + os.sep)):
        return False

    # 文件类型白名单
    ext = os.path.splitext(real_path)[1].lower()
    if ext and ext not in ALLOWED_FILE_TYPES:
        return False

    return True


# ─── 文件链接提取 ───

# Markdown 链接正则: [text](url)
MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def extract_file_links(markdown_text: str,
                       base_dir: str = '.') -> List[FileLink]:
    """从 Markdown 文本中提取文件链接。

    识别三类链接：
    1. 本地文件：[text](file.pdf) / [text](./docs/file.md)
    2. 远程文件：[text](https://example.com/file.pdf)
    3. data URI：[text](data:application/pdf;base64,...)

    Args:
        markdown_text: Markdown 原文
        base_dir: md 文件所在目录（用于相对路径解析）

    Returns:
        FileLink 列表
    """
    links: List[FileLink] = []
    for m in MD_LINK_RE.finditer(markdown_text):
        text = m.group(1)
        url = m.group(2).strip()

        # 跳过图片引用（![alt](url) 已被 scan_rich 处理）
        if url.startswith('data:'):
            kind = 'data'
            links.append(FileLink(text, url, kind=kind))
        elif url.startswith(('http://', 'https://')):
            kind = 'remote'
            links.append(FileLink(text, url, kind=kind))
        elif url.startswith('file://'):
            kind = 'local'
            path = url[7:]
            links.append(FileLink(text, url, kind=kind))
        else:
            kind = 'local'
            links.append(FileLink(text, url, kind=kind))

    # 解析本地文件路径
    for link in links:
        if link.kind == 'local':
            path = link.url
            if path.startswith('file://'):
                path = path[7:]
            if _is_safe_path(path, base_dir):
                if os.path.isabs(path):
                    abs_path = os.path.normpath(path)
                else:
                    abs_path = os.path.normpath(os.path.join(base_dir, path))
                link.resolved_path = abs_path
                link.exists = os.path.isfile(abs_path)
            else:
                link.resolved_path = None
                link.exists = False

    return links


# ─── 文件链接路由 ───

class FileLinkRouter:
    """宿主可替换的文件链接路由。

    提供默认实现（系统默认程序打开），宿主可替换为
    WebView2/内部查看器等。
    """

    def __init__(self, base_dir: str = '.'):
        self.base_dir = base_dir

    def can_open(self, link: FileLink) -> bool:
        """判断能否打开该链接。"""
        if link.kind == 'data':
            return False  # data URI 不能直接打开
        if link.kind == 'remote':
            return False  # 远程链接不在此层打开
        if not link.exists or not link.resolved_path:
            return False
        return os.path.isfile(link.resolved_path)

    def open(self, link: FileLink) -> bool:
        """打开文件链接。

        使用系统默认程序打开（Windows: ShellExecute, Unix: xdg-open）。

        Returns:
            是否成功
        """
        if not self.can_open(link):
            return False
        return open_file(link.resolved_path)


def open_file(path: str) -> bool:
    """用系统默认程序打开文件。

    Args:
        path: 文件绝对路径

    Returns:
        是否成功
    """
    try:
        if platform.system() == 'Windows':
            # Windows: 使用 os.startfile
            os.startfile(path)  # type: ignore
            return True
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        else:
            # Linux/Unix: xdg-open
            subprocess.Popen(['xdg-open', path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
    except Exception:
        return False


def can_open_file(path: str, base_dir: str = '.') -> bool:
    """检查文件是否可安全打开。

    Args:
        path: 文件路径
        base_dir: 基准目录

    Returns:
        是否安全且存在
    """
    if not _is_safe_path(path, base_dir):
        return False
    if os.path.isabs(path):
        abs_path = os.path.normpath(path)
    else:
        abs_path = os.path.normpath(os.path.join(base_dir, path))
    return os.path.isfile(abs_path)
