"""
vools.bridge.nim.encoding - Nim 编码函数桥接
"""

import base64
import zlib

from ._loader import get_nim_lib
from .base64_shim import base64_encode as _shim_base64_encode, base64_decode as _shim_base64_decode
from ..core.decorators import bridge_function

_nim_lib = get_nim_lib('vools_encoding')


# Python 回退实现
def _py_base64_encode(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.b64encode(data).decode('utf-8')


def _py_base64_decode(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.b64decode(data).decode('utf-8')


def _py_zlib_compress(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return zlib.compress(data).decode('latin-1')


def _py_zlib_decompress(data):
    if isinstance(data, str):
        data = data.encode('latin-1')
    return zlib.decompress(data).decode('utf-8')


# 使用 @bridge_function 装饰器提供 Nim 加速
# fallback 到纯 Python 实现

@bridge_function("nim", fallback=_py_base64_encode, lib_name="vools_encoding", func_name="base64_encode")
def base64_encode(data):
    """Base64 编码，优先使用 Nim 加速"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.b64encode(data).decode('utf-8')


@bridge_function("nim", fallback=_py_base64_decode, lib_name="vools_encoding", func_name="base64_decode")
def base64_decode(data):
    """Base64 解码，优先使用 Nim 加速"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return base64.b64decode(data).decode('utf-8')


# zlib 函数保持现有实现（使用 vools_encoding.dll）
def _py_zlib_compress(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return zlib.compress(data).decode('latin-1')


def _py_zlib_decompress(data):
    if isinstance(data, str):
        data = data.encode('latin-1')
    return zlib.decompress(data).decode('utf-8')


def _nim_zlib_compress(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return _nim_lib.zlib_compress(data, len(data)).decode('latin-1')


def _nim_zlib_decompress(data):
    if isinstance(data, str):
        data = data.encode('latin-1')
    return _nim_lib.zlib_decompress(data, len(data)).decode('utf-8')


# 公开 API
zlib_compress = _nim_zlib_compress if _nim_lib else _py_zlib_compress
zlib_decompress = _nim_zlib_decompress if _nim_lib else _py_zlib_decompress
