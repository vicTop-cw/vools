"""vools.bridge.vbscript - VBScript 语言桥接模块"""

from .compiler import (
    vbscript,
    vbs,
    vbscript_compiler_available,
    compile_and_run,
    VBScriptFuture,
    VBScriptBridge,
    _vbscript_bridge,
)
from .types import PY_TO_VBS_TYPE, VBS_TO_CTYPES, get_vbs_type, get_vbs_ctype

vbscript_bridge = _vbscript_bridge

__all__ = [
    'vbscript',
    'vbs',
    'vbscript_compiler_available',
    'compile_and_run',
    'VBScriptFuture',
    'VBScriptBridge',
    'vbscript_bridge',
    'PY_TO_VBS_TYPE',
    'VBS_TO_CTYPES',
    'get_vbs_type',
    'get_vbs_ctype',
]
