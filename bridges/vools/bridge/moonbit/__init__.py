"""vools.bridge.moonbit - MoonBit 语言桥接模块"""

from .compiler import (
    moonbit,
    moonbit_compiler_available,
    MoonBitBridge,
    _moonbit_bridge,
)

moonbit_bridge = _moonbit_bridge

__all__ = [
    'moonbit',
    'moonbit_compiler_available',
    'MoonBitBridge',
    'moonbit_bridge',
]
