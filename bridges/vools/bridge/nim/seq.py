"""
vools.bridge.nim.seq - Nim 序列操作函数桥接
"""

from ._loader import get_nim_lib
from ..core.serialization import csv_serialize, csv_deserialize

_nim_lib = get_nim_lib('vools_seq')


# Python 回退实现
def _py_map_int(data, multiplier):
    return [x * multiplier for x in data]


def _py_filter_int(data, threshold):
    return [x for x in data if x > threshold]


def _py_sum_int(data):
    return sum(data)


def _py_max_int(data):
    return max(data) if data else 0


def _py_min_int(data):
    return min(data) if data else 0


def _py_sort_int(data, desc=False):
    return sorted(data, reverse=desc)


def _py_unique_int(data):
    seen = set()
    result = []
    for x in data:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


def _py_count_int(data, threshold):
    return sum(1 for x in data if x > threshold)


def _py_reverse_int(data):
    return list(reversed(data))


def _py_take_int(data, n):
    return data[:n]


def _py_skip_int(data, n):
    return data[n:]


def _py_map_float(data, multiplier):
    return [x * multiplier for x in data]


def _py_filter_float(data, threshold):
    return [x for x in data if x > threshold]


def _py_sum_float(data):
    return sum(data)


def _py_max_float(data):
    return max(data) if data else 0.0


def _py_min_float(data):
    return min(data) if data else 0.0


def _py_sort_float(data, desc=False):
    return sorted(data, reverse=desc)


def _py_unique_float(data):
    seen = set()
    result = []
    for x in data:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result


def _py_count_float(data, threshold):
    return sum(1 for x in data if x > threshold)


def _py_reverse_float(data):
    return list(reversed(data))


def _py_map_string(data, prefix, suffix):
    return [prefix + x.strip() + suffix for x in data]


def _py_filter_string(data, min_len):
    return [x for x in data if x.strip() and len(x.strip()) >= min_len]


def _py_sort_string(data, desc=False):
    return sorted(data, reverse=desc)


def _py_unique_string(data):
    seen = set()
    result = []
    for x in data:
        s = x.strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _py_count_string(data, min_len):
    return sum(1 for x in data if x.strip() and len(x.strip()) >= min_len)


def _py_reverse_string(data):
    return list(reversed(data))


def _py_take_string(data, n):
    return data[:n]


def _py_skip_string(data, n):
    return data[n:]


# Nim 实现
def _nim_map_int(data, multiplier):
    return csv_deserialize(_nim_lib.seq_map_int(csv_serialize(data), multiplier), 'int')


def _nim_filter_int(data, threshold):
    return csv_deserialize(_nim_lib.seq_filter_int(csv_serialize(data), threshold), 'int')


def _nim_sum_int(data):
    return int(_nim_lib.seq_reduce_sum_int(csv_serialize(data)).decode('utf-8'))


def _nim_max_int(data):
    return int(_nim_lib.seq_reduce_max_int(csv_serialize(data)).decode('utf-8'))


def _nim_min_int(data):
    return int(_nim_lib.seq_reduce_min_int(csv_serialize(data)).decode('utf-8'))


def _nim_sort_int(data, desc=False):
    d = 1 if desc else 0
    return csv_deserialize(_nim_lib.seq_sort_int(csv_serialize(data), d), 'int')


def _nim_unique_int(data):
    return csv_deserialize(_nim_lib.seq_unique_int(csv_serialize(data)), 'int')


def _nim_count_int(data, threshold):
    return int(_nim_lib.seq_count_int(csv_serialize(data), threshold).decode('utf-8'))


def _nim_reverse_int(data):
    return csv_deserialize(_nim_lib.seq_reverse_int(csv_serialize(data)), 'int')


def _nim_take_int(data, n):
    return csv_deserialize(_nim_lib.seq_take_int(csv_serialize(data), n), 'int')


def _nim_skip_int(data, n):
    return csv_deserialize(_nim_lib.seq_skip_int(csv_serialize(data), n), 'int')


def _nim_map_float(data, multiplier):
    return csv_deserialize(_nim_lib.seq_map_float(
        csv_serialize(data), repr(multiplier).encode('utf-8')), 'float')


def _nim_filter_float(data, threshold):
    return csv_deserialize(_nim_lib.seq_filter_float(
        csv_serialize(data), repr(threshold).encode('utf-8')), 'float')


def _nim_sum_float(data):
    return float(_nim_lib.seq_reduce_sum_float(csv_serialize(data)).decode('utf-8'))


