"""
benchmark.suites.hash_suite - 哈希函数基准测试套件

测试各种数据大小下的哈希函数性能：
- 小数据 (16 字节)
- 中数据 (1KB)
- 大数据 (1MB)
"""

import time
import hashlib
from typing import Callable, Dict, Any

__all__ = ['HashSuite', 'run_hash_benchmarks', 'get_hash_suite']


# 测试数据
_SMALL_DATA = b"hello world" * 2  # 22 bytes
_MEDIUM_DATA = b"x" * 1024  # 1KB
_LARGE_DATA = b"y" * (1024 * 1024)  # 1MB


class HashSuite:
    """哈希函数基准测试套件"""

    name = "hash"

    @staticmethod
    def get_tests() -> Dict[str, Callable]:
        """获取所有哈希测试"""
        from vools.security.hash import (
            sha256_hex, md5_hex, sha1_hex,
            sha224_hex, sha384_hex, sha512_hex,
        )
        return {
            'sha256_small': (sha256_hex, _SMALL_DATA),
            'sha256_medium': (sha256_hex, _MEDIUM_DATA),
            'sha256_large': (sha256_hex, _LARGE_DATA),
            'md5_small': (md5_hex, _SMALL_DATA),
            'md5_medium': (md5_hex, _MEDIUM_DATA),
            'md5_large': (md5_hex, _LARGE_DATA),
            'sha1_small': (sha1_hex, _SMALL_DATA),
            'sha1_medium': (sha1_hex, _MEDIUM_DATA),
            'sha1_large': (sha1_hex, _LARGE_DATA),
            'sha224_small': (sha224_hex, _SMALL_DATA),
            'sha224_medium': (sha224_hex, _MEDIUM_DATA),
            'sha224_large': (sha224_hex, _LARGE_DATA),
            'sha384_small': (sha384_hex, _SMALL_DATA),
            'sha384_medium': (sha384_hex, _MEDIUM_DATA),
            'sha384_large': (sha384_hex, _LARGE_DATA),
            'sha512_small': (sha512_hex, _SMALL_DATA),
            'sha512_medium': (sha512_hex, _MEDIUM_DATA),
            'sha512_large': (sha512_hex, _LARGE_DATA),
        }

    @staticmethod
    def get_pure_python_tests() -> Dict[str, Callable]:
        """获取纯 Python 哈希测试（用于对比）"""
        def py_sha256(data): return hashlib.sha256(data).hexdigest()
        def py_md5(data): return hashlib.md5(data).hexdigest()
        def py_sha1(data): return hashlib.sha1(data).hexdigest()
        def py_sha224(data): return hashlib.sha224(data).hexdigest()
        def py_sha384(data): return hashlib.sha384(data).hexdigest()
        def py_sha512(data): return hashlib.sha512(data).hexdigest()

        return {
            'sha256_small': (py_sha256, _SMALL_DATA),
            'sha256_medium': (py_sha256, _MEDIUM_DATA),
            'sha256_large': (py_sha256, _LARGE_DATA),
            'md5_small': (py_md5, _SMALL_DATA),
            'md5_medium': (py_md5, _MEDIUM_DATA),
            'md5_large': (py_md5, _LARGE_DATA),
            'sha1_small': (py_sha1, _SMALL_DATA),
            'sha1_medium': (py_sha1, _MEDIUM_DATA),
            'sha1_large': (py_sha1, _LARGE_DATA),
            'sha224_small': (py_sha224, _SMALL_DATA),
            'sha224_medium': (py_sha224, _MEDIUM_DATA),
            'sha224_large': (py_sha224, _LARGE_DATA),
            'sha384_small': (py_sha384, _SMALL_DATA),
            'sha384_medium': (py_sha384, _MEDIUM_DATA),
            'sha384_large': (py_sha384, _LARGE_DATA),
            'sha512_small': (py_sha512, _SMALL_DATA),
            'sha512_medium': (py_sha512, _MEDIUM_DATA),
            'sha512_large': (py_sha512, _LARGE_DATA),
        }


def run_hash_benchmarks(func: Callable, data: bytes, repeat: int = 100) -> Dict[str, float]:
    """
    运行哈希基准测试

    Args:
        func: 哈希函数
        data: 测试数据
        repeat: 重复次数

    Returns:
        包含平均耗时和方差的字典
    """
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        result = func(data)
        end = time.perf_counter()
        times.append(end - start)

    avg_time = sum(times) / len(times)
    variance = sum((t - avg_time) ** 2 for t in times) / len(times)
    stddev = variance ** 0.5

    return {
        'avg': avg_time,
        'stddev': stddev,
        'min': min(times),
        'max': max(times),
        'result_len': len(result),
    }


