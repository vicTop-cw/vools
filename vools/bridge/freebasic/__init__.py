"""
vools.bridge.freebasic - FreeBASIC 语言桥接模块

提供 FreeBASIC 动态编译与跨语言桥接能力，对齐 vools.bridge.nim 的 API 形态。

设计目标：免序列化（serialization-free）交互
- list 参数走 POINTER + 长度，不走 CSV/JSON
- 通过 transport 模块可注入 zero-copy 实现（如 zinc）

前置条件：
- 安装 FreeBASIC，并将 fbc64 加入 PATH
- 参考: https://www.freebasic.net/

使用示例：
    from vools.bridge.freebasic import fbc, compile_and_run, fbc_compiler_available

    if fbc_compiler_available():
        @fbc
        def fib(n: int) -> int:
            return '''
            If n <= 1 Then
                Return 1
            Else
                Return fib(n-1) + fib(n-2)
            End If
            '''

        print(fib(10))
"""

from .types import (
    PY_TO_FB_TYPE,
    FB_TO_CTYPES,
    get_fb_type,
    infer_fb_argtypes,
    is_array_type,
    get_ctype_for,
)
from .transport import (
    Transport,
    CtypesTransport,
    ZincTransport,
    get_transport,
    set_transport,
)
from .loader import get_fbc_lib, is_fbc_available
from .compiler import (
    FbcBridge,
    _fbc_bridge,
    fbc,
    compile_and_run,
    compile_and_run_async,
    fbc_compiler_available,
    FbcFuture,
    _compile_fbc_code,
    _call_fbc_func,
    _generate_fbc_wrapper,
    _BAS_CACHE_DIR,
)

__all__ = [
    # 桥接类
    'FbcBridge',
    '_fbc_bridge',
    # 类型映射
    'PY_TO_FB_TYPE',
    'FB_TO_CTYPES',
    'get_fb_type',
    'infer_fb_argtypes',
    'is_array_type',
    'get_ctype_for',
    # Transport
    'Transport',
    'CtypesTransport',
    'ZincTransport',
    'get_transport',
    'set_transport',
    # 库加载
    'get_fbc_lib',
    'is_fbc_available',
    # 编译器
    'fbc',
    'compile_and_run',
    'compile_and_run_async',
    'fbc_compiler_available',
    'FbcFuture',
    '_compile_fbc_code',
    '_call_fbc_func',
    '_generate_fbc_wrapper',
    '_BAS_CACHE_DIR',
]
