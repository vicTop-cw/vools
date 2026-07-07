"""
curry 装饰器高压测试
"""
import sys
import os
import time
import tracemalloc
import gc
from vools.decorators.curry_core import curry
from vools.decorators.curry_decorator import curry_class
from vools.decorators.curry_delay import delay_curry


def benchmark(name, func, iterations=10000):
    """基准测试"""
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


def main():
    print("=" * 120)
    print("curry 装饰器高压测试")
    print("=" * 120)
    
    iterations = 10000
    print(f"\n测试配置: {iterations} 次迭代\n")
    print(f"{'测试名称':<60} | {'耗时':>8} | {'OPS':>12} | {'内存峰值':>12}")
    print("-" * 120)
    
    # ========== curry_core 测试 ==========
    print("\n【curry_core - 标准柯里化】")
    
    @curry
    def add3(a, b, c):
        return a + b + c
    
    @curry
    def mul2(a, b):
        return a * b
    
    benchmark("curry: 完整调用 add3(1)(2)(3)", lambda: add3(1)(2)(3), iterations)
    benchmark("curry: 部分调用 add3(1)(2)", lambda: add3(1)(2), iterations)
    benchmark("curry: 直接调用 add3(1, 2, 3)", lambda: add3(1, 2, 3), iterations)
    benchmark("curry: mul2(2)(3)", lambda: mul2(2)(3), iterations)
    
    # 类方法测试
    class Calculator:
        @curry
        def add(self, a, b):
            return a + b
    
    calc = Calculator()
    benchmark("curry: 实例方法 calc.add(1)(2)", lambda: calc.add(1)(2), iterations)
    
    # ========== curry_decorator 测试 ==========
    print("\n【curry_decorator - 类装饰器】")
    
    @curry_class
    class CurriedClass:
        def add(self, a, b, c):
            return a + b + c
        
        def multiply(self, x, y):
            return x * y
    
    cc = CurriedClass()
    benchmark("curry_class: cc.add(1).add(2).add(3)", lambda: cc.add(1).add(2).add(3), iterations)
    benchmark("curry_class: cc.multiply(5).multiply(6)", lambda: cc.multiply(5).multiply(6), iterations)
    benchmark("curry_class: cc.add(1, 2, 3) 直接调用", lambda: cc.add(1, 2, 3), iterations)
    
    # ========== curry_delay 测试 ==========
    print("\n【curry_delay - 延迟柯里化】")
    
    @delay_curry
    def delay_add(a, b, c):
        return a + b + c
    
    @delay_curry
    def delay_mul(a, b):
        return a * b
    
    benchmark("delay_curry: delay_add(1)(2)(3)()", lambda: delay_add(1)(2)(3)(), iterations)
    benchmark("delay_curry: delay_mul(2)(3)()", lambda: delay_mul(2)(3)(), iterations)
    
    # ========== 性能对比 ==========
    print("\n" + "=" * 120)
    print("性能对比：curry vs 原生 Python")
    print("=" * 120)
    
    def native_add3(a, b, c):
        return a + b + c
    
    print(f"\n{'操作':<60} | {'curry':>15} | {'原生Python':>15} | {'性能比':>10}")
    print("-" * 120)
    
    _, ops1, _ = benchmark("原生: add3(1, 2, 3)", lambda: native_add3(1, 2, 3), 100000)
    _, ops2, _ = benchmark("curry: add3(1)(2)(3)", lambda: add3(1)(2)(3), 100000)
    print(f"{'性能比 (curry/native)':<60} | {ops2:>15.0f} | {ops1:>15.0f} | {ops2/ops1:>10.2f}x")
    
    _, ops1, _ = benchmark("原生: 直接调用", lambda: native_add3(1, 2, 3), 100000)
    _, ops2, _ = benchmark("curry_class: 直接调用", lambda: cc.add(1, 2, 3), 100000)
    print(f"{'性能比 (curry_class/native)':<60} | {ops2:>15.0f} | {ops1:>15.0f} | {ops2/ops1:>10.2f}x")
    
    _, ops1, _ = benchmark("原生: 直接调用", lambda: native_add3(1, 2, 3), 100000)
    _, ops2, _ = benchmark("delay_curry: 延迟调用", lambda: delay_add(1)(2)(3)(), 100000)
    print(f"{'性能比 (delay_curry/native)':<60} | {ops2:>15.0f} | {ops1:>15.0f} | {ops2/ops1:>10.2f}x")
    
    # ========== 内存压力测试 ==========
    print("\n" + "=" * 120)
    print("内存压力测试")
    print("=" * 120)
    
    for mod_name, decorator in [("curry_core", curry), ("curry_delay", delay_curry)]:
        gc.collect()
        tracemalloc.start()
        
        @decorator
        def test_func(a, b):
            return a + b
        
        for i in range(50000):
            test_func(i)(i+1)
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        print(f"{mod_name}:")
        print(f"  内存增长: {current / 1024:.1f} KB")
        print(f"  峰值内存: {peak / 1024:.1f} KB")
    
    # ========== 优化建议 ==========
    print("\n" + "=" * 120)
    print("优化建议")
    print("=" * 120)
    print("""
1. 【高优先级】函数签名重复解析
   - curry_core.py 中的 _get_cached_signature 使用 lru_cache，但每次创建新对象都会重新解析
   - 建议：缓存函数签名信息到装饰器级别

2. 【高优先级】is_strict 类型检查开销
   - 每次调用都进行类型检查
   - 建议：默认关闭严格模式，或延迟类型检查到执行时

3. 【中优先级】对象创建开销
   - 每次柯里化调用都创建新的 Curried 对象
   - 建议：复用对象或使用 __slots__ 优化

4. 【中优先级】dict 操作开销
   - bound_args.copy() 和 {**dict1, **dict2} 频繁调用
   - 建议：使用不可变数据结构

5. 【低优先级】字符串操作开销
   - 参数名处理和字符串拼接
   - 建议：预编译或缓存字符串操作

6. 【重要发现】curry_class 每次实例化都重新处理方法
   - 建议：将方法处理移到类级别而非实例级别
""")


if __name__ == '__main__':
    main()
