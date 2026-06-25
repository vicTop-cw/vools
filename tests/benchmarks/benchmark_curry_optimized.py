"""
curry 装饰器优化版本高压测试
对比原始版本和优化版本的性能差异
"""
import sys
import os
import time
import tracemalloc
import gc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.decorators.curry_core import curry as curry_original
from vools.decorators.curry_decorator import curry_class as curry_class_original
from vools.decorators.curry_delay import delay_curry as delay_curry_original

from vools.decorators.curry_core_optimized import curry as curry_optimized
from vools.decorators.curry_decorator_optimized import curry_class as curry_class_optimized
from vools.decorators.curry_delay_optimized import delay_curry as delay_curry_optimized


def benchmark(name, func, iterations=10000):
    gc.collect()
    tracemalloc.start()
    
    start = time.perf_counter()
    for _ in range(iterations):
        func()
    elapsed = time.perf_counter() - start
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    ops_per_sec = iterations / elapsed
    memory_kb = peak / 1024
    
    print(f"{name:60s} | {elapsed:.4f}s | {ops_per_sec:10.0f} ops/s | {memory_kb:10.1f} KB")
    return elapsed, ops_per_sec, memory_kb


def test_functional_correctness():
    """测试功能正确性"""
    print("=== 功能正确性测试 ===\n")
    
    @curry_optimized
    def add3(a, b, c):
        return a + b + c
    
    @curry_optimized
    def mul2(a, b):
        return a * b
    
    assert add3(1)(2)(3) == 6, "curry_optimized: 完整调用失败"
    assert add3(1, 2)(3) == 6, "curry_optimized: 部分调用失败"
    assert add3(1, 2, 3) == 6, "curry_optimized: 直接调用失败"
    assert mul2(2)(3) == 6, "curry_optimized: mul2失败"
    print("[OK] curry_core_optimized 功能测试通过")
    
    @curry_class_optimized
    class CurriedClass:
        def add(self, a, b, c):
            return a + b + c
        
        def multiply(self, x, y):
            return x * y
    
    cc = CurriedClass()
    assert cc.add(1).add(2).add(3) == 6, "curry_class_optimized: 链式调用失败"
    assert cc.multiply(5).multiply(6) == 30, "curry_class_optimized: multiply失败"
    assert cc.add(1, 2, 3) == 6, "curry_class_optimized: 直接调用失败"
    print("[OK] curry_decorator_optimized 功能测试通过")
    
    @delay_curry_optimized
    def delay_add(a, b, c):
        return a + b + c
    
    assert delay_add(1)(2)(3)() == 6, "delay_curry_optimized: 延迟调用失败"
    print("[OK] curry_delay_optimized 功能测试通过")
    
    print("\n=== 所有功能测试通过 ===\n")


