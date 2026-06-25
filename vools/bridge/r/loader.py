"""
vools.bridge.r.loader - R 环境加载器

提供 R 环境可用性检查，对齐其他桥接的 loader API。

使用 manager 统一管理编译器配置。
"""

import platform
import subprocess

from ..manager import get_helper
from .compiler import r_compiler_available, _check_jsonlite_available, _IS_WINDOWS, _safe_subprocess_run

# 使用 manager 的编译器辅助
_r_helper = get_helper('r')


def is_r_available():
    """
    检查 R 环境是否可用

    使用 manager 统一管理。

    Windows 下检查 WSL + Rscript，Linux/macOS 下直接检查 Rscript。

    返回：
        bool: R 可用返回 True，否则返回 False
    """
    return _r_helper.is_available()


def get_r_version():
    """
    获取 R 版本信息

    使用 manager 统一管理。

    返回：
        str: R 版本字符串，不可用返回 None
    """
    # 优先使用 manager 获取的版本
    version = _r_helper.get_version()
    if version:
        return version

    # 兜底：直接检查
    use_wsl = _IS_WINDOWS
    try:
        if use_wsl:
            cmd = ['wsl', 'Rscript', '--version']
        else:
            cmd = ['Rscript', '--version']

        result = _safe_subprocess_run(cmd, timeout=15)
        if result.returncode == 0:
            output = result.stderr.strip() or result.stdout.strip()
            for line in output.split('\n'):
                if 'version' in line.lower():
                    return line.strip()
            return output.split('\n')[0] if output else None
        return None
    except Exception:
        return None


def is_jsonlite_available():
    """
    检查 jsonlite 包是否可用

    返回：
        bool: jsonlite 可用返回 True，否则返回 False
    """
    use_wsl = _IS_WINDOWS
    return _check_jsonlite_available(use_wsl)
