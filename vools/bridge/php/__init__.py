"""vools.bridge.php - PHP 语言桥接模块"""

from .compiler import (
    php,
    phpe,
    php_compiler_available,
    compile_and_run,
    PHPFuture,
    PHPBridge,
    _php_bridge,
)
from .types import PY_TO_PHP_TYPE, PHP_TO_CTYPES, get_php_type, get_php_ctype

php_bridge = _php_bridge

__all__ = [
    'php',
    'phpe',
    'php_compiler_available',
    'compile_and_run',
    'PHPFuture',
    'PHPBridge',
    'php_bridge',
    'PY_TO_PHP_TYPE',
    'PHP_TO_CTYPES',
    'get_php_type',
    'get_php_ctype',
]