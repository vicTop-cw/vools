"""
vools.sys.env - 系统环境变量读取模块

提供跨平台系统环境变量读取功能，通过 PowerShell（Windows）或 Shell（Linux）
直接读取系统级环境变量（注册表/配置文件），而不是仅读取进程级 os.environ。

用法：
    from vools.sys.env import get_env

    # 读取系统 PATH 环境变量（Windows 从注册表，Linux 从 /etc/environment）
    path = get_env("PATH")

    # 读取用户级环境变量
    home = get_env("HOME")
"""

import os
import platform
from typing import Optional

# 平台检测
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'
_IS_MACOS = platform.system() == 'Darwin'

# 桥接库可用性缓存
_powershell_bridge = None
_shell_bridge = None


def _get_powershell_bridge():
    """获取 PowerShell 桥接实例（延迟加载）"""
    global _powershell_bridge
    if _powershell_bridge is None:
        try:
            from vools.bridge.powershell import powershell_bridge, powershell_compiler_available
            if powershell_compiler_available():
                _powershell_bridge = powershell_bridge
        except ImportError:
            pass
    return _powershell_bridge


def _get_shell_bridge():
    """获取 Shell 桥接实例（延迟加载）"""
    global _shell_bridge
    if _shell_bridge is None:
        try:
            from vools.bridge.shell import shell_bridge, shell_compiler_available
            if shell_compiler_available():
                _shell_bridge = shell_bridge
        except ImportError:
            pass
    return _shell_bridge


def _get_env_powershell(name: str) -> Optional[str]:
    """
    通过 PowerShell 获取系统环境变量（Windows）

    从注册表 Machine 级别读取系统环境变量，比 os.environ 更全面。

    Args:
        name: 环境变量名

    Returns:
        环境变量值，如果不存在返回 None
    """
    bridge = _get_powershell_bridge()
    if bridge is None:
        return None

    try:
        # PowerShell 代码：获取系统级（Machine）环境变量
        ps_code = f'''[System.Environment]::GetEnvironmentVariable("{name}", "Machine")'''
        result = bridge.compile_and_run(
            code=ps_code,
            func_name='get_env',
            args=(name,),
            ret_type=str,
        )
        if result and result != '':
            return result
    except Exception:
        pass

    return None


def _get_env_shell(name: str) -> Optional[str]:
    """
    通过 Shell 获取系统环境变量（Linux）

    从 /etc/environment 和 printenv 读取系统级环境变量。

    Args:
        name: 环境变量名

    Returns:
        环境变量值，如果不存在返回 None
    """
    bridge = _get_shell_bridge()
    if bridge is None:
        return None

    try:
        # Shell 代码：优先从 /etc/environment 读取，否则用 printenv
        shell_code = f'''if grep -q "^{name}=" /etc/environment 2>/dev/null; then
    grep "^{name}=" /etc/environment | cut -d'=' -f2- | tr -d '"'
else
    printenv "{name}" 2>/dev/null || echo ""
fi'''
        result = bridge.compile_and_run(
            code=shell_code,
            func_name='get_env',
            args=(name,),
            ret_type=str,
        )
        if result and result != '':
            return result
    except Exception:
        pass

    return None


def _get_env_fallback(name: str) -> Optional[str]:
    """
    回退方案：使用 os.environ 获取环境变量

    Args:
        name: 环境变量名

    Returns:
        环境变量值，如果不存在返回 None
    """
    return os.environ.get(name)


def get_env(name: str) -> Optional[str]:
    """
    获取系统环境变量（跨平台加速版本）

    自动根据操作系统选择最优的读取方式：
    - Windows: 通过 PowerShell 从注册表读取系统级环境变量
    - Linux: 通过 Shell 从 /etc/environment 或 printenv 读取
    - Fallback: 使用 os.environ.get()

    与 os.environ.get() 的区别：
    - os.environ 只读取当前进程继承的环境变量
    - get_env 在 Windows 上可以读取注册表中的系统级配置
    - get_env 在 Linux 上可以读取系统级配置文件

    Args:
        name: 环境变量名

    Returns:
        环境变量值，如果不存在返回 None

    示例：
        >>> get_env("PATH")  # Windows: 从注册表读取系统 PATH
        >>> get_env("HOME")  # Linux: 从 /etc/environment 读取 HOME
        >>> get_env("PATH")  # Linux: 使用 Shell 读取系统 PATH
    """
    # 尝试平台特定的加速方法
    if _IS_WINDOWS:
        result = _get_env_powershell(name)
        if result is not None:
            return result
    elif _IS_LINUX:
        result = _get_env_shell(name)
        if result is not None:
            return result

    # 回退到 os.environ
    return _get_env_fallback(name)


def get_env_with_default(name: str, default: str) -> str:
    """
    获取系统环境变量，带默认值

    Args:
        name: 环境变量名
        default: 默认值

    Returns:
        环境变量值，如果不存在返回 default

    示例：
        >>> get_env_with_default("MY_VAR", "default_value")
    """
    result = get_env(name)
    return result if result is not None else default


__all__ = ['get_env', 'get_env_with_default']
