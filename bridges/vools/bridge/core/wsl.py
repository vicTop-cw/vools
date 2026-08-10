"""
vools.bridge.core.wsl - WSL 辅助工具

为 Windows 上的桥接模块提供统一的 WSL 检测、路径转换和命令执行接口。
"""

import os
import shutil
import platform
import subprocess
from typing import Optional, List

_IS_WINDOWS = platform.system() == 'Windows'


def is_wsl_available() -> bool:
    """检查 WSL 是否可用（仅 Windows 上）"""
    if not _IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ['wsl', '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def check_wsl_command(cmd: str) -> bool:
    """检查 WSL 中是否存在指定命令"""
    if not is_wsl_available():
        return False
    try:
        result = subprocess.run(
            ['wsl', 'which', cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() != b''
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def windows_to_wsl_path(windows_path: str) -> str:
    """将 Windows 绝对路径转换为 WSL 路径。

    例如：C:\\Users\\foo\\bar -> /mnt/c/Users/foo/bar
    """
    windows_path = os.path.abspath(windows_path)
    drive = windows_path[0].lower()
    rest = windows_path[2:].replace('\\', '/')
    return f'/mnt/{drive}{rest}'


def wsl_run(cmd_args: List[str], timeout: int = 60,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """通过 WSL 运行命令，自动处理编码问题"""
    wsl_cmd = ['wsl'] + cmd_args
    if text:
        result = subprocess.run(
            wsl_cmd,
            stdout=stdout, stderr=stderr,
            timeout=timeout,
        )
        result.stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
        result.stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
        return result
    return subprocess.run(wsl_cmd, stdout=stdout, stderr=stderr,
                          timeout=timeout, text=text, **kwargs)


def resolve_command(local_name: str) -> tuple:
    """解析命令，返回 (cmd_prefix, path_converter, use_wsl)

    检测顺序：
    1. 本地命令（PATH 或常见路径）
    2. WSL 中的同名命令

    返回：
        (cmd_prefix, path_converter, use_wsl)
        - cmd_prefix: 可传给 subprocess 的列表，如 ['ruby'] 或 ['wsl', 'ruby']
        - path_converter: 函数，将 Windows 路径转为运行时可识别的路径
        - use_wsl: 是否使用 WSL
    """
    # 1. 本地命令
    local_path = shutil.which(local_name)
    if local_path:
        return ([local_path], lambda p: p, False)

    # 2. WSL 命令
    if _IS_WINDOWS and check_wsl_command(local_name):
        return (['wsl', local_name], windows_to_wsl_path, True)

    # 3. 回退
    return ([local_name], lambda p: p, False)
