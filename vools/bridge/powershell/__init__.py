"""vools.bridge.powershell - PowerShell 语言桥接模块"""

from .compiler import (
    powershell,
    ps,
    powershell_compiler_available,
    compile_and_run,
    PowerShellFuture,
    PowerShellBridge,
    _powershell_bridge,
)
from .types import PY_TO_PS_TYPE, PS_TO_CTYPES, get_ps_type, get_ps_ctype

powershell_bridge = _powershell_bridge

__all__ = [
    'powershell',
    'ps',
    'powershell_compiler_available',
    'compile_and_run',
    'PowerShellFuture',
    'PowerShellBridge',
    'powershell_bridge',
    'PY_TO_PS_TYPE',
    'PS_TO_CTYPES',
    'get_ps_type',
    'get_ps_ctype',
]
