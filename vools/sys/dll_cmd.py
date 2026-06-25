"""
vools.sys.dll_cmd - DLL 管理子命令

提供 --list, --dll, --func, --args 选项。
"""

import ctypes
import os
import sys

from ..bridge.core.loader import _LIB_DIR, _IS_WINDOWS


# 已知的 Nim DLL 及其函数映射
_NIM_DLLS = {
    'vools_crypto': ['md5_hash', 'sha1_hash', 'sha256_hash', 'hmac_sha256', 'hmac_md5'],
    'vools_encoding': ['base64_encode', 'base64_decode', 'zlib_compress', 'zlib_decompress'],
    'vools_seq': ['seq_map_int', 'seq_filter_int', 'seq_sort_int', 'seq_take_int', 'seq_skip_int',
                   'seq_reduce_sum_int', 'seq_reduce_max_int', 'seq_reduce_min_int',
                   'seq_unique_int', 'seq_count_int', 'seq_reverse_int'],
    'vools_datetime': ['dt_is_leap_year', 'dt_days_in_month', 'dt_days_in_year',
                        'dt_day_of_week', 'dt_week_of_year', 'dt_days_between',
                        'dt_ymd_to_ts', 'dt_ts_to_ymd', 'dt_ts_to_ymdhms',
                        'dt_range_days', 'dt_range_days_between', 'dt_range_months',
                        'dt_validate_date', 'dt_add_days', 'dt_add_months'],
    'vools_curried': ['cur_sum_int', 'cur_mean_int', 'cur_min_int', 'cur_max_int',
                       'cur_minmax_int', 'cur_stddev_int', 'cur_variance_int',
                       'cur_median_int', 'cur_l2norm_int', 'cur_distinct_int',
                       'cur_dot_int', 'cur_count_int'],
}


def _find_dll_path(name):
    """查找 DLL 路径"""
    if _IS_WINDOWS:
        for ext in ('.dll', '.so', '.pyd'):
            path = os.path.join(_LIB_DIR, name + ext)
            if os.path.exists(path):
                return path
    return None


def _setup_funcs(lib, dll_name):
    """根据 DLL 名称设置函数签名"""
    if dll_name == 'vools_crypto':
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
    elif dll_name == 'vools_encoding':
        lib.base64_encode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.base64_encode.restype = ctypes.c_char_p
        lib.base64_decode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.base64_decode.restype = ctypes.c_char_p
        lib.zlib_compress.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.zlib_compress.restype = ctypes.c_char_p
        lib.zlib_decompress.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.zlib_decompress.restype = ctypes.c_char_p


class DllCommands:
    """DLL 管理命令集"""

    def list(self):
        """列出所有可用的 Nim DLL"""
        print("可用 Nim DLL:")
        print("-" * 50)
        
        available = []
        unavailable = []
        
        for dll_name, funcs in _NIM_DLLS.items():
            dll_path = _find_dll_path(dll_name)
            if dll_path:
                available.append((dll_name, funcs, dll_path))
            else:
                unavailable.append(dll_name)
        
        for dll_name, funcs, dll_path in available:
            print(f"\n✓ {dll_name}")
            print(f"  路径: {dll_path}")
            print(f"  函数: {', '.join(funcs[:5])}...")
        
        if unavailable:
            print(f"\n不可用 DLL ({len(unavailable)}): {', '.join(unavailable)}")
        
        print(f"\n共 {len(available)} 个可用 DLL")

    def dll(self, dll_name: str, func: str, args: str):
        """
        调用 DLL 中的函数
        
        示例: vools sys dll --dll vools_crypto --func md5_hash --args "hello"
        """
        dll_path = _find_dll_path(dll_name)
        if not dll_path:
            print(f"错误: DLL '{dll_name}' 未找到")
            sys.exit(1)
        
        try:
            lib = ctypes.CDLL(dll_path)
            _setup_funcs(lib, dll_name)
            
            fn = getattr(lib, func)
            
            # 根据函数类型调用
            if 'hmac' in func:
                # hmac 函数需要 key 参数
                parts = args.split(',')
                if len(parts) != 2:
                    print("错误: hmac 函数需要 data,key 格式的参数")
                    sys.exit(1)
                data, key = parts[0].encode(), parts[1].encode()
                result = fn(data, len(data), key, len(key))
            else:
                # 普通函数
                data = args.encode()
                result = fn(data, len(data))
            
            print(result.decode() if result else "")
            
        except AttributeError as e:
            print(f"错误: 函数 '{func}' 在 DLL '{dll_name}' 中未找到")
            print(f"可用函数: {', '.join(_NIM_DLLS.get(dll_name, []))}")
            sys.exit(1)
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)

    def func(self, dll_name: str, func: str):
        """
        列出 DLL 中的函数
        
        示例: vools sys dll --func vools_crypto
        """
        if dll_name in _NIM_DLLS:
            print(f"{dll_name} 中的函数:")
            for f in _NIM_DLLS[dll_name]:
                print(f"  - {f}")
        else:
            print(f"错误: 未知 DLL '{dll_name}'")
            print(f"可用 DLL: {', '.join(_NIM_DLLS.keys())}")
            sys.exit(1)
