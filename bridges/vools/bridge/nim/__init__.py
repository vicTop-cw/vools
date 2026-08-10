"""
vools.bridge.nim - Nim 语言桥接模块

提供 Nim 加速的高性能函数，自动回退到 Python 实现。
"""

from .sigcache_shim import (
    hash_signature,
    hash_signature_int,
    build_signature_str,
    signature_hash_from_inspect,
    is_available as is_sigcache_available,
)
from .crypto import md5, sha1, sha256, hmac_sha256, hmac_md5
from .seq import (
    seq_map_int, seq_filter_int, seq_reduce_sum_int, seq_reduce_max_int,
    seq_reduce_min_int, seq_sort_int, seq_unique_int, seq_count_int,
    seq_reverse_int, seq_take_int, seq_skip_int,
    seq_map_float, seq_filter_float, seq_reduce_sum_float, seq_reduce_max_float,
    seq_reduce_min_float, seq_sort_float, seq_unique_float, seq_count_float,
    seq_reverse_float,
    seq_map_string, seq_filter_string, seq_sort_string, seq_unique_string,
    seq_count_string, seq_reverse_string, seq_take_string, seq_skip_string,
)
from .datetime import (
    dt_is_leap_year, dt_days_in_month, dt_days_in_year, dt_day_of_week,
    dt_week_of_year, dt_days_between, dt_ymd_to_ts, dt_ts_to_ymd,
    dt_ts_to_ymdhms, dt_range_days, dt_range_days_between, dt_range_months,
    dt_validate_date, dt_add_days, dt_add_months,
)
from .curried import (
    cur_sum_int, cur_mean_int, cur_min_int, cur_max_int, cur_minmax_int,
    cur_stddev_int, cur_variance_int, cur_median_int, cur_l2norm_int,
    cur_distinct_int, cur_dot_int, cur_count_int,
    cur_sum_float, cur_mean_float, cur_min_float, cur_max_float,
    cur_minmax_float, cur_stddev_float, cur_variance_float, cur_median_float,
    cur_l2norm_float, cur_dot_float,
    cur_distinct_string, cur_union_string, cur_intersect_string,
    cur_diff_string, cur_count_string,
)
from .encoding import base64_encode, base64_decode, zlib_compress, zlib_decompress
from .serialize_shim import (
    pickle_encode as nim_pickle_encode,
    pickle_decode as nim_pickle_decode,
    msgpack_encode as nim_msgpack_encode,
    msgpack_decode as nim_msgpack_decode,
    is_available as is_serialize_available,
)
from .json_shim import (
    json_encode as nim_json_encode,
    json_decode as nim_json_decode,
    json_encode_bytes as nim_json_encode_bytes,
    json_decode_bytes as nim_json_decode_bytes,
    is_available as is_json_available,
)

from ._loader import is_nim_available
from .compiler import nim, compile_and_run, nim_compiler_available

__all__ = [
    # sigcache 模块
    'hash_signature', 'hash_signature_int', 'build_signature_str',
    'signature_hash_from_inspect', 'is_sigcache_available',
    # crypto 模块
    'md5', 'sha1', 'sha256', 'hmac_sha256', 'hmac_md5',
    'seq_map_int', 'seq_filter_int', 'seq_reduce_sum_int', 'seq_reduce_max_int',
    'seq_reduce_min_int', 'seq_sort_int', 'seq_unique_int', 'seq_count_int',
    'seq_reverse_int', 'seq_take_int', 'seq_skip_int',
    'seq_map_float', 'seq_filter_float', 'seq_reduce_sum_float', 'seq_reduce_max_float',
    'seq_reduce_min_float', 'seq_sort_float', 'seq_unique_float', 'seq_count_float',
    'seq_reverse_float',
    'seq_map_string', 'seq_filter_string', 'seq_sort_string', 'seq_unique_string',
    'seq_count_string', 'seq_reverse_string', 'seq_take_string', 'seq_skip_string',
    'dt_is_leap_year', 'dt_days_in_month', 'dt_days_in_year', 'dt_day_of_week',
    'dt_week_of_year', 'dt_days_between', 'dt_ymd_to_ts', 'dt_ts_to_ymd',
    'dt_ts_to_ymdhms', 'dt_range_days', 'dt_range_days_between', 'dt_range_months',
    'dt_validate_date', 'dt_add_days', 'dt_add_months',
    'cur_sum_int', 'cur_mean_int', 'cur_min_int', 'cur_max_int', 'cur_minmax_int',
    'cur_stddev_int', 'cur_variance_int', 'cur_median_int', 'cur_l2norm_int',
    'cur_distinct_int', 'cur_dot_int', 'cur_count_int',
    'cur_sum_float', 'cur_mean_float', 'cur_min_float', 'cur_max_float',
    'cur_minmax_float', 'cur_stddev_float', 'cur_variance_float', 'cur_median_float',
    'cur_l2norm_float', 'cur_dot_float',
    'cur_distinct_string', 'cur_union_string', 'cur_intersect_string',
    'cur_diff_string', 'cur_count_string',
    'base64_encode', 'base64_decode', 'zlib_compress', 'zlib_decompress',
    'nim_pickle_encode', 'nim_pickle_decode',
    'nim_msgpack_encode', 'nim_msgpack_decode',
    'nim_json_encode', 'nim_json_decode',
    'nim_json_encode_bytes', 'nim_json_decode_bytes',
    'is_nim_available', 'is_serialize_available', 'is_json_available',
    'nim_compiler_available',
    'nim', 'compile_and_run',
]
