"""
vools.bridge.vbnet - VB.NET 语言桥接模块

提供 VB.NET 代码的动态编译和 DLL 调用能力。

前置条件：
- 安装 .NET SDK (dotnet) 并添加到 PATH
- 或提供预编译的 VB.NET DLL

用法：
    from vools.bridge.vbnet import vbnet, compile_and_run

    @vbnet
    def add(a: int, b: int) -> int:
        return "Return a + b"

    result = add(1, 2)  # 自动编译并调用

    # 异步执行
    @vbnet(async_mode=True)
    async def compute(x: int) -> int:
        return "Return x * x"

    result = await compute(5)

    # 直接运行代码
    result = compile_and_run("Return 42", args=())
"""

from .compiler import (
    vbnet,
    vb,
    vbnet_compiler_available,
    compile_and_run,
    VBNetFuture,
    VBNetBridge,
    _vbnet_bridge,
)
from .types import (
    PY_TO_VB_TYPE,
    VB_TO_CTYPES,
    get_vb_type,
    get_vb_ctype,
)

vbnet_bridge = _vbnet_bridge

__all__ = [
    'vbnet',
    'vb',
    'vbnet_compiler_available',
    'compile_and_run',
    'VBNetFuture',
    'VBNetBridge',
    'vbnet_bridge',
    'PY_TO_VB_TYPE',
    'VB_TO_CTYPES',
    'get_vb_type',
    'get_vb_ctype',
]
