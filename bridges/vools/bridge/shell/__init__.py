"""vools.bridge.shell - Shell/Bash 语言桥接模块"""

from .compiler import (
    shell,
    sh,
    bash,
    shell_compiler_available,
    bash_compiler_available,
    compile_and_run,
    ShellFuture,
    ShellBridge,
    _shell_bridge,
)
from .types import PY_TO_SHELL_TYPE, SHELL_TO_CTYPES, get_shell_type, get_shell_ctype

shell_bridge = _shell_bridge

__all__ = [
    'shell',
    'sh',
    'bash',
    'shell_compiler_available',
    'bash_compiler_available',
    'compile_and_run',
    'ShellFuture',
    'ShellBridge',
    'shell_bridge',
    'PY_TO_SHELL_TYPE',
    'SHELL_TO_CTYPES',
    'get_shell_type',
    'get_shell_ctype',
]
