"""probe/environment.py — 环境变量探测。

安全原则：只记录 key 名存在与否，不记录敏感值。
"""

import os
import re
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
    executable_files = []
    for d in path_dirs:
        if os.path.isdir(d):
            try:
                for f in os.listdir(d):
                    full = os.path.join(d, f)
                    if os.access(full, os.X_OK):
                        executable_files.append(f)
            except (OSError, PermissionError):
                pass
    info["path_executables"] = sorted(set(executable_files))

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