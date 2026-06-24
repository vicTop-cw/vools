"""
vools.bridge.csharp - C# 语言桥接模块

提供 C# 代码的动态编译和 DLL 调用能力。

前置条件：
- 安装 .NET SDK (dotnet) 并添加到 PATH
- 或提供预编译的 C# DLL

用法：
    from vools.bridge.csharp import csharp, compile_and_run

    @csharp
    def add(a: int, b: int) -> int:
        return "return a + b;"

    result = add(1, 2)  # 自动编译并调用

    # 异步执行
    @csharp(async_mode=True)
    async def compute(x: int) -> int:
        return "return x * x;"

    result = await compute(5)

    # 直接运行代码
    result = compile_and_run("return 42;", args=())
"""

from .compiler import (
    csharp,
    cs,
    csharp_compiler_available,
    compile_and_run,
    CsharpFuture,
    CSharpBridge,
    _csharp_bridge,
)
from .loader import get_cs_lib, is_csharp_available
from .types import (
    PY_TO_CS_TYPE,
    CS_TO_CTYPES,
    get_cs_type,
    get_cs_ctype,
)

csharp_bridge = _csharp_bridge

__all__ = [
    'csharp',
    'cs',
    'csharp_compiler_available',
    'compile_and_run',
    'CsharpFuture',
    'CSharpBridge',
    'csharp_bridge',
    'get_cs_lib',
    'is_csharp_available',
    'PY_TO_CS_TYPE',
    'CS_TO_CTYPES',
    'get_cs_type',
    'get_cs_ctype',
]