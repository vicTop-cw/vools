"""
vools 性能基准测试框架

用法：
    python benchmark/bridge_benchmark.py                    # 运行所有测试
    python benchmark/bridge_benchmark.py --json            # JSON 输出
    python benchmark/bridge_benchmark.py --func pickle_encode  # 只测试指定函数
    python benchmark/bridge_benchmark.py --repeat 1000       # 迭代 1000 次
"""

import time
import tracemalloc
import argparse
import json
import statistics
import sys
import os
from typing import Callable, Any, Dict, List, Optional

# 确保可以导入 vools 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BenchmarkResult:
    """单次基准测试结果"""
    
    def __init__(self, name: str):
        self.name = name
        self.py_time_us: float = 0        # 纯 Python 耗时（微秒）
        self.bridge_time_us: float = 0     # 桥接库耗时（微秒）
        self.py_memory_bytes: int = 0      # 纯 Python 内存峰值
        self.bridge_memory_bytes: int = 0  # 桥接库内存峰值
        self.speedup: float = 0            # 速度提升倍数
        self.memory_reduction: float = 0  # 内存减少百分比
    
    def calc(self):
        """计算速度提升和内存节省"""
        if self.py_time_us > 0:
            self.speedup = self.py_time_us / max(self.bridge_time_us, 0.001)
        if self.py_memory_bytes > 0:
            self.memory_reduction = (
                (self.py_memory_bytes - self.bridge_memory_bytes) / 
                self.py_memory_bytes * 100
            )


class BridgeBenchmark:
    """桥接基准测试运行器"""
    
    def __init__(self, repeat: int = 100, warmup: int = 3):
        self.repeat = repeat
        self.warmup = warmup
        self.results: List[BenchmarkResult] = []
    
    def bench(
        self, 
        name: str, 
        py_func: Callable, 
        bridge_func: Optional[Callable], 
        args: tuple = (), 
        kwargs: dict = None
    ) -> BenchmarkResult:
        """测试单个函数对
        
        Args:
            name: 测试名称
            py_func: 纯 Python 实现函数
            bridge_func: 桥接库实现函数（可为 None）
            args: 传递给函数的参数
            kwargs: 传递给函数的关键字参数
        
        Returns:
            BenchmarkResult 测试结果
        """
        kwargs = kwargs or {}
        result = BenchmarkResult(name)
        
        # 热身
        for _ in range(self.warmup):
            py_func(*args, **kwargs)
            if bridge_func:
                bridge_func(*args, **kwargs)
        
        # 纯 Python 计时
        py_times = []
        tracemalloc.start()
        for _ in range(self.repeat):
            start = time.perf_counter()
            py_func(*args, **kwargs)
            end = time.perf_counter()
            py_times.append((end - start) * 1_000_000)  # 转为微秒
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.py_time_us = statistics.median(py_times)
        result.py_memory_bytes = peak
        
        # 桥接库计时（如果可用）
        if bridge_func:
            bridge_times = []
            tracemalloc.start()
            for _ in range(self.repeat):
                start = time.perf_counter()
                bridge_func(*args, **kwargs)
                end = time.perf_counter()
                bridge_times.append((end - start) * 1_000_000)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            result.bridge_time_us = statistics.median(bridge_times)
            result.bridge_memory_bytes = peak
        
        result.calc()
        self.results.append(result)
        return result
    
    def report(self, verbose: bool = False, json_output: bool = False) -> str:
        """生成报告
        
        Args:
            verbose: 是否输出详细信息
            json_output: 是否输出 JSON 格式
        
        Returns:
            报告字符串
        """
        if json_output:
            return json.dumps([
                {
                    "name": r.name,
                    "speedup": round(r.speedup, 2),
                    "memory_reduction_pct": round(r.memory_reduction, 1),
                    "py_time_us": round(r.py_time_us, 2),
                    "bridge_time_us": round(r.bridge_time_us, 2),
                    "py_memory_bytes": r.py_memory_bytes,
                    "bridge_memory_bytes": r.bridge_memory_bytes,
                }
                for r in self.results
            ], indent=2)
        
        lines = ["=" * 70, "vools 性能基准测试报告", "=" * 70, ""]
        for r in self.results:
            lines.append(f"函数: {r.name}")
            lines.append(
                f"  纯 Python: {r.py_time_us:.2f} us | "
                f"桥接库: {r.bridge_time_us:.2f} us"
            )
            lines.append(f"  速度提升: {r.speedup:.1f}x")
            lines.append(f"  内存节省: {r.memory_reduction:.1f}%")
            if verbose:
                lines.append(
                    f"  内存: 纯 Python {r.py_memory_bytes:,} bytes | "
                    f"桥接库 {r.bridge_memory_bytes:,} bytes"
                )
            lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)
    
    def run_suite(self, suite: List[Dict[str, Any]], func_filter: str = None):
        """运行一个测试套件
        
        Args:
            suite: 测试套件列表
            func_filter: 函数名过滤器（部分匹配）
        """
        for case in suite:
            name = case["name"]
            # 如果指定了过滤器，则跳过不匹配的测试
            if func_filter and func_filter not in name:
                continue
            
            self.bench(
                name=name,
                py_func=case["py_func"],
                bridge_func=case.get("bridge_func"),
                args=case.get("args", ()),
                kwargs=case.get("kwargs"),
            )


