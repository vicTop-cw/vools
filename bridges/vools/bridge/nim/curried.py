"""
vools.bridge.nim.curried - Nim 函数式函数桥接
"""

from ._loader import get_nim_lib
from ..core.serialization import csv_serialize, csv_deserialize

_nim_lib = get_nim_lib('vools_curried')


# Python 回退实现
def _py_sum_int(data):
    return sum(data)


def _py_mean_int(data):
    return sum(data) / len(data) if data else 0


def _py_min_int(data):
    return min(data) if data else 0


def _py_max_int(data):
    return max(data) if data else 0


def _py_minmax_int(data):
    if not data:
        return '0,0'
    return f"{min(data)},{max(data)}"


def _py_stddev_int(data):
    if len(data) < 2:
        return 0.0
    mean = sum(data) / len(data)
    variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
    return variance ** 0.5


def _py_variance_int(data):
    if len(data) < 2:
        return 0.0
    mean = sum(data) / len(data)
    return sum((x - mean) ** 2 for x in data) / (len(data) - 1)


def _py_median_int(data):
    if not data:
        return 0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n % 2 == 1:
        return sorted_data[n // 2]
    return (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2


def _py_l2norm_int(data):
    return sum(x ** 2 for x in data) ** 0.5


def _py_distinct_int(data):
    seen = set()
    return [x for x in data if x not in seen and not seen.add(x)]


def _py_dot_int(data1, data2):
    return sum(a * b for a, b in zip(data1, data2))


def _py_count_int(data, threshold):
    return sum(1 for x in data if x > threshold)


def _py_sum_float(data):
    return sum(data)


def _py_mean_float(data):
    return sum(data) / len(data) if data else 0.0


def _py_min_float(data):
    return min(data) if data else 0.0


def _py_max_float(data):
    return max(data) if data else 0.0


def _py_minmax_float(data):
    if not data:
        return '0.0,0.0'
    return f"{min(data)},{max(data)}"


def _py_stddev_float(data):
    if len(data) < 2:
        return 0.0
    mean = sum(data) / len(data)
    variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
    return variance ** 0.5


def _py_variance_float(data):
    if len(data) < 2:
        return 0.0
    mean = sum(data) / len(data)
    return sum((x - mean) ** 2 for x in data) / (len(data) - 1)


def _py_median_float(data):
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n % 2 == 1:
        return sorted_data[n // 2]
    return (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2


def _py_l2norm_float(data):
    return sum(x ** 2 for x in data) ** 0.5


def _py_dot_float(data1, data2):
    return sum(a * b for a, b in zip(data1, data2))


def _py_distinct_string(data):
    seen = set()
    return [x for x in data if x not in seen and not seen.add(x)]


def _py_union_string(data1, data2):
    return list(set(data1) | set(data2))


def _py_intersect_string(data1, data2):
    return list(set(data1) & set(data2))


def _py_diff_string(data1, data2):
    return list(set(data1) - set(data2))


def _py_count_string(data, target):
    return sum(1 for x in data if x == target)


# Nim 实现
def _nim_sum_int(data):
    return int(_nim_lib.cur_sum_int(csv_serialize(data)).decode('utf-8'))


def _nim_mean_int(data):
    return float(_nim_lib.cur_mean_int(csv_serialize(data)).decode('utf-8'))


def _nim_min_int(data):
    return int(_nim_lib.cur_min_int(csv_serialize(data)).decode('utf-8'))


def _nim_max_int(data):
    return int(_nim_lib.cur_max_int(csv_serialize(data)).decode('utf-8'))


def _nim_minmax_int(data):
    return _nim_lib.cur_minmax_int(csv_serialize(data)).decode('utf-8')


def _nim_stddev_int(data):
    return float(_nim_lib.cur_stddev_int(csv_serialize(data)).decode('utf-8'))


def _nim_variance_int(data):
    return float(_nim_lib.cur_variance_int(csv_serialize(data)).decode('utf-8'))


def _nim_median_int(data):
    return float(_nim_lib.cur_median_int(csv_serialize(data)).decode('utf-8'))


def _nim_l2norm_int(data):
    return float(_nim_lib.cur_l2norm_int(csv_serialize(data)).decode('utf-8'))


def _nim_distinct_int(data):
    return csv_deserialize(_nim_lib.cur_distinct_int(csv_serialize(data)), 'int')


def _nim_dot_int(data1, data2):
    return float(_nim_lib.cur_dot_int(csv_serialize(data1), csv_serialize(data2)).decode('utf-8'))


def _nim_count_int(data, threshold):
    return int(_nim_lib.cur_count_int(csv_serialize(data), threshold).decode('utf-8'))


def _nim_sum_float(data):
    return float(_nim_lib.cur_sum_float(csv_serialize(data)).decode('utf-8'))


def _nim_mean_float(data):
    return float(_nim_lib.cur_mean_float(csv_serialize(data)).decode('utf-8'))


def _nim_min_float(data):
    return float(_nim_lib.cur_min_float(csv_serialize(data)).decode('utf-8'))


def _nim_max_float(data):
    return float(_nim_lib.cur_max_float(csv_serialize(data)).decode('utf-8'))


def _nim_minmax_float(data):
    return _nim_lib.cur_minmax_float(csv_serialize(data)).decode('utf-8')


def _nim_stddev_float(data):
    return float(_nim_lib.cur_stddev_float(csv_serialize(data)).decode('utf-8'))


def _nim_variance_float(data):
    return float(_nim_lib.cur_variance_float(csv_serialize(data)).decode('utf-8'))


def _nim_median_float(data):
    return float(_nim_lib.cur_median_float(csv_serialize(data)).decode('utf-8'))


def _nim_l2norm_float(data):
    return float(_nim_lib.cur_l2norm_float(csv_serialize(data)).decode('utf-8'))


def _nim_dot_float(data1, data2):
    return float(_nim_lib.cur_dot_float(csv_serialize(data1), csv_serialize(data2)).decode('utf-8'))


def _nim_distinct_string(data):
    return csv_deserialize(_nim_lib.cur_distinct_string(csv_serialize(data)), 'string')


def _nim_union_string(data1, data2):
    return csv_deserialize(_nim_lib.cur_union_string(csv_serialize(data1), csv_serialize(data2)), 'string')


def _nim_intersect_string(data1, data2):
    return csv_deserialize(_nim_lib.cur_intersect_string(csv_serialize(data1), csv_serialize(data2)), 'string')


def _nim_diff_string(data1, data2):
    return csv_deserialize(_nim_lib.cur_diff_string(csv_serialize(data1), csv_serialize(data2)), 'string')


def _nim_count_string(data, target):
    return int(_nim_lib.cur_count_string(csv_serialize(data), target.encode('utf-8')).decode('utf-8'))


# 公开 API
_USE_NIM = _nim_lib is not None

cur_sum_int = _nim_sum_int if _USE_NIM else _py_sum_int
cur_mean_int = _nim_mean_int if _USE_NIM else _py_mean_int
cur_min_int = _nim_min_int if _USE_NIM else _py_min_int
cur_max_int = _nim_max_int if _USE_NIM else _py_max_int
cur_minmax_int = _nim_minmax_int if _USE_NIM else _py_minmax_int
cur_stddev_int = _nim_stddev_int if _USE_NIM else _py_stddev_int
cur_variance_int = _nim_variance_int if _USE_NIM else _py_variance_int
cur_median_int = _nim_median_int if _USE_NIM else _py_median_int
cur_l2norm_int = _nim_l2norm_int if _USE_NIM else _py_l2norm_int
cur_distinct_int = _nim_distinct_int if _USE_NIM else _py_distinct_int
cur_dot_int = _nim_dot_int if _USE_NIM else _py_dot_int
cur_count_int = _nim_count_int if _USE_NIM else _py_count_int

cur_sum_float = _nim_sum_float if _USE_NIM else _py_sum_float
cur_mean_float = _nim_mean_float if _USE_NIM else _py_mean_float
cur_min_float = _nim_min_float if _USE_NIM else _py_min_float
cur_max_float = _nim_max_float if _USE_NIM else _py_max_float
cur_minmax_float = _nim_minmax_float if _USE_NIM else _py_minmax_float
cur_stddev_float = _nim_stddev_float if _USE_NIM else _py_stddev_float
cur_variance_float = _nim_variance_float if _USE_NIM else _py_variance_float
cur_median_float = _nim_median_float if _USE_NIM else _py_median_float
cur_l2norm_float = _nim_l2norm_float if _USE_NIM else _py_l2norm_float
cur_dot_float = _nim_dot_float if _USE_NIM else _py_dot_float

cur_distinct_string = _nim_distinct_string if _USE_NIM else _py_distinct_string
cur_union_string = _nim_union_string if _USE_NIM else _py_union_string
cur_intersect_string = _nim_intersect_string if _USE_NIM else _py_intersect_string
cur_diff_string = _nim_diff_string if _USE_NIM else _py_diff_string
cur_count_string = _nim_count_string if _USE_NIM else _py_count_string
