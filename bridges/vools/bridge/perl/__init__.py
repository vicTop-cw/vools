"""vools.bridge.perl - Perl 语言桥接模块"""

from .compiler import (
    perl,
    pl,
    perl_compiler_available,
    compile_and_run,
    PerlFuture,
    PerlBridge,
    _perl_bridge,
)
from .types import PY_TO_PERL_TYPE, PERL_TO_CTYPES, get_perl_type, get_perl_ctype

perl_bridge = _perl_bridge

__all__ = [
    'perl',
    'pl',
    'perl_compiler_available',
    'compile_and_run',
    'PerlFuture',
    'PerlBridge',
    'perl_bridge',
    'PY_TO_PERL_TYPE',
    'PERL_TO_CTYPES',
    'get_perl_type',
    'get_perl_ctype',
]