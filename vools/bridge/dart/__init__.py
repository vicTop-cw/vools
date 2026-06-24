"""vools.bridge.dart - Dart 语言桥接模块"""

from .compiler import (
    dart,
    dartexe,
    dart_compiler_available,
    compile_and_run,
    DartFuture,
    DartBridge,
    _dart_bridge,
)
from .types import PY_TO_DART_TYPE, DART_TO_CTYPES, get_dart_type, get_dart_ctype

dart_bridge = _dart_bridge

__all__ = [
    'dart',
    'dartexe',
    'dart_compiler_available',
    'compile_and_run',
    'DartFuture',
    'DartBridge',
    'dart_bridge',
    'PY_TO_DART_TYPE',
    'DART_TO_CTYPES',
    'get_dart_type',
    'get_dart_ctype',
]
