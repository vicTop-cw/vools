"""
vools/_nim_curried.py
Nim 加速的数学/统计/集合操作 - 自动回退到 Python
"""
from ._nim_loader import load_nim_lib
import ctypes

_nim_lib = load_nim_lib('vools_curried')


def _setup_funcs():
    if _nim_lib is None:
        return
    int_funcs = ['cur_sum_int', 'cur_mean_int', 'cur_min_int', 'cur_max_int',
                 'cur_minmax_int', 'cur_stddev_int', 'cur_variance_int',
                 'cur_median_int', 'cur_l2norm_int', 'cur_distinct_int', 'cur_count_int']
    for name in int_funcs:
        fn = getattr(_nim_lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    _nim_lib.cur_dot_int.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _nim_lib.cur_dot_int.restype = ctypes.c_char_p
    _nim_lib.cur_count_int.argtypes = [ctypes.c_char_p, ctypes.c_int]
    _nim_lib.cur_count_int.restype = ctypes.c_char_p

    float_funcs = ['cur_sum_float', 'cur_mean_float', 'cur_min_float', 'cur_max_float',
                   'cur_minmax_float', 'cur_stddev_float', 'cur_variance_float',
                   'cur_median_float', 'cur_l2norm_float']
    for name in float_funcs:
        fn = getattr(_nim_lib, name)
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    _nim_lib.cur_dot_float.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _nim_lib.cur_dot_float.restype = ctypes.c_char_p

    for name in ('cur_distinct_string', 'cur_union_string', 'cur_intersect_string',
                 'cur_diff_string'):
        fn = getattr(_nim_lib, name)
        fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        fn.restype = ctypes.c_char_p
    _nim_lib.cur_distinct_string.argtypes = [ctypes.c_char_p]
    _nim_lib.cur_distinct_string.restype = ctypes.c_char_p
    _nim_lib.cur_count_string.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _nim_lib.cur_count_string.restype = ctypes.c_char_p


_setup_funcs()
_USE_NIM = _nim_lib is not None


# ============================================================
# Python 回退
# ============================================================
import math as _math
from collections import Counter

def _py_sum(arr):
    return sum(arr)

def _py_mean(arr):
    return sum(arr) / len(arr) if arr else 0.0

def _py_min(arr):
    return min(arr) if arr else 0

def _py_max(arr):
    return max(arr) if arr else 0

def _py_minmax(arr):
    if not arr:
        return (0, 0)
    return (min(arr), max(arr))

def _py_stddev(arr):
    if not arr:
        return 0.0
    m = sum(arr) / len(arr)
    return _math.sqrt(sum((x - m) ** 2 for x in arr) / len(arr))

def _py_variance(arr):
    if not arr:
        return 0.0
    m = sum(arr) / len(arr)
    return sum((x - m) ** 2 for x in arr) / len(arr)

def _py_median(arr):
    if not arr:
        return 0.0
    s = sorted(arr)
    n = len(s)
    if n % 2:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0

def _py_dot(a, b):
    return sum(x * y for x, y in zip(a, b))

def _py_l2norm(arr):
    return _math.sqrt(sum(x * x for x in arr))

def _py_distinct(arr):
    seen = set()
    result = []
    for x in arr:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result

def _py_count(arr, v):
    return sum(1 for x in arr if x == v)

def _py_union(a, b):
    return _py_distinct(list(a) + list(b))

def _py_intersect(a, b):
    sb = set(b)
    return [x for x in a if x in sb and x in sb]

def _py_diff(a, b):
    sb = set(b)
    return [x for x in a if x not in sb]


# ============================================================
# Nim 包装
# ============================================================

def _ints_to_csv(data):
    return ','.join(str(x) for x in data).encode('utf-8')

def _floats_to_csv(data):
    return ','.join(repr(x) for x in data).encode('utf-8')

def _csv_to_ints(s):
    if not s:
        return []
    return [int(x) for x in s.decode('utf-8').split(',') if x.strip()]

def _csv_to_floats(s):
    if not s:
        return []
    return [float(x) for x in s.decode('utf-8').split(',') if x.strip()]

def _csv_to_strings(s):
    if not s:
        return []
    return [x.strip() for x in s.decode('utf-8').split(',') if x.strip()]


def _nim_sum_int(data):
    return int(_nim_lib.cur_sum_int(_ints_to_csv(data)).decode())

def _nim_mean_int(data):
    return float(_nim_lib.cur_mean_int(_ints_to_csv(data)).decode())

def _nim_min_int(data):
    return int(_nim_lib.cur_min_int(_ints_to_csv(data)).decode())

def _nim_max_int(data):
    return int(_nim_lib.cur_max_int(_ints_to_csv(data)).decode())

def _nim_minmax_int(data):
    s = _nim_lib.cur_minmax_int(_ints_to_csv(data)).decode()
    mn, mx = s.split(',')
    return (int(mn), int(mx))

def _nim_stddev_int(data):
    return float(_nim_lib.cur_stddev_int(_ints_to_csv(data)).decode())

def _nim_variance_int(data):
    return float(_nim_lib.cur_variance_int(_ints_to_csv(data)).decode())

def _nim_median_int(data):
    return float(_nim_lib.cur_median_int(_ints_to_csv(data)).decode())

def _nim_dot_int(a, b):
    return int(_nim_lib.cur_dot_int(_ints_to_csv(a), _ints_to_csv(b)).decode())

def _nim_l2norm_int(data):
    return float(_nim_lib.cur_l2norm_int(_ints_to_csv(data)).decode())

def _nim_distinct_int(data):
    return _csv_to_ints(_nim_lib.cur_distinct_int(_ints_to_csv(data)))

def _nim_count_int(data, v):
    return int(_nim_lib.cur_count_int(_ints_to_csv(data), v).decode())


def _nim_sum_float(data):
    return float(_nim_lib.cur_sum_float(_floats_to_csv(data)).decode())

def _nim_mean_float(data):
    return float(_nim_lib.cur_mean_float(_floats_to_csv(data)).decode())

def _nim_min_float(data):
    return float(_nim_lib.cur_min_float(_floats_to_csv(data)).decode())

def _nim_max_float(data):
    return float(_nim_lib.cur_max_float(_floats_to_csv(data)).decode())

def _nim_minmax_float(data):
    s = _nim_lib.cur_minmax_float(_floats_to_csv(data)).decode()
    mn, mx = s.split(',')
    return (float(mn), float(mx))

def _nim_stddev_float(data):
    return float(_nim_lib.cur_stddev_float(_floats_to_csv(data)).decode())

def _nim_variance_float(data):
    return float(_nim_lib.cur_variance_float(_floats_to_csv(data)).decode())

def _nim_median_float(data):
    return float(_nim_lib.cur_median_float(_floats_to_csv(data)).decode())

def _nim_dot_float(a, b):
    return float(_nim_lib.cur_dot_float(_floats_to_csv(a), _floats_to_csv(b)).decode())

def _nim_l2norm_float(data):
    return float(_nim_lib.cur_l2norm_float(_floats_to_csv(data)).decode())


def _nim_distinct_string(data):
    return _csv_to_strings(_nim_lib.cur_distinct_string(','.join(data).encode('utf-8')))

def _nim_union_string(a, b):
    return _csv_to_strings(_nim_lib.cur_union_string(
        ','.join(a).encode('utf-8'), ','.join(b).encode('utf-8')))

def _nim_intersect_string(a, b):
    return _csv_to_strings(_nim_lib.cur_intersect_string(
        ','.join(a).encode('utf-8'), ','.join(b).encode('utf-8')))

def _nim_diff_string(a, b):
    return _csv_to_strings(_nim_lib.cur_diff_string(
        ','.join(a).encode('utf-8'), ','.join(b).encode('utf-8')))

def _nim_count_string(data, target):
    return int(_nim_lib.cur_count_string(
        ','.join(data).encode('utf-8'), target.encode('utf-8')).decode())


# ============================================================
# 公开 API
# ============================================================

sum_int = _nim_sum_int if _USE_NIM else _py_sum
mean_int = _nim_mean_int if _USE_NIM else _py_mean
min_int = _nim_min_int if _USE_NIM else _py_min
max_int = _nim_max_int if _USE_NIM else _py_max
minmax_int = _nim_minmax_int if _USE_NIM else _py_minmax
stddev_int = _nim_stddev_int if _USE_NIM else _py_stddev
variance_int = _nim_variance_int if _USE_NIM else _py_variance
median_int = _nim_median_int if _USE_NIM else _py_median
dot_int = _nim_dot_int if _USE_NIM else _py_dot
l2norm_int = _nim_l2norm_int if _USE_NIM else _py_l2norm
distinct_int = _nim_distinct_int if _USE_NIM else _py_distinct
count_int = _nim_count_int if _USE_NIM else _py_count

sum_float = _nim_sum_float if _USE_NIM else _py_sum
mean_float = _nim_mean_float if _USE_NIM else _py_mean
min_float = _nim_min_float if _USE_NIM else _py_min
max_float = _nim_max_float if _USE_NIM else _py_max
minmax_float = _nim_minmax_float if _USE_NIM else _py_minmax
stddev_float = _nim_stddev_float if _USE_NIM else _py_stddev
variance_float = _nim_variance_float if _USE_NIM else _py_variance
median_float = _nim_median_float if _USE_NIM else _py_median
dot_float = _nim_dot_float if _USE_NIM else _py_dot
l2norm_float = _nim_l2norm_float if _USE_NIM else _py_l2norm

distinct_string = _nim_distinct_string if _USE_NIM else _py_distinct
union_string = _nim_union_string if _USE_NIM else _py_union
intersect_string = _nim_intersect_string if _USE_NIM else _py_intersect
diff_string = _nim_diff_string if _USE_NIM else _py_diff
count_string = _nim_count_string if _USE_NIM else _py_count


def is_nim_curried_available():
    return _USE_NIM
