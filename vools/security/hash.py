"""
vools.security.hash - 安全哈希函数模块

提供常用的哈希函数（SHA256、MD5等），支持 Nim 加速。
当 Nim 桥接库可用时自动使用高性能实现，否则回退到纯 Python 实现。

函数：
    - sha256_hex(data: bytes) -> str: SHA256 哈希（十六进制）
    - md5_hex(data: bytes) -> str: MD5 哈希（十六进制）
    - sha1_hex(data: bytes) -> str: SHA1 哈希（十六进制）
    - sha224_hex(data: bytes) -> str: SHA224 哈希（十六进制）
    - sha384_hex(data: bytes) -> str: SHA384 哈希（十六进制）
    - sha512_hex(data: bytes) -> str: SHA512 哈希（十六进制）
"""

import hashlib
import sys
from typing import Callable

__all__ = [
    'sha256_hex',
    'md5_hex',
    'sha1_hex',
    'sha224_hex',
    'sha384_hex',
    'sha512_hex',
]

# 优先使用 Nim 桥接库（来自 vools.bridge.nim.crypto）
# crypto.py 已经正确实现了 _nim_sha256/_py_sha256 的自动切换
# 注意：必须延迟导入，避免 import vools 时预加载 vools.bridge 子包，
# 否则 vools.BRIDGE_AVAILABLE 标志的翻转逻辑永远不执行。
_nim_available = False
_nim_sha256_impl = None
_nim_md5_impl = None
_nim_sha1_impl = None


def _load_nim_impls() -> None:
    """延迟加载 Nim 桥接实现（仅在需要时导入 vools.bridge）。"""
    global _nim_available, _nim_sha256_impl, _nim_md5_impl, _nim_sha1_impl
    if _nim_available:
        return
    try:
        from ..bridge.nim import sha256 as _sha256_impl
        from ..bridge.nim import md5 as _md5_impl
        from ..bridge.nim import sha1 as _sha1_impl
        _nim_sha256_impl = _sha256_impl
        _nim_md5_impl = _md5_impl
        _nim_sha1_impl = _sha1_impl
        _nim_available = True
    except ImportError:
        _nim_available = False


def _py_sha256_hex(data: bytes) -> str:
    """纯 Python SHA256 实现"""
    return hashlib.sha256(data).hexdigest()


def _py_md5_hex(data: bytes) -> str:
    """纯 Python MD5 实现"""
    return hashlib.md5(data).hexdigest()


def _py_sha1_hex(data: bytes) -> str:
    """纯 Python SHA1 实现"""
    return hashlib.sha1(data).hexdigest()


def _py_sha224_hex(data: bytes) -> str:
    """纯 Python SHA224 实现"""
    return hashlib.sha224(data).hexdigest()


def _py_sha384_hex(data: bytes) -> str:
    """纯 Python SHA384 实现"""
    return hashlib.sha384(data).hexdigest()


def _py_sha512_hex(data: bytes) -> str:
    """纯 Python SHA512 实现"""
    return hashlib.sha512(data).hexdigest()


def _create_bridge_func(nim_func, py_fallback: Callable) -> Callable:
    """
    创建带 Nim 桥接的函数

    Args:
        nim_func: Nim 桥接函数
        py_fallback: Python 回退函数

    Returns:
        桥接函数，当 Nim 不可用时调用回退函数
    """
    if nim_func is None:
        return py_fallback

    def wrapper(data: bytes) -> str:
        try:
            return nim_func(data)
        except Exception:
            return py_fallback(data)

    return wrapper


# SHA256 - hashlib 高度优化，Nim wrapper 开销反而更慢，保持纯 Python
sha256_hex = _py_sha256_hex

# MD5 - hashlib 高度优化，Nim wrapper 开销反而更慢，保持纯 Python
md5_hex = _py_md5_hex

# SHA1 - hashlib 高度优化，Nim wrapper 开销反而更慢，保持纯 Python
sha1_hex = _py_sha1_hex

# SHA224 - vools.bridge.nim.crypto 不提供 sha224，直接用纯 Python
sha224_hex = _py_sha224_hex

# SHA384 - vools.bridge.nim.crypto 不提供 sha384，直接用纯 Python
sha384_hex = _py_sha384_hex

# SHA512 - vools.bridge.nim.crypto 不提供 sha512，直接用纯 Python
sha512_hex = _py_sha512_hex
