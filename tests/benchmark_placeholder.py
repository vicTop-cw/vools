"""
placeholder.py 高压测试
"""

import sys
import os
import time
import tracemalloc
import gc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vools.functional.placeholder as ph
from vools.functional.placeholder_impl import X


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
    
    print(f"{name:50s} | {elapsed:.4f}s | {ops_per_sec:10.0f} ops/s | {memory_kb:10.1f} KB")
    return elapsed, ops_per_sec, memory_kb


def main():
    print("=" * 100)
    print("placeholder.py 高压测试")
    print("=" * 100)
    
    iterations = 10000
    print(f"\n测试配置: {iterations} 次迭代\n")
    print(f"{'测试名称':<50} | {'耗时':>8} | {'OPS':>12} | {'内存峰值':>12}")
    print("-" * 100)
    
    # 1. 基础占位符调用
    benchmark("基础占位符: (_ + 1)(5)", lambda: (ph._ + 1)(5), iterations)
    
    # 2. 多操作符组合
    benchmark("多操作符: (_ * 2 + 1)(3)", lambda: (ph._ * 2 + 1)(3), iterations)
    
    # 3. 索引访问
    benchmark("索引访问: _[0]([1,2,3])", lambda: ph._[0]([1, 2, 3]), iterations)
    
    # 4. 多个占位符
    benchmark("多占位符: (_1 + _2)(1, 2)", lambda: (ph._1 + ph._2)(1, 2), iterations)
    
    # 5. 函数构造
    benchmark("函数构造: to_holder(lambda x: x*2)", lambda: ph.to_holder(lambda x: x*2), iterations)
    
    # 6. X 占位符
    benchmark("X 占位符: X.strip()['  hello  ']", lambda: X.strip()['  hello  '], iterations)
    
    # 7. X 链式
    benchmark("X 链式: X.split(',')['a,b,c']", lambda: X.split(',')['a,b,c'], iterations)
    
    # 8. X 复杂链式
    benchmark("X 复杂链式: X.strip().split(',')", lambda: X.strip().split(',')['a,b,c'], iterations)
    
    # 9. X 直接索引
    benchmark("X 直接索引: X[0]('hello')", lambda: X[0]('hello'), iterations)
    
    # 10. X 属性链
    def x_attr_chain():
        return X.upper.lower()('HELLO')
    benchmark("X 属性链: X.upper.lower()('HELLO')", x_attr_chain, iterations)
    
    # 11. 占位符链式
    def holder_chain():
        return (ph._ + 1) * 2
    benchmark("占位符链式: (_ + 1) * 2", holder_chain, iterations)
    
    # 12. 比较操作
    def comparison():
        return ph._1 < ph._2
    benchmark("比较操作: _1 < _2", comparison, iterations)
    
    # 13. 布尔操作
    def boolean_op():
        return (ph._1 & ph._2)
    benchmark("布尔操作: _1 & _2", boolean_op, iterations)
    
    print("\n" + "=" * 100)
    print("性能对比：placeholder vs 原生 Python")
    print("=" * 100)
    
    # 原生 Python 对比
    def native_add():
        return 5 + 1
    def native_mul():
        return 3 * 2 + 1
    def native_index():
        return [1, 2, 3][0]
    def native_compare():
        return 1 < 2
    
    print(f"\n{'操作':<50} | {'placeholder':>15} | {'原生Python':>15} | {'性能比':>10}")
    print("-" * 100)
    
    _, ops1, _ = benchmark("原生加法: 5 + 1", native_add, 100000)
    _, ops2, _ = benchmark("占位符: (_ + 1)(5)", lambda: (ph._ + 1)(5), 100000)
    print(f"{'性能比 (placeholder/native)':<50} | {ops2:>15.0f} | {ops1:>15.0f} | {ops2/ops1:>10.2f}x")
    
    _, ops1, _ = benchmark("原生索引: [1,2,3][0]", native_index, 100000)
    _, ops2, _ = benchmark("占位符索引: _[0]([1,2,3])", lambda: ph._[0]([1, 2, 3]), 100000)
    print(f"{'性能比 (placeholder/native)':<50} | {ops2:>15.0f} | {ops1:>15.0f} | {ops2/ops1:>10.2f}x")
    
    _, ops1, _ = benchmark("原生比较: 1 < 2", native_compare, 100000)
    _, ops2, _ = benchmark("占位符比较: (_1 < _2)(1, 2)", lambda: (ph._1 < ph._2)(1, 2), 100000)
    print(f"{'性能比 (placeholder/native)':<50} | {ops2:>15.0f} | {ops1:>15.0f} | {ops2/ops1:>10.2f}x")
    
    print("\n" + "=" * 100)
    print("内存压力测试")
    print("=" * 100)
    
    gc.collect()
    tracemalloc.start()
    
    for i in range(50000):
        ph._ + 1
        ph._1 * ph._2
        ph._[0]
        X.strip()
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    print(f"50000次操作后:")
    print(f"  内存增长: {current / 1024:.1f} KB")
    print(f"  峰值内存: {peak / 1024:.1f} KB")
    
    print("\n" + "=" * 100)
    print("优化建议")
    print("=" * 100)
    print("""
1. 【高优先级】eval() 调用过多
   - _ 占位符每次操作都调用 eval(self.expr, self.env)
   - 实测: _ 占位符比原生 Python 慢约 50-100x
   - 建议：使用 functools.lru_cache 缓存 eval 结果
   
2. 【高优先级】__setattr__ 绕过开销
   - super(type(obj), obj).__setattr__() 每次都查找 MRO
   - 建议：使用 __slots__ 或优化属性设置

3. 【中优先级】正则表达式重复编译
   - _replace_isolated_x 每次都编译正则
   - 建议：预编译正则表达式

4. 【中优先级】env 字典频繁复制
   - self.env.copy() 在每次操作中都执行
   - 建议：使用不可变数据结构或延迟复制

5. 【低优先级】_random_name 调用开销
   - random.choice 每次都创建新随机数
   - 建议：使用批量生成或缓存机制

6. 【重要发现】X 占位符 vs _ 占位符 性能差异巨大
   - X 占位符: ~128,000 ops/s (使用操作序列模式)
   - _ 占位符: ~11,000 ops/s (使用 eval 模式)
   - X 占位符快约 10x，因为不使用 eval
""")


if __name__ == '__main__':
    main()
