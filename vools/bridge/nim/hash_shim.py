"""
vools.bridge.nim.hash_shim - Nim 哈希库 Python 胶水层

使用 ctypes 加载编译好的 Nim 哈希共享库，提供类型安全的函数调用。
当库不可用时，_lib 为 None，hash.py 会使用纯 Python 回退。
"""

import ctypes
import sys
import os
from pathlib import Path

__all__ = ['_lib']

# 查找库路径
_lib_base = Path(__file__).parent.parent.parent / "lib"
if sys.platform == "win32":
    _LIB_PATH = _lib_base / "windows" / "vools_crypto.dll"
else:
    _LIB_PATH = _lib_base / "linux" / "libvools_crypto.so"

# 尝试加载库
_lib = None

if _LIB_PATH.exists():
    try:
        _lib = ctypes.CDLL(str(_LIB_PATH))

        # 设置函数签名（仅包含 vools_crypto.dll 中实际存在的函数）
        _lib.sha256_hash.argtypes = [ctypes.c_char_p, ctypes.c_int]
        _lib.sha256_hash.restype = ctypes.c_char_p

        _lib.md5_hash.argtypes = [ctypes.c_char_p, ctypes.c_int]
        _lib.md5_hash.restype = ctypes.c_char_p

        _lib.sha1_hash.argtypes = [ctypes.c_char_p, ctypes.c_int]
        _lib.sha1_hash.restype = ctypes.c_char_p

        _lib.hmac_sha256.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _lib.hmac_sha256.restype = ctypes.c_char_p

        _lib.hmac_md5.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _lib.hmac_md5.restype = ctypes.c_char_p

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Failed to load Nim hash library from {_LIB_PATH}: {e}"
        )
        _lib = None
else:
    import logging
    logging.getLogger(__name__).debug(
        f"Nim hash library not found at {_LIB_PATH}, using Python fallback"
    )