def main():
    test_functional_correctness()
    
    print("=" * 140)
    print("curry 装饰器优化版本高压测试")
    print("=" * 140)
    
    iterations = 10000
    print(f"\n测试配置: {iterations} 次迭代\n")
    print(f"{'测试名称':<60} | {'耗时':>8} | {'OPS':>12} | {'内存峰值':>12} | {'对比':>10}")
    print("-" * 140)
    
    # ========== curry_core 测试 ==========
    print("\n【curry_core - 标准柯里化】")
    
    @curry_original
    def add3_original(a, b, c):
        return a + b + c
    
    @curry_optimized
    def add3_optimized(a, b, c):
        return a + b + c
    
    @curry_original
    def mul2_original(a, b):
        return a * b
    
    @curry_optimized
    def mul2_optimized(a, b):
        return a * b
    
    _, ops_original, _ = benchmark("curry (原始): add3(1)(2)(3)", lambda: add3_original(1)(2)(3), iterations)
    _, ops_optimized, _ = benchmark("curry (优化): add3(1)(2)(3)", lambda: add3_optimized(1)(2)(3), iterations)
    print(f"{'性能提升':<60} | {'':>8} | {'':>12} | {'':>12} | {(ops_optimized/ops_original):>10.2f}x")
    
    _, ops_original, _ = benchmark("curry (原始): mul2(2)(3)", lambda: mul2_original(2)(3), iterations)
    _, ops_optimized, _ = benchmark("curry (优化): mul2(2)(3)", lambda: mul2_optimized(2)(3), iterations)
    print(f"{'性能提升':<60} | {'':>8} | {'':>12} | {'':>12} | {(ops_optimized/ops_original):>10.2f}x")
    
    class CalculatorOriginal:
        @curry_original
        def add(self, a, b):
            return a + b
    
    class CalculatorOptimized:
        @curry_optimized
        def add(self, a, b):
            return a + b
    
    calc_original = CalculatorOriginal()
    calc_optimized = CalculatorOptimized()
    
    _, ops_original, _ = benchmark("curry (原始): 实例方法", lambda: calc_original.add(1)(2), iterations)
    _, ops_optimized, _ = benchmark("curry (优化): 实例方法", lambda: calc_optimized.add(1)(2), iterations)
    print(f"{'性能提升':<60} | {'':>8} | {'':>12} | {'':>12} | {(ops_optimized/ops_original):>10.2f}x")
    
    # ========== curry_decorator 测试 ==========
    print("\n【curry_decorator - 类装饰器】")
    
    @curry_class_original
    class CurriedClassOriginal:
        def add(self, a, b, c):
            return a + b + c
        
        def multiply(self, x, y):
            return x * y
    
    @curry_class_optimized
    class CurriedClassOptimized:
        def add(self, a, b, c):
            return a + b + c
        
        def multiply(self, x, y):
            return x * y
    
    cco = CurriedClassOriginal()
    cco_opt = CurriedClassOptimized()
    
    _, ops_original, _ = benchmark("curry_class (原始): cc.add(1).add(2).add(3)", lambda: cco.add(1).add(2).add(3), iterations)
    _, ops_optimized, _ = benchmark("curry_class (优化): cc.add(1).add(2).add(3)", lambda: cco_opt.add(1).add(2).add(3), iterations)
    print(f"{'性能提升':<60} | {'':>8} | {'':>12} | {'':>12} | {(ops_optimized/ops_original):>10.2f}x")
    
    _, ops_original, _ = benchmark("curry_class (原始): cc.multiply(5).multiply(6)", lambda: cco.multiply(5).multiply(6), iterations)
    _, ops_optimized, _ = benchmark("curry_class (优化): cc.multiply(5).multiply(6)", lambda: cco_opt.multiply(5).multiply(6), iterations)
    print(f"{'性能提升':<60} | {'':>8} | {'':>12} | {'':>12} | {(ops_optimized/ops_original):>10.2f}x")
    
    # ========== curry_delay 测试 ==========
    print("\n【curry_delay - 延迟柯里化】")
    
    @delay_curry_original
    def delay_add_original(a, b, c):
        return a + b + c
    
    @delay_curry_optimized
    def delay_add_optimized(a, b, c):
        return a + b + c
    
    _, ops_original, _ = benchmark("delay_curry (原始): delay_add(1)(2)(3)()", lambda: delay_add_original(1)(2)(3)(), iterations)
    _, ops_optimized, _ = benchmark("delay_curry (优化): delay_add(1)(2)(3)()", lambda: delay_add_optimized(1)(2)(3)(), iterations)
    print(f"{'性能提升':<60} | {'':>8} | {'':>12} | {'':>12} | {(ops_optimized/ops_original):>10.2f}x")
    
    # ========== 内存压力测试 ==========
    print("\n" + "=" * 140)
    print("内存压力测试")
    print("=" * 140)
    
    for mod_name, decorator_original, decorator_optimized in [
        ("curry_core", curry_original, curry_optimized), 
        ("curry_delay", delay_curry_original, delay_curry_optimized)
    ]:
        gc.collect()
        tracemalloc.start()
        
        @decorator_original
        def test_func_original(a, b):
            return a + b
        
        for i in range(50000):
            test_func_original(i)(i+1)
        
        current_original, peak_original = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        gc.collect()
        tracemalloc.start()
        
        @decorator_optimized
        def test_func_optimized(a, b):
            return a + b
        
        for i in range(50000):
            test_func_optimized(i)(i+1)
        
        current_optimized, peak_optimized = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        print(f"{mod_name}:")
        print(f"  原始版本 - 内存增长: {current_original / 1024:.1f} KB, 峰值内存: {peak_original / 1024:.1f} KB")
        print(f"  优化版本 - 内存增长: {current_optimized / 1024:.1f} KB, 峰值内存: {peak_optimized / 1024:.1f} KB")
        print(f"  内存优化: {(1 - current_optimized/current_original) * 100:+.1f}%\n")


if __name__ == '__main__':
    main()