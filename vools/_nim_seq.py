"""
vools/_nim_seq.py (Deprecated)

This module is deprecated and will be removed in a future version.
Use vools.bridge.nim.seq instead.
"""

import warnings

warnings.warn(
    "vools._nim_seq is deprecated, use vools.bridge.nim.seq instead",
    DeprecationWarning,
    stacklevel=2
)

from .bridge.nim.seq import (
    seq_map_int, seq_filter_int, seq_reduce_sum_int, seq_reduce_max_int,
    seq_reduce_min_int, seq_sort_int, seq_unique_int, seq_count_int,
    seq_reverse_int, seq_take_int, seq_skip_int,
    seq_map_float, seq_filter_float, seq_reduce_sum_float, seq_reduce_max_float,
    seq_reduce_min_float, seq_sort_float, seq_unique_float, seq_count_float,
    seq_reverse_float,
    seq_map_string, seq_filter_string, seq_sort_string, seq_unique_string,
    seq_count_string, seq_reverse_string, seq_take_string, seq_skip_string,
)

def is_nim_seq_available():
    from .bridge.nim._loader import is_nim_available as _is_avail
    return _is_avail()
