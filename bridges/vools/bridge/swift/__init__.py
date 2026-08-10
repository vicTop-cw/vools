"""vools.bridge.swift - Swift 语言桥接模块"""

from .compiler import (
    swift,
    swiftc,
    swift_compiler_available,
    compile_and_run,
    SwiftFuture,
    SwiftBridge,
    _swift_bridge,
)
from .types import PY_TO_SWIFT_TYPE, SWIFT_TO_CTYPES, get_swift_type, get_swift_ctype

swift_bridge = _swift_bridge

__all__ = [
    'swift',
    'swiftc',
    'swift_compiler_available',
    'compile_and_run',
    'SwiftFuture',
    'SwiftBridge',
    'swift_bridge',
    'PY_TO_SWIFT_TYPE',
    'SWIFT_TO_CTYPES',
    'get_swift_type',
    'get_swift_ctype',
]