def _nim_max_float(data):
    return float(_nim_lib.seq_reduce_max_float(csv_serialize(data)).decode('utf-8'))


def _nim_min_float(data):
    return float(_nim_lib.seq_reduce_min_float(csv_serialize(data)).decode('utf-8'))


def _nim_sort_float(data, desc=False):
    d = 1 if desc else 0
    return csv_deserialize(_nim_lib.seq_sort_float(csv_serialize(data), d), 'float')


def _nim_unique_float(data):
    return csv_deserialize(_nim_lib.seq_unique_float(csv_serialize(data)), 'float')


def _nim_count_float(data, threshold):
    return int(_nim_lib.seq_count_float(
        csv_serialize(data), repr(threshold).encode('utf-8')).decode('utf-8'))


def _nim_reverse_float(data):
    return csv_deserialize(_nim_lib.seq_reverse_float(csv_serialize(data)), 'float')


def _nim_map_string(data, prefix, suffix):
    return csv_deserialize(_nim_lib.seq_map_string(
        csv_serialize(data), prefix.encode('utf-8'), suffix.encode('utf-8')), 'string')


def _nim_filter_string(data, min_len):
    return csv_deserialize(_nim_lib.seq_filter_string(csv_serialize(data), min_len), 'string')


def _nim_sort_string(data, desc=False):
    d = 1 if desc else 0
    return csv_deserialize(_nim_lib.seq_sort_string(csv_serialize(data), d), 'string')


def _nim_unique_string(data):
    return csv_deserialize(_nim_lib.seq_unique_string(csv_serialize(data)), 'string')


def _nim_count_string(data, min_len):
    return int(_nim_lib.seq_count_string(csv_serialize(data), min_len).decode('utf-8'))


def _nim_reverse_string(data):
    return csv_deserialize(_nim_lib.seq_reverse_string(csv_serialize(data)), 'string')


def _nim_take_string(data, n):
    return csv_deserialize(_nim_lib.seq_take_string(csv_serialize(data), n), 'string')


def _nim_skip_string(data, n):
    return csv_deserialize(_nim_lib.seq_skip_string(csv_serialize(data), n), 'string')


# 公开 API
_USE_NIM = _nim_lib is not None

seq_map_int = _nim_map_int if _USE_NIM else _py_map_int
seq_filter_int = _nim_filter_int if _USE_NIM else _py_filter_int
seq_reduce_sum_int = _nim_sum_int if _USE_NIM else _py_sum_int
seq_reduce_max_int = _nim_max_int if _USE_NIM else _py_max_int
seq_reduce_min_int = _nim_min_int if _USE_NIM else _py_min_int
seq_sort_int = _nim_sort_int if _USE_NIM else _py_sort_int
seq_unique_int = _nim_unique_int if _USE_NIM else _py_unique_int
seq_count_int = _nim_count_int if _USE_NIM else _py_count_int
seq_reverse_int = _nim_reverse_int if _USE_NIM else _py_reverse_int
seq_take_int = _nim_take_int if _USE_NIM else _py_take_int
seq_skip_int = _nim_skip_int if _USE_NIM else _py_skip_int

seq_map_float = _nim_map_float if _USE_NIM else _py_map_float
seq_filter_float = _nim_filter_float if _USE_NIM else _py_filter_float
seq_reduce_sum_float = _nim_sum_float if _USE_NIM else _py_sum_float
seq_reduce_max_float = _nim_max_float if _USE_NIM else _py_max_float
seq_reduce_min_float = _nim_min_float if _USE_NIM else _py_min_float
seq_sort_float = _nim_sort_float if _USE_NIM else _py_sort_float
seq_unique_float = _nim_unique_float if _USE_NIM else _py_unique_float
seq_count_float = _nim_count_float if _USE_NIM else _py_count_float
seq_reverse_float = _nim_reverse_float if _USE_NIM else _py_reverse_float

seq_map_string = _nim_map_string if _USE_NIM else _py_map_string
seq_filter_string = _nim_filter_string if _USE_NIM else _py_filter_string
seq_sort_string = _nim_sort_string if _USE_NIM else _py_sort_string
seq_unique_string = _nim_unique_string if _USE_NIM else _py_unique_string
seq_count_string = _nim_count_string if _USE_NIM else _py_count_string
seq_reverse_string = _nim_reverse_string if _USE_NIM else _py_reverse_string
seq_take_string = _nim_take_string if _USE_NIM else _py_take_string
seq_skip_string = _nim_skip_string if _USE_NIM else _py_skip_string
