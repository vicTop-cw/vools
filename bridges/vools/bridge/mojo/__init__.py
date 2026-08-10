"""
vools.bridge.mojo - Mojo 语言桥接模块

提供 Mojo 1.0b1（Modular）的动态编译与 ctypes 桥接能力。
运行环境：WSL Linux（macOS / 原生 Linux 也可，Windows 原生不支持）。

设计目标：免序列化（serialization-free）跨语言交互
- list 参数走 UnsafePointer[T] + 长度 Int64（不经过 CSV/JSON）
- str / bytes 走 UnsafePointer[c_char]（utf-8 c_char_p，不依赖 Mojo String）
- 通过 transport 模块可注入 zero-copy 实现（zinc / Mojo from Python）

快速开始：
    from vools.bridge.mojo import mojo, mojo_compiler_available

    if not mojo_compiler_available():
        raise RuntimeError('请在 WSL 内安装 Mojo 1.0b1')

    @mojo
    def fib(n: int) -> int:
        return \"\"\"
        if n <= 1:
            return 1
        return fib(n-1) + fib(n-2)
        \"\"\"

    print(fib(10))   # -> 55
"""

from .types import (
    PY_TO_MOJO_TYPE,
    MOJO_TO_CTYPES,
    get_mojo_type,
    get_ctype_for,
    infer_mojo_argtypes,
    is_array_type,
    array_length_type,
)
from .transport import (
    Transport,
    CtypesTransport,
    ZincTransport,
    get_transport,
    set_transport,
)
from .templates import (
    generate_function_signature,
    generate_mojo_wrapper,
    preprocess_mojo_body,
    split_preprocessor_and_body,
)
from .loader import (
    get_mojo_lib,
    is_mojo_available as _is_mojo_precompiled_available,
)
from .compiler import (
    mojo,
    MojoFuture,
    mojo_compiler_available,
    compile_and_run,
    MojoBridge,
    _mojo_bridge,
)


def is_mojo_available() -> bool:
    """
    检查 Mojo 桥接是否可用（编译器或预编译库二选一）

    返回：
        bool: True 表示至少有一种使用方式可用
    """
    return mojo_compiler_available() or _is_mojo_precompiled_available()


__all__ = [
    # 装饰器
    'mojo',
    'MojoFuture',
    # 编译器
    'mojo_compiler_available',
    'compile_and_run',
    'is_mojo_available',
    # LangBridge 实现
    'MojoBridge',
    # 类型映射
    'PY_TO_MOJO_TYPE',
    'MOJO_TO_CTYPES',
    'get_mojo_type',
    'get_ctype_for',
    'infer_mojo_argtypes',
    'is_array_type',
    'array_length_type',
    # Transport
    'Transport',
    'CtypesTransport',
    'ZincTransport',
    'get_transport',
    'set_transport',
    # 加载器
    'get_mojo_lib',
    # 模板
    'generate_function_signature',
    'generate_mojo_wrapper',
    'preprocess_mojo_body',
    'split_preprocessor_and_body',
]
