"""
vools.bridge.nim._loader - Nim 库加载器

处理 Nim 共享库的加载和函数签名设置。
"""

import ctypes
from ..core.loader import load_library, is_available

_NIM_LIBS = {}


def _setup_crypto_funcs(lib):
    """设置 crypto 库函数签名"""
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
    """设置 encoding 库函数签名"""
    lib.base64_encode.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.base64_encode.restype = ctypes.c_char_p
    lib.base64_decode.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.base64_decode.restype = ctypes.c_char_p
    lib.zlib_compress.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.zlib_compress.restype = ctypes.c_char_p
    lib.zlib_decompress.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.zlib_decompress.restype = ctypes.c_char_p


def _setup_seq_funcs(lib):
    """设置 seq 库函数签名"""
    for name in ('seq_map_int', 'seq_filter_int', 'seq_sort_int', 'seq_take_int', 'seq_skip_int'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p, ctypes.c_int]
        fn.restype = ctypes.c_char_p
    for name in ('seq_reduce_sum_int', 'seq_reduce_max_int', 'seq_reduce_min_int',
                 'seq_unique_int', 'seq_count_int', 'seq_reverse_int'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    lib.seq_count_int.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.seq_count_int.restype = ctypes.c_char_p

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


def _setup_datetime_funcs(lib):
    """设置 datetime 库函数签名"""
    lib.dt_is_leap_year.argtypes = [ctypes.c_int]
    lib.dt_is_leap_year.restype = ctypes.c_int
    lib.dt_days_in_month.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.dt_days_in_month.restype = ctypes.c_int
    lib.dt_days_in_year.argtypes = [ctypes.c_int]
    lib.dt_days_in_year.restype = ctypes.c_int
    lib.dt_day_of_week.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_day_of_week.restype = ctypes.c_int
    lib.dt_week_of_year.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_week_of_year.restype = ctypes.c_int
    lib.dt_days_between.argtypes = [ctypes.c_int]*6
    lib.dt_days_between.restype = ctypes.c_int
    lib.dt_ymd_to_ts.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_ymd_to_ts.restype = ctypes.c_int64
    lib.dt_ts_to_ymd.argtypes = [ctypes.c_int64]
    lib.dt_ts_to_ymd.restype = ctypes.c_char_p
    lib.dt_ts_to_ymdhms.argtypes = [ctypes.c_int64]
    lib.dt_ts_to_ymdhms.restype = ctypes.c_char_p
    lib.dt_range_days.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_range_days.restype = ctypes.c_char_p
    lib.dt_range_days_between.argtypes = [ctypes.c_int]*6
    lib.dt_range_days_between.restype = ctypes.c_char_p
    lib.dt_range_months.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_range_months.restype = ctypes.c_char_p
    lib.dt_validate_date.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_validate_date.restype = ctypes.c_int
    lib.dt_add_days.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_add_days.restype = ctypes.c_char_p
    lib.dt_add_months.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.dt_add_months.restype = ctypes.c_char_p


def _setup_curried_funcs(lib):
    """设置 curried 库函数签名"""
    for name in ('cur_sum_int', 'cur_mean_int', 'cur_min_int', 'cur_max_int',
                 'cur_minmax_int', 'cur_stddev_int', 'cur_variance_int',
                 'cur_median_int', 'cur_l2norm_int', 'cur_distinct_int'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    lib.cur_dot_int.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cur_dot_int.restype = ctypes.c_char_p
    lib.cur_count_int.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.cur_count_int.restype = ctypes.c_char_p

    for name in ('cur_sum_float', 'cur_mean_float', 'cur_min_float', 'cur_max_float',
                 'cur_minmax_float', 'cur_stddev_float', 'cur_variance_float',
                 'cur_median_float', 'cur_l2norm_float'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    lib.cur_dot_float.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cur_dot_float.restype = ctypes.c_char_p

    lib.cur_distinct_string.argtypes = [ctypes.c_char_p]
    lib.cur_distinct_string.restype = ctypes.c_char_p
    for name in ('cur_union_string', 'cur_intersect_string', 'cur_diff_string'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    lib.cur_count_string.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cur_count_string.restype = ctypes.c_char_p


_FUNC_SETUPS = {
    'vools_crypto': _setup_crypto_funcs,
    'vools_encoding': _setup_encoding_funcs,
    'vools_seq': _setup_seq_funcs,
    'vools_datetime': _setup_datetime_funcs,
    'vools_curried': _setup_curried_funcs,
}


def get_nim_lib(name):
    """获取 Nim 共享库"""
    if name in _NIM_LIBS:
        return _NIM_LIBS[name]
    lib = load_library('nim', name, _FUNC_SETUPS.get(name))
    _NIM_LIBS[name] = lib
    return lib


def is_nim_available():
    """检查 Nim 是否可用"""
    return get_nim_lib('vools_crypto') is not None
