"""
vools.bridge.cypy - Cypy 语言桥接模块

Cypy 是一门 Python-like 语言，编译器 cypyc 将其转译为 Cython（.pyx）再编译为高性能 C 扩展。
本模块提供：

- @cypy 装饰器：将 Python 函数转换为 Cypy 代码（函数体即 Cypy 代码）
- compile_and_run：直接转译一段 Cypy 源码
- CypyBridge：继承 LangBridge 的桥接实现

使用示例::

    from vools.bridge.cypy import cypy, cypy_compiler_available

    if cypy_compiler_available():
        @cypy
        def hello() -> str:
            return "print(1 + 2)"

        # 环境支持完整编译时返回执行输出；否则返回转译的 .pyx 路径
        print(hello())

前置条件：
- cypyc 工具链（pip install cypyc 后可用，或 E:\\IDEProjects\\AI\\Cypy 源码）
- 完整执行链路需要 Python C API 头文件（Python.h）+ C 编译器（MSVC cl / gcc）
"""

from .compiler import (
    CypyBridge,
    cypy,
    _cypy_bridge,
    compile_and_run,
    cypy_compiler_available,
    cypy_run_available,
    get_cypy_version,
    get_cypy_type,
)

cypy_bridge = _cypy_bridge

__all__ = [
    'CypyBridge',
    'cypy',
    'cypy_bridge',
    'compile_and_run',
    'cypy_compiler_available',
    'cypy_run_available',
    'get_cypy_version',
    'get_cypy_type',
]
