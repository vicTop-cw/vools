"""probe/environment.py — 环境变量探测。

安全原则：只记录 key 名存在与否，不记录敏感值。
"""


__all__ = [
    "get_environment_info",
    "EnvironmentProber",
]

import itertools
import os
import re
import stat
import sys

from .base import Prober, ProbeItem

# 敏感 key 模式（只记 key 名，不记值）
SENSITIVE_PATTERNS = [
    r'API_KEY', r'TOKEN', r'SECRET', r'PASSWORD', r'PASSWD',
    r'PRIVATE_KEY', r'CREDENTIAL', r'AUTH', r'BASIC_AUTH',
]

# 关键环境变量白名单（始终采集）
CRITICAL_VARS = [
    'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP',
    'SYSTEMROOT', 'SystemRoot', 'ProgramFiles', 'ProgramFiles(x86)',
    'ProgramData', 'PATH', 'PATHEXT',
    'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY',
    'http_proxy', 'https_proxy', 'no_proxy',
    'VIRTUAL_ENV', 'CONDA_PREFIX', 'CONDA_DEFAULT_ENV',
    'PYTHONPATH', 'PYTHONHOME', 'PYTHONUNBUFFERED',
    'LANG', 'LC_ALL', 'LC_CTYPE',
    'DISPLAY', 'TERM',
]

# ── PATH 扫描预算 ──
# 用户 PATH 里常有几十个目录、单个目录几千个文件（VS 工具链、WindowsApps、
# node_modules 之类），旧实现对每个条目都做一次 os.access(X_OK)，单次探测实测
# 6.5s。这里用「目录数 / 单目录条目 / 总条目」三重上限把最坏情况钉死。
_MAX_SCAN_DIRS = 256
_MAX_ENTRIES_PER_DIR = 4096
_MAX_ENTRIES_TOTAL = 20000

# Windows 下 os.access(path, X_OK) 对任何**存在**的文件都返回 True
# （Windows 无法用 access() 判断执行权限），旧实现因此把 .dll/.pdb/.txt
# 也全算成「可执行文件」—— 既慢又不准。真正的判据是 PATHEXT。
_DEFAULT_PATHEXT = ('.COM', '.EXE', '.BAT', '.CMD')


def _windows_executable_exts():
    """Windows 可执行扩展名元组（小写）：取 PATHEXT，缺省兜底常见四种。"""
    raw = os.environ.get('PATHEXT') or ''
    exts = [e.strip().lower() for e in raw.split(os.pathsep) if e.strip()]
    if not exts:
        exts = [e.lower() for e in _DEFAULT_PATHEXT]
    return tuple(exts)


def _scan_path_executables(path_dirs):
    """扫描 PATH，返回可执行文件名集合（只记名字，不记完整路径）。

    相对旧实现（listdir + 逐条目 os.access）的三处优化：
      1. os.scandir：Windows 上名字/属性直接来自目录枚举缓冲，判断「是不是目录」
         零额外系统调用，省掉每个条目一次 stat；
      2. Windows 只按 PATHEXT 扩展名筛选（一次 access/stat 都不做），
         POSIX 才 stat 取 mode 执行位；
      3. PATH 目录去重 + 三重条目上限，病态 PATH 不会把探测拖成几十秒。
    """
    names = set()
    if not path_dirs:
        return names

    is_windows = sys.platform == 'win32'
    exts = _windows_executable_exts() if is_windows else None
    visited = set()
    scanned = 0

    for directory in path_dirs:
        if len(visited) >= _MAX_SCAN_DIRS:
            break
        try:
            key = os.path.normcase(os.path.abspath(directory))
        except (OSError, ValueError):
            key = directory
        if key in visited:
            continue                      # PATH 里重复目录很常见，扫一遍就够
        visited.add(key)

        try:
            with os.scandir(directory) as entries:
                for entry in itertools.islice(entries, _MAX_ENTRIES_PER_DIR):
                    scanned += 1
                    if scanned > _MAX_ENTRIES_TOTAL:
                        return names
                    try:
                        if is_windows:
                            if entry.is_dir():        # 零额外系统调用
                                continue
                            if not entry.name.lower().endswith(exts):
                                continue
                        else:
                            mode = entry.stat(follow_symlinks=False).st_mode
                            if not stat.S_ISREG(mode) or not (mode & 0o111):
                                continue
                    except OSError:
                        continue
                    names.add(entry.name)
        except OSError:
            continue                      # 不存在/无权限/不是目录：跳过

    return names


def _detect_virtual_env() -> dict:
    """检测虚拟环境（venv/virtualenv）。"""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        return {
            "active": True,
            "path": venv,
            "python_path": os.path.join(
                venv, "Scripts" if sys.platform == "win32" else "bin", "python"
            ),
        }
    if hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix:
        return {
            "active": True,
            "path": sys.prefix,
            "python_path": sys.executable,
        }
    return {"active": False}


def _detect_conda_env() -> dict:
    """检测 conda 环境。"""
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        return {
            "active": True,
            "name": os.environ.get("CONDA_DEFAULT_ENV", os.path.basename(conda_prefix)),
            "path": conda_prefix,
        }
    return {"active": False}


def get_environment_info() -> dict:
    """探测环境变量信息。"""
    info = {}

    # ── PATH 分析 ──
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    info["path_dirs"] = path_dirs
    info["path_count"] = len(path_dirs)
    # 只记录可执行文件列表（不记录完整路径，避免泄露）
    info["path_executables"] = sorted(_scan_path_executables(path_dirs))

    # ── 关键环境变量 ──
    info["env_vars"] = {}
    for var in CRITICAL_VARS:
        val = os.environ.get(var)
        if val is not None:
            if var == "PATH":
                info["env_vars"][var] = "[REDACTED:%d items]" % len(path_dirs)
            else:
                info["env_vars"][var] = val

    # ── 敏感 key 扫描 ──
    info["secret_keys_found"] = {}
    for key in os.environ:
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, key, re.IGNORECASE):
                info["secret_keys_found"][key] = True
                break

    # ── 虚拟环境检测 ──
    info["virtual_env"] = _detect_virtual_env()

    # ── conda 环境检测 ──
    info["conda_env"] = _detect_conda_env()

    return info


class EnvironmentProber(Prober):
    """环境变量探测器。"""

    def probe(self) -> list:
        info = get_environment_info()
        return [ProbeItem(
            name="environment",
            category="environment",
            available=True,
            extra=info,
        )]