def get_hash_suite():
    """
    获取哈希函数基准测试套件
    
    Returns:
        测试用例列表，每项包含:
        - name: 测试名称
        - py_func: 纯 Python 实现
        - bridge_func: 桥接库实现
        - args: 传递给函数的参数
        - expected_speedup: 期望的速度提升倍数
    """
    from vools.security.hash import sha256_hex, md5_hex, sha1_hex
    
    # 纯 Python 哈希函数
    def py_sha256(data): return hashlib.sha256(data).hexdigest()
    def py_md5(data): return hashlib.md5(data).hexdigest()
    def py_sha1(data): return hashlib.sha1(data).hexdigest()
    
    return [
        # sha256 tests
        {
            "name": "security.hash.sha256_small",
            "py_func": py_sha256,
            "bridge_func": sha256_hex,
            "args": (_SMALL_DATA,),
            "expected_speedup": 3.0,
        },
        {
            "name": "security.hash.sha256_medium",
            "py_func": py_sha256,
            "bridge_func": sha256_hex,
            "args": (_MEDIUM_DATA,),
            "expected_speedup": 3.0,
        },
        {
            "name": "security.hash.sha256_large",
            "py_func": py_sha256,
            "bridge_func": sha256_hex,
            "args": (_LARGE_DATA,),
            "expected_speedup": 3.0,
        },
        # md5 tests
        {
            "name": "security.hash.md5_small",
            "py_func": py_md5,
            "bridge_func": md5_hex,
            "args": (_SMALL_DATA,),
            "expected_speedup": 3.0,
        },
        {
            "name": "security.hash.md5_medium",
            "py_func": py_md5,
            "bridge_func": md5_hex,
            "args": (_MEDIUM_DATA,),
            "expected_speedup": 3.0,
        },
        {
            "name": "security.hash.md5_large",
            "py_func": py_md5,
            "bridge_func": md5_hex,
            "args": (_LARGE_DATA,),
            "expected_speedup": 3.0,
        },
        # sha1 tests
        {
            "name": "security.hash.sha1_small",
            "py_func": py_sha1,
            "bridge_func": sha1_hex,
            "args": (_SMALL_DATA,),
            "expected_speedup": 3.0,
        },
        {
            "name": "security.hash.sha1_medium",
            "py_func": py_sha1,
            "bridge_func": sha1_hex,
            "args": (_MEDIUM_DATA,),
            "expected_speedup": 3.0,
        },
        {
            "name": "security.hash.sha1_large",
            "py_func": py_sha1,
            "bridge_func": sha1_hex,
            "args": (_LARGE_DATA,),
            "expected_speedup": 3.0,
        },
    ]


def main():
    """主函数：运行所有基准测试"""
    import json

    suite = HashSuite()
    tests = suite.get_tests()
    py_tests = suite.get_pure_python_tests()

    results = {}

    # 运行 Nim 加速版本
    print("Running Nim-accelerated hash benchmarks...")
    for name, (func, data) in tests.items():
        size = "small" if "small" in name else "medium" if "medium" in name else "large"
        alg = name.split("_")[0]
        r = run_hash_benchmarks(func, data, repeat=100)
        results[f"nim_{alg}_{size}"] = r
        print(f"  {name}: {r['avg']*1000:.4f}ms ± {r['stddev']*1000:.4f}ms")

    # 运行纯 Python 版本
    print("\nRunning pure Python hash benchmarks...")
    for name, (func, data) in py_tests.items():
        size = "small" if "small" in name else "medium" if "medium" in name else "large"
        alg = name.split("_")[0]
        r = run_hash_benchmarks(func, data, repeat=100)
        results[f"py_{alg}_{size}"] = r
        print(f"  {name}: {r['avg']*1000:.4f}ms ± {r['stddev']*1000:.4f}ms")

    # 计算加速比
    print("\nSpeedup ratios (Nim vs Python):")
    for alg in ['sha256', 'md5', 'sha1', 'sha224', 'sha384', 'sha512']:
        for size in ['small', 'medium', 'large']:
            nim_key = f"nim_{alg}_{size}"
            py_key = f"py_{alg}_{size}"
            if nim_key in results and py_key in results:
                speedup = results[py_key]['avg'] / results[nim_key]['avg']
                print(f"  {alg}_{size}: {speedup:.2f}x")

    return results


if __name__ == '__main__':
    main()
