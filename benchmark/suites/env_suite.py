"""
benchmark.suites.env_suite - 系统环境变量读取基准测试套件

对比 os.environ.get() vs PowerShell/Shell 桥接方式的环境变量读取性能。

注意：PowerShell/Shell 方式的优势不在于速度，而在于可以读取系统级
环境变量（Windows 注册表、Linux /etc/environment），而不只是进程级环境变量。

测试变量：
- PATH: 常用环境变量，包含多个路径
- HOME/LUSERPROFILE: 用户目录变量
- SYSTEMROOT: Windows 系统目录
"""

import os
import platform
from typing import Dict, List, Any

# 平台检测
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX = platform.system() == 'Linux'

# 测试用的环境变量名
_TEST_VARS = ['PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'USERNAME', 'TEMP']

# 尝试导入桥接版本
_bridge_available = False
_bridge_get_env = None

try:
    from vools.sys.env import get_env as bridge_get_env
    _bridge_get_env = bridge_get_env
    _bridge_available = True
except ImportError:
    pass


def get_env_py(name: str) -> str:
    """
    纯 Python 版本：使用 os.environ.get() 读取环境变量

    Args:
        name: 环境变量名

    Returns:
        环境变量值，不存在返回空字符串
    """
    return os.environ.get(name, '')


def get_env_bridge(name: str) -> str:
    """
    桥接版本：使用 PowerShell/Shell 读取系统环境变量

    Args:
        name: 环境变量名

    Returns:
        环境变量值，不存在返回空字符串
    """
    if _bridge_get_env:
        result = _bridge_get_env(name)
        return result if result is not None else ''
    return get_env_py(name)


def get_env_suite() -> List[Dict[str, Any]]:
    """
    获取环境变量读取基准测试套件

    Returns:
        测试用例列表
    """
    test_cases = []

    for var_name in _TEST_VARS:
        # 过滤在当前平台不存在的变量
        if var_name == 'HOME' and _IS_WINDOWS:
            continue
        if var_name == 'USERPROFILE' and not _IS_WINDOWS:
            continue
        if var_name == 'SYSTEMROOT' and not _IS_WINDOWS:
            continue

        test_cases.append({
            "name": f"sys.env.get_env_{var_name.lower()}",
            "py_func": get_env_py,
            "bridge_func": get_env_bridge if _bridge_available else None,
            "args": (var_name,),
            "expected_speedup": 0.5,  # 可能比纯 Python 慢，但提供更多功能
        })

    return test_cases


class EnvSuite:
    """环境变量基准测试套件类"""

    name = "sys.env"

    @staticmethod
    def get_tests() -> Dict[str, Any]:
        """获取所有环境变量测试"""
        return {
            var_name.lower(): (get_env_bridge if _bridge_available else get_env_py, var_name)
            for var_name in _TEST_VARS
        }

    @staticmethod
    def get_pure_python_tests() -> Dict[str, Any]:
        """获取纯 Python 测试"""
        return {
            var_name.lower(): (get_env_py, var_name)
            for var_name in _TEST_VARS
        }


if __name__ == '__main__':
    # 简单测试
    print(f"平台: {'Windows' if _IS_WINDOWS else 'Linux'}")
    print(f"桥接可用: {_bridge_available}")
    print()

    for var_name in ['PATH', 'HOME', 'USERPROFILE', 'TEMP']:
        if var_name == 'HOME' and _IS_WINDOWS:
            continue
        if var_name == 'USERPROFILE' and not _IS_WINDOWS:
            continue

        py_result = get_env_py(var_name)
        py_len = len(py_result)

        if _bridge_available:
            bridge_result = get_env_bridge(var_name)
            bridge_len = len(bridge_result)
            match = "✓" if py_result == bridge_result else "✗"
            print(f"{var_name}: py={py_len} chars, bridge={bridge_len} chars {match}")
        else:
            print(f"{var_name}: py={py_len} chars (bridge unavailable)")
