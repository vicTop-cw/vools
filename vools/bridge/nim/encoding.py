"""
vools.bridge.nim.encoding - Nim 编码函数桥接
"""

import base64
import zlib

from ._loader import get_nim_lib

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


# Nim 实现
def _nim_base64_encode(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return _nim_lib.base64_encode(data, len(data)).decode('utf-8')


def _nim_base64_decode(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return _nim_lib.base64_decode(data, len(data)).decode('utf-8')


def _nim_zlib_compress(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return _nim_lib.zlib_compress(data, len(data)).decode('latin-1')


def _nim_zlib_decompress(data):
    if isinstance(data, str):
        data = data.encode('latin-1')
    return _nim_lib.zlib_decompress(data, len(data)).decode('utf-8')


# 公开 API
base64_encode = _nim_base64_encode if _nim_lib else _py_base64_encode
base64_decode = _nim_base64_decode if _nim_lib else _py_base64_decode
zlib_compress = _nim_zlib_compress if _nim_lib else _py_zlib_compress
zlib_decompress = _nim_zlib_decompress if _nim_lib else _py_zlib_decompress
