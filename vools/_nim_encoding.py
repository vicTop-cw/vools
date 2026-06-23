"""
vools/_nim_encoding.py
Nim 加速的编码函数
"""
import base64
import zlib
from ._nim_loader import load_nim_lib

_nim_lib = load_nim_lib('vools_encoding')

# Python 回退
def _py_base64_encode(data):
    return base64.b64encode(data).decode('ascii').rstrip('=')


def _py_base64_decode(data):
    # 添加 padding
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += '=' * padding
    return base64.b64decode(data)


def _py_zlib_compress(data, level=6):
    return zlib.compress(data, level)


def _py_zlib_decompress(data):
    return zlib.decompress(data)


# Nim 实现
def _nim_base64_encode(data):
    result = _nim_lib.base64_encode(data, len(data))
    return result.decode('utf-8')


def _nim_base64_decode(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    result = _nim_lib.base64_decode(data, len(data))
    return result


base64_encode = _nim_base64_encode if _nim_lib else _py_base64_encode
base64_decode = _nim_base64_decode if _nim_lib else _py_base64_decode

# zlib 使用 Python 回退（Nim 的 RLE 压缩不是真正的 zlib）
zlib_compress = _py_zlib_compress
zlib_decompress = _py_zlib_decompress
