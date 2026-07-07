"""
vools 性能基准测试框架

提供统一的基准测试工具，用于对比纯 Python 实现 vs 桥接库实现的性能。
"""

from .bridge_benchmark import BridgeBenchmark, BenchmarkResult

__all__ = ['BridgeBenchmark', 'BenchmarkResult']
