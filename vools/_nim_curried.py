"""
vools/_nim_curried.py (Deprecated)

This module is deprecated and will be removed in a future version.
Use vools.bridge.nim.curried instead.
"""

import warnings

warnings.warn(
    "vools._nim_curried is deprecated, use vools.bridge.nim.curried instead",
    DeprecationWarning,
    stacklevel=2
)

from .bridge.nim.curried import (
    cur_sum_int, cur_mean_int, cur_min_int, cur_max_int, cur_minmax_int,
    cur_stddev_int, cur_variance_int, cur_median_int, cur_l2norm_int,
    cur_distinct_int, cur_dot_int, cur_count_int,
    cur_sum_float, cur_mean_float, cur_min_float, cur_max_float,
    cur_minmax_float, cur_stddev_float, cur_variance_float, cur_median_float,
    cur_l2norm_float, cur_dot_float,
    cur_distinct_string, cur_union_string, cur_intersect_string,
    cur_diff_string, cur_count_string,
)

def is_nim_curried_available():
    from .bridge.nim._loader import is_nim_available as _is_avail
    return _is_avail()
