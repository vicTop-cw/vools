"""vools.bridge.zig - Zig 语言桥接模块"""

from .compiler import (
    zig,
    zigc,
    zig_compiler_available,
    compile_and_run,
    ZigFuture,
    ZigBridge,
    _zig_bridge,
)
from .types import PY_TO_ZIG_TYPE, ZIG_TO_CTYPES, get_zig_type, get_zig_ctype

zig_bridge = _zig_bridge

__all__ = [
    'zig',
    'zigc',
    'zig_compiler_available',
    'compile_and_run',
    'ZigFuture',
    'ZigBridge',
    'zig_bridge',
    'PY_TO_ZIG_TYPE',
    'ZIG_TO_CTYPES',
    'get_zig_type',
    'get_zig_ctype',
]