# 注册基准测试套件
BENCHMARK_SUITES = {
    "serialize.pickle_encode": {
        "data": {"obj": {"key": "value"}},
        "expected_speedup": 5.0,
    },
    "security.hash.sha256": {
        "data": {"data": b"hello world" * 100},
        "expected_speedup": 3.0,
    },
    "data.seq.base64_encode": {
        "data": {"data": b"hello world" * 100},
        "expected_speedup": 3.0,
    },
}


def main():
    parser = argparse.ArgumentParser(description="vools 性能基准测试")
    parser.add_argument(
        "--func", 
        help="只测试包含此字符串的函数（部分匹配）"
    )
    parser.add_argument(
        "--repeat", 
        type=int, 
        default=100, 
        help="迭代次数（默认 100）"
    )
    parser.add_argument(
        "--json", 
        action="store_true", 
        help="JSON 输出"
    )
    parser.add_argument(
        "--warmup", 
        type=int, 
        default=3, 
        help="热身次数（默认 3）"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="详细输出"
    )
    args = parser.parse_args()
    
    runner = BridgeBenchmark(repeat=args.repeat, warmup=args.warmup)
    
    # 导入测试套件
    # 使用 try/except 同时支持直接运行和作为包导入
    try:
        # 尝试相对导入（作为包导入时）
        from .suites import (
            get_serialize_suite,
            get_hash_suite,
            get_base64_suite,
            get_json_suite,
            get_env_suite,
            get_compress_suite,
            get_sigcache_suite,
        )
    except ImportError:
        # 尝试绝对导入（直接运行脚本时）
        try:
            from suites import (
                get_serialize_suite,
                get_hash_suite,
                get_base64_suite,
                get_json_suite,
                get_env_suite,
                get_compress_suite,
                get_sigcache_suite,
            )
        except ImportError:
            get_serialize_suite = None
            get_hash_suite = None
            get_base64_suite = None
            get_json_suite = None
            get_env_suite = None
            get_compress_suite = None
            get_sigcache_suite = None

    # 运行所有套件
    suites_loaded = False
    if get_serialize_suite:
        suites_list = [
            get_serialize_suite(),
            get_hash_suite(),
            get_base64_suite(),
            get_json_suite(),
            get_env_suite(),
            get_compress_suite(),
        ]
        for suite in suites_list:
            runner.run_suite(suite, func_filter=args.func)
        suites_loaded = True
    
    if not suites_loaded:
        print("Warning: 无法导入测试套件。")
        print("框架仍可运行，但没有实际的基准测试用例。")
        print("")
    
    # 输出报告
    if runner.results:
        print(runner.report(verbose=args.verbose, json_output=args.json))
    else:
        print("没有运行任何基准测试。")


if __name__ == "__main__":
    main()
