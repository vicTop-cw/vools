"""
vools/_nim_loader.py
Nim DLL 自动检测与加载器
首次导入时检测 DLL 是否存在，存在则加载，不存在则静默回退 Python
"""
import os
import sys
import ctypes

# 查找 DLL 的目录（与本文件同目录的 lib/ 子目录）
_LIB_DIR = os.path.join(os.path.dirname(__file__), 'lib')

# 已加载的 DLL 缓存
_LOADED_LIBS = {}

# Nim DLL 依赖的运行时库搜索路径（开发期）
_NIM_RUNTIME_PATHS = [
    r"C:\Users\victo\.codearts-cpp\tools\mingw\bin",
    r"E:\Dowloads\nim-2.2.10_x64\nim-2.2.10\bin",
]


def _add_nim_runtime_path():
    """将 Nim 运行时库路径加入 DLL 搜索（一次性）"""
    for p in _NIM_RUNTIME_PATHS:
        if os.path.exists(p):
            try:
                os.add_dll_directory(p)
            except (AttributeError, OSError):
                pass
            # 同时设置 PATH 兜底
            cur = os.environ.get('PATH', '')
            if p not in cur:
                os.environ['PATH'] = p + os.pathsep + cur


_add_nim_runtime_path()


def _find_dll(name):
    """查找 DLL，返回完整路径或 None"""
    for ext in ('.dll', '.so', '.pyd', ''):
        path = os.path.join(_LIB_DIR, name + ext)
        if os.path.exists(path):
            return path
    return None


# ============================================================
# DLL 函数签名设置
# ============================================================

def _setup_crypto_funcs(lib):
    """设置 crypto DLL 的函数签名"""
    lib.md5_hash.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.md5_hash.restype = ctypes.c_char_p
    lib.sha1_hash.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.sha1_hash.restype = ctypes.c_char_p
    lib.sha256_hash.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.sha256_hash.restype = ctypes.c_char_p
    lib.hmac_sha256.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.hmac_sha256.restype = ctypes.c_char_p
    lib.hmac_md5.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.hmac_md5.restype = ctypes.c_char_p


def _setup_encoding_funcs(lib):
    """设置 encoding DLL 的函数签名"""
    lib.base64_encode.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.base64_encode.restype = ctypes.c_char_p
    lib.base64_decode.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.base64_decode.restype = ctypes.c_char_p
    lib.base64_decode_len.argtypes = [ctypes.c_int]
    lib.base64_decode_len.restype = ctypes.c_int
    lib.zlib_compress.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.zlib_compress.restype = ctypes.c_char_p
    lib.zlib_decompress.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.zlib_decompress.restype = ctypes.c_char_p


def _setup_seq_funcs(lib):
    """设置 seq DLL 的函数签名（CSV cstring 接口）"""
    # int 系列
    for name in ('seq_map_int', 'seq_filter_int', 'seq_sort_int', 'seq_take_int', 'seq_skip_int'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p, ctypes.c_int]
        fn.restype = ctypes.c_char_p
    for name in ('seq_reduce_sum_int', 'seq_reduce_max_int', 'seq_reduce_min_int',
                 'seq_unique_int', 'seq_count_int', 'seq_reverse_int'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    # seq_count_int 实际是 (cstring, cint)
    lib.seq_count_int.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_count_int.restype = ctypes.c_char_p
    # float 系列
    for name in ('seq_map_float', 'seq_filter_float', 'seq_count_float'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    for name in ('seq_reduce_sum_float', 'seq_reduce_max_float', 'seq_reduce_min_float',
                 'seq_unique_float', 'seq_reverse_float', 'seq_sort_float'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    lib.seq_sort_float.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_sort_float.restype = ctypes.c_char_p
    # string 系列
    lib.seq_map_string.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.seq_map_string.restype = ctypes.c_char_p
    lib.seq_filter_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_filter_string.restype = ctypes.c_char_p
    lib.seq_sort_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_sort_string.restype = ctypes.c_char_p
    lib.seq_count_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_count_string.restype = ctypes.c_char_p
    for name in ('seq_unique_string', 'seq_reverse_string', 'seq_take_string', 'seq_skip_string'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    lib.seq_take_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_take_string.restype = ctypes.c_char_p
    lib.seq_skip_string.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_skip_string.restype = ctypes.c_char_p


_FUNC_SETUPS = {
    'vools_crypto': _setup_crypto_funcs,
    'vools_encoding': _setup_encoding_funcs,
    'vools_seq': _setup_seq_funcs,
}


def load_nim_lib(name):
    """加载 Nim DLL，返回 ctypes CDLL 对象，失败返回 None"""
    if name in _LOADED_LIBS:
        return _LOADED_LIBS[name]

    path = _find_dll(name)
    if path is None:
        _LOADED_LIBS[name] = None
        return None

    try:
        lib = ctypes.CDLL(path)
        setup_func = _FUNC_SETUPS.get(name)
        if setup_func:
            setup_func(lib)
        _LOADED_LIBS[name] = lib
        return lib
    except Exception:
        _LOADED_LIBS[name] = None
        return None


def is_nim_available():
    """检测是否有任何 Nim DLL 可用"""
    return load_nim_lib('vools_crypto') is not None
