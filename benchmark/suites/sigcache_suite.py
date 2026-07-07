"""
benchmark.suites.sigcache_suite - 签名哈希基准测试套件

测试签名哈希函数的性能：
- 不同长度签名字符串的哈希
- 从 inspect.Signature 计算哈希
- 纯 Python vs Nim 桥接实现对比
"""

import inspect
import time
from typing import Callable, Dict, Any

__all__ = ['SigcacheSuite', 'run_sigcache_benchmarks']

# 测试用的签名字符串
_SMALL_SIG = "add(a: int, b: int) -> int"
_MEDIUM_SIG = "process_data(items: list, callback: callable, options: dict = None) -> dict"
_LARGE_SIG = "complex_function(arg1: str, arg2: int, arg3: float = 0.0, arg4: bool = False, *args, **kwargs) -> tuple"


# 尝试导入 Nim 桥接库
_nim_hash_signature = None
_nim_available = False

try:
    from vools.bridge.nim import hash_signature as _nim_hash_sig, is_sigcache_available
    _nim_available = is_sigcache_available()
    if _nim_available:
        _nim_hash_signature = _nim_hash_sig
except ImportError:
    pass


def _python_hash_signature(data: str) -> str:
    """纯 Python FNV-1a 哈希实现"""
    FNV_OFFSET = 0xcbf29ce484222325
    FNV_PRIME = 0x100000001b3

    hash_value = FNV_OFFSET
    for byte in data.encode('utf-8'):
        hash_value ^= byte
        hash_value = (hash_value * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF

    return format(hash_value, '016x')


def _python_build_signature_str(func_name: str, params: str, ret_type: str) -> str:
    """纯 Python 构建签名字符串"""
    return f"{func_name}({params}) -> {ret_type}"


class SigcacheSuite:
    """签名哈希基准测试套件"""

    name = "sigcache"

    @staticmethod
    def get_tests() -> Dict[str, Callable]:
        """获取所有签名哈希测试"""
        tests = {}

        # 直接哈希测试
        if _nim_hash_signature:
            tests['hash_small'] = (_nim_hash_signature, _SMALL_SIG)
            tests['hash_medium'] = (_nim_hash_signature, _MEDIUM_SIG)
            tests['hash_large'] = (_nim_hash_signature, _LARGE_SIG)
        else:
            tests['hash_small'] = (_python_hash_signature, _SMALL_SIG)
            tests['hash_medium'] = (_python_hash_signature, _MEDIUM_SIG)
            tests['hash_large'] = (_python_hash_signature, _LARGE_SIG)

        return tests

    @staticmethod
    def get_pure_python_tests() -> Dict[str, Callable]:
        """获取纯 Python 签名哈希测试（用于对比）"""
        return {
            'hash_small': (_python_hash_signature, _SMALL_SIG),
            'hash_medium': (_python_hash_signature, _MEDIUM_SIG),
            'hash_large': (_python_hash_signature, _LARGE_SIG),
        }


def run_sigcache_benchmarks(func: Callable, data: str, repeat: int = 1000) -> Dict[str, float]:
    """
    运行签名哈希基准测试

    Args:
        func: 哈希函数
        data: 签名字符串
        repeat: 重复次数

    Returns:
        包含平均耗时和方差的字典
    """
    times = []
    result = None
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
        'result': result,
    }


def benchmark_signature_from_func(repeat: int = 1000) -> Dict[str, float]:
    """测试从 inspect.Signature 计算哈希的性能"""

    def simple_func(a: int, b: int) -> int:
        return a + b

    def complex_func(a: int, b: str, c: float = 0.0, *args, **kwargs) -> dict:
        return {"a": a, "b": b}

    sigs = [simple_func, complex_func]

    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        for func in sigs:
            sig = inspect.signature(func)
            sig_str = f"{func.__name__}("
            params = []
            for pname, p in sig.parameters.items():
                pstr = pname
                if p.annotation != inspect.Parameter.empty:
                    pstr += f": {p.annotation}"
                if p.default != inspect.Parameter.empty:
                    pstr += f" = {p.default}"
                params.append(pstr)
            sig_str += ", ".join(params)
            sig_str += f") -> {sig.return_annotation}"
            if _nim_hash_signature:
                _nim_hash_signature(sig_str)
            else:
                _python_hash_signature(sig_str)
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
    }


def main():
    """主函数：运行所有基准测试"""
    suite = SigcacheSuite()
    tests = suite.get_tests()
    py_tests = suite.get_pure_python_tests()

    print(f"Nim library available: {_nim_available}")
    print(f"Nim hash_signature: {_nim_hash_signature}")
    print()

    results = {}

    # 运行 Nim 加速版本（如果有）
    if _nim_hash_signature:
        print("Running Nim-accelerated sigcache benchmarks...")
        for name, (func, data) in tests.items():
            r = run_sigcache_benchmarks(func, data, repeat=1000)
            results[f"nim_{name}"] = r
            print(f"  {name}: {r['avg']*1000:.4f}ms ± {r['stddev']*1000:.4f}ms (result={r['result']})")

    # 运行纯 Python 版本
    print("\nRunning pure Python sigcache benchmarks...")
    for name, (func, data) in py_tests.items():
        r = run_sigcache_benchmarks(func, data, repeat=1000)
        results[f"py_{name}"] = r
        print(f"  {name}: {r['avg']*1000:.4f}ms ± {r['stddev']*1000:.4f}ms")

    # 计算加速比
    if _nim_hash_signature:
        print("\nSpeedup ratios (Nim vs Python):")
        for name in ['hash_small', 'hash_medium', 'hash_large']:
            nim_key = f"nim_{name}"
            py_key = f"py_{name}"
            if nim_key in results and py_key in results:
                speedup = results[py_key]['avg'] / results[nim_key]['avg']
                print(f"  {name}: {speedup:.2f}x")

    # 测试 inspect.Signature 集成的性能
    print("\nRunning inspect.Signature integration benchmarks...")
    r = benchmark_signature_from_func(repeat=1000)
    print(f"  2 funcs x 1000 iterations: {r['avg']*1000:.4f}ms ± {r['stddev']*1000:.4f}ms")

    return results


def get_sigcache_suite():
    """获取 sigcache 基准测试套件"""
    suite = SigcacheSuite()
    return suite


if __name__ == '__main__':
    main()
