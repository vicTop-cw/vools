"""vools.bridge.kotlin - Kotlin 语言桥接模块"""

from .compiler import (
    kotlin,
    kt,
    is_kotlin_compiler_available,
    compile_and_run,
    KotlinFuture,
    KotlinBridge,
    _kotlin_bridge,
)
from .types import PY_TO_KOTLIN_TYPE, KOTLIN_TO_CTYPES, get_kotlin_type, get_kotlin_ctype

kotlin_bridge = _kotlin_bridge

__all__ = [
    'kotlin',
    'kt',
    'is_kotlin_compiler_available',
    'kotlin_compiler_available',
    'compile_and_run',
    'KotlinFuture',
    'KotlinBridge',
    'kotlin_bridge',
    'PY_TO_KOTLIN_TYPE',
    'KOTLIN_TO_CTYPES',
    'get_kotlin_type',
    'get_kotlin_ctype',
]

# Alias for API compatibility
kotlin_compiler_available = is_kotlin_compiler_available
