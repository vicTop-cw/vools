"""
vools/_nim_crypto.py
Nim 加速的加密函数，优先使用 Nim DLL，不存在则回退 Python
"""
import hashlib
import hmac as _py_hmac
from ._nim_loader import load_nim_lib

# 尝试加载 Nim DLL
_nim_lib = load_nim_lib('vools_crypto')

# Python 回退实现
def _py_md5(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.md5(data).hexdigest()


def _py_sha1(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha1(data).hexdigest()


def _py_sha256(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _py_hmac_sha256(data, key):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(key, str):
        key = key.encode('utf-8')
    return _py_hmac.new(key, data, hashlib.sha256).hexdigest()


def _py_hmac_md5(data, key):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(key, str):
        key = key.encode('utf-8')
    return _py_hmac.new(key, data, hashlib.md5).hexdigest()


def _nim_md5(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    result = _nim_lib.md5_hash(data, len(data))
    return result.decode('utf-8')


def _nim_sha1(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    result = _nim_lib.sha1_hash(data, len(data))
    return result.decode('utf-8')


def _nim_sha256(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    result = _nim_lib.sha256_hash(data, len(data))
    return result.decode('utf-8')


def _nim_hmac_sha256(data, key):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(key, str):
        key = key.encode('utf-8')
    result = _nim_lib.hmac_sha256(data, len(data), key, len(key))
    return result.decode('utf-8')


def _nim_hmac_md5(data, key):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(key, str):
        key = key.encode('utf-8')
    result = _nim_lib.hmac_md5(data, len(data), key, len(key))
    return result.decode('utf-8')


# 根据是否可用 Nim 选择实现
md5 = _nim_md5 if _nim_lib else _py_md5
sha1 = _nim_sha1 if _nim_lib else _py_sha1
sha256 = _nim_sha256 if _nim_lib else _py_sha256
hmac_sha256 = _nim_hmac_sha256 if _nim_lib else _py_hmac_sha256
hmac_md5 = _nim_hmac_md5 if _nim_lib else _py_hmac_md5


def is_nim_available():
    return _nim_lib is not None
