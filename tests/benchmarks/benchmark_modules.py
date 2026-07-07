"""
基准测试脚本 - 评估各模块性能
"""
import time
import random
from functools import partial

def benchmark(name, func, iterations=10000):
    """运行基准测试"""
    start = time.time()
    for _ in range(iterations):
        func()
    elapsed = time.time() - start
    print(f"{name}: {elapsed:.4f}s for {iterations} iterations")
    return elapsed

def test_lazy():
    """测试 lazy 模块性能"""
    from vools.decorators.lazy import lazy
    
    @lazy
    def slow_func():
        return 42
    
    def test():
        return slow_func()
    
    benchmark("lazy 基础调用", test)
    
    @lazy
    def compute():
        return sum(range(100))
    
    def test_compute():
        return compute()
    
    benchmark("lazy 计算调用", test_compute)

def test_cache():
    """测试 cache 模块性能"""
    from vools.cache import memorize
    
    @memorize
    def fib(n):
        if n <= 1:
            return n
        return fib(n-1) + fib(n-2)
    
    def test():
        return fib(20)
    
    benchmark("memorize 缓存", test)

def test_overload():
    """测试 overload 模块性能"""
    from vools.decorators.overload import overload
    
    @overload
    def overload_func_int(a: int):
        return a * 2
    
    def test():
        return overload_func_int(42)
    
    benchmark("overload int 调用", test)

def test_shotcut():
    """测试 shotcut 模块性能"""
    from vools.decorators.shotcut import singleton, timeit
    
    @singleton
    class MyClass:
        def __init__(self):
            self.value = 42
    
    def test_singleton():
        return MyClass().value
    
    benchmark("singleton 装饰器", test_singleton)

def test_box():
    """测试 box 模块性能"""
    from vools.functional.box import Box
    
    def test():
        return Box([1, 2, 3]).map(lambda x: x * 2).filter(lambda x: x > 2).run()
    
    benchmark("Box 链式调用", test)

def test_placeholder():
    """测试 placeholder 模块性能"""
    from vools.functional.placeholder import _, _1, _2
    
    def test():
        return (_ + _1)(3, 4)
    
    benchmark("placeholder 二元运算", test)
    
    def test_chain():
        return (_ * 2 + _1)(3, 5)
    
    benchmark("placeholder 链式运算", test_chain)

def test_pipe_ops():
    """测试 pipe_ops 模块性能"""
    from vools.functional.pipe_ops import p, ops
    
    def test():
        return p([1, 2, 3, 4]) >> ops.filter(lambda x: x > 2) >> ops.map(lambda x: x * 2)
    
    benchmark("pipe_ops 管道操作", test)

def test_iif():
    """测试 iif 模块性能"""
    from vools.functional.iif import iif
    
    def test():
        return iif(True, 1, 2)
    
    benchmark("iif 基础调用", test)
    
    def test_callable():
        return iif(lambda: True, lambda: 1, lambda: 2)
    
    benchmark("iif 可调用条件", test_callable)

def test_curry():
    """测试 curry 模块性能"""
    from vools.decorators.curry_core import curry
    
    @curry
    def add(a, b, c):
        return a + b + c
    
    def test():
        return add(1)(2)(3)
    
    benchmark("curry 链式调用", test)

def test_delay_curry():
    """测试 delay_curry 模块性能"""
    from vools.decorators.curry_delay import delay_curry
    
    @delay_curry
    def add(a, b):
        return a + b
    
    def test():
        return add(1)(2)
    
    benchmark("delay_curry 链式调用", test)

if __name__ == "__main__":
    print("=" * 60)
    print("VOOLS 模块性能基准测试")
    print("=" * 60)
    
    test_lazy()
    print()
    
    test_cache()
    print()
    
    test_overload()
    print()
    
    test_shotcut()
    print()
    
    test_box()
    print()
    
    test_placeholder()
    print()
    
    test_pipe_ops()
    print()
    
    test_iif()
    print()
    
    test_curry()
    print()
    
    test_delay_curry()
    print()
    
    print("=" * 60)
    print("基准测试完成")
    print("=" * 60)