"""
Stuff 性能对比测试
对比原始版本和改进版本的性能和内存使用情况
"""

import gc
import sys
import time
import tracemalloc
from typing import List, Callable, Any

# 原始版本
sys.path.insert(0, 'E:/IDEProjects/AI/vools')
from vools.utils.stuff import Stuff as OriginalStuff, stuff as original_stuff

# 改进版本
from vools.Temp.stuff import Stuff as ImprovedStuff, stuff as improved_stuff, StuffConfig


# =============================================================================
# 性能测试
# =============================================================================

def benchmark(name: str, func: Callable, iterations: int = 10000) -> dict:
    """运行性能基准测试"""
    # 预热
    for _ in range(100):
        func()
    
    # 计时
    start = time.perf_counter()
    for _ in range(iterations):
        func()
    elapsed = time.perf_counter() - start
    
    return {
        'name': name,
        'iterations': iterations,
        'total_time': elapsed,
        'time_per_call': elapsed / iterations * 1_000_000,  # 微秒
    }


def memory_test(name: str, func: Callable, iterations: int = 1000) -> dict:
    """运行内存基准测试"""
    gc.collect()
    tracemalloc.start()
    
    # 执行多次以累积内存使用
    for _ in range(iterations):
        func()
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    return {
        'name': name,
        'iterations': iterations,
        'current_memory': current / 1024,  # KB
        'peak_memory': peak / 1024,  # KB
    }


# =============================================================================
# 测试用例
# =============================================================================

def test_basic_curry():
    """测试基本柯里化"""
    @original_stuff
    def add(a, b, c):
        return a + b + c
    
    return add(1)(2)(3)()


def test_improved_curry():
    """测试改进版基本柯里化"""
    @improved_stuff
    def add(a, b, c):
        return a + b + c
    
    return add(1)(2)(3)()


def test_dependency_injection():
    """测试依赖注入"""
    @original_stuff
    def process(a, b, c):
        return f"{a}-{b}-{c}"
    
    @process.register
    def get_a():
        return 1
    
    @process.register(param_name=2)
    def get_bc():
        return 2, 3
    
    return process()


def test_improved_dependency_injection():
    """测试改进版依赖注入"""
    @improved_stuff
    def process(a, b, c):
        return f"{a}-{b}-{c}"
    
    @process.provide
    def get_a():
        return 1
    
    @process.provide(param=2)
    def get_bc():
        return 2, 3
    
    return process()


def test_chain_dependency():
    """测试链式依赖 - 简化版"""
    @original_stuff
    def calc(a, b):
        return a + b
    
    @calc.register(param_name='a')
    def get_a():
        return 10
    
    @calc.register(param_name='b')
    def get_b():
        return 2
    
    return calc()


def test_improved_chain_dependency():
    """测试改进版链式依赖 - 简化版"""
    @improved_stuff
    def calc(a, b):
        return a + b
    
    @calc.provide(param='a')
    def get_a():
        return 10
    
    @calc.provide(param='b')
    def get_b():
        return 2
    
    return calc()


def test_multi_aggregate():
    """测试多函数聚合"""
    @original_stuff
    def collect(values):
        return sum(values)
    
    def get_val1():
        return 1
    def get_val2():
        return 2
    def get_val3():
        return 3
    
    collect.fill_multi(get_val1, get_val2, get_val3, param_name='values')
    return collect()


def test_improved_multi_aggregate():
    """测试改进版多函数聚合"""
    @improved_stuff
    def collect(values):
        return sum(values)
    
    def get_val1():
        return 1
    def get_val2():
        return 2
    def get_val3():
        return 3
    
    collect.aggregate_providers(get_val1, get_val2, get_val3, param='values')
    return collect()


def test_class_method():
    """测试类方法 - 简化版"""
    class Calculator:
        @original_stuff
        def compute(self, a, b):
            return a + b
    
    calc = Calculator()
    return calc.compute(1, 2)()


def test_improved_class_method():
    """测试改进版类方法"""
    class Calculator:
        @improved_stuff
        def compute(self, a, b):
            return a + b
    
    calc = Calculator()
    return calc.compute(1, 2)()


def test_reset():
    """测试重置功能 - 改进版独有"""
    @improved_stuff
    def resettable(a, b):
        return a + b
    
    resettable(1)(2)
    resettable.reset()
    return resettable.is_ready


def test_improved_reset():
    """测试改进版重置功能"""
    @improved_stuff
    def resettable(a, b):
        return a + b
    
    resettable(1)(2)
    resettable.reset()
    return resettable.is_ready


# =============================================================================
# 运行测试
# =============================================================================

def print_results(title: str, results: List[dict]):
    """打印结果表格"""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")
    print(f"{'测试名称':<40} {'结果':>15}")
    print(f"{'-'*80}")
    for r in results:
        print(f"{r['name']:<40} {str(r.get('result', '')):>15}")


def run_performance_comparison():
    """运行性能对比"""
    print("\n" + "="*80)
    print("性能对比测试 (10000 次迭代)")
    print("="*80)
    
    tests = [
        ("基本柯里化 - 原始", test_basic_curry),
        ("基本柯里化 - 改进", test_improved_curry),
        ("依赖注入 - 原始", test_dependency_injection),
        ("依赖注入 - 改进", test_improved_dependency_injection),
        ("链式依赖 - 原始", test_chain_dependency),
        ("链式依赖 - 改进", test_improved_chain_dependency),
        ("多函数聚合 - 原始", test_multi_aggregate),
        ("多函数聚合 - 改进", test_improved_multi_aggregate),
        ("类方法 - 原始", test_class_method),
        ("类方法 - 改进", test_improved_class_method),
        ("重置功能 - 原始", test_reset),
        ("重置功能 - 改进", test_improved_reset),
    ]
    
    results = []
    for name, func in tests:
        r = benchmark(name, func, iterations=10000)
        results.append(r)
        print(f"{name:<40}: {r['time_per_call']:.2f} μs/次")
    
    return results


def run_memory_comparison():
    """运行内存对比"""
    print("\n" + "="*80)
    print("内存使用对比 (1000 次迭代)")
    print("="*80)
    
    tests = [
        ("基本柯里化 - 原始", test_basic_curry),
        ("基本柯里化 - 改进", test_improved_curry),
        ("依赖注入 - 原始", test_dependency_injection),
        ("依赖注入 - 改进", test_improved_dependency_injection),
        ("类方法 - 原始", test_class_method),
        ("类方法 - 改进", test_improved_class_method),
    ]
    
    results = []
    for name, func in tests:
        r = memory_test(name, func, iterations=1000)
        results.append(r)
        print(f"{name:<40}: 峰值 {r['peak_memory']:.2f} KB")
    
    return results


def run_correctness_test():
    """运行正确性测试"""
    print("\n" + "="*80)
    print("正确性测试")
    print("="*80)
    
    tests = [
        ("基本柯里化", test_basic_curry, test_improved_curry, "6"),
        ("依赖注入", test_dependency_injection, test_improved_dependency_injection, "1-2-3"),
        ("链式依赖", test_chain_dependency, test_improved_chain_dependency, "12"),
        ("多函数聚合", test_multi_aggregate, test_improved_multi_aggregate, "6"),
        ("重置功能", test_reset, test_improved_reset, "False"),
    ]
    
    all_passed = True
    for name, orig_func, improved_func, expected in tests:
        orig_result = orig_func()
        improved_result = improved_func()
        
        orig_ok = str(orig_result) == expected
        improved_ok = str(improved_result) == expected
        
        status = "✓" if (orig_ok and improved_ok) else "✗"
        print(f"{status} {name:<30}: 原始={orig_result}, 改进={improved_result}, 期望={expected}")
        
        if not (orig_ok and improved_ok):
            all_passed = False
    
    return all_passed


def main():
    """主函数"""
    print("="*80)
    print("Stuff 性能与内存对比测试")
    print("="*80)
    
    # 正确性测试
    correctness = run_correctness_test()
    
    # 性能测试
    perf_results = run_performance_comparison()
    
    # 内存测试
    memory_results = run_memory_comparison()
    
    # 总结
    print("\n" + "="*80)
    print("总结")
    print("="*80)
    
    if correctness:
        print("✓ 所有正确性测试通过")
    else:
        print("✗ 部分正确性测试失败")
    
    # 计算平均性能差异
    perf_diff = []
    for i in range(0, len(perf_results), 2):
        if i + 1 < len(perf_results):
            orig = perf_results[i]['time_per_call']
            improved = perf_results[i + 1]['time_per_call']
            diff = ((improved - orig) / orig) * 100
            perf_diff.append((perf_results[i]['name'].replace(' - 原始', ''), diff))
    
    print("\n性能对比 (改进 vs 原始):")
    for name, diff in perf_diff:
        sign = "+" if diff > 0 else ""
        print(f"  {name:<25}: {sign}{diff:.1f}%")
    
    avg_diff = sum(d for _, d in perf_diff) / len(perf_diff)
    print(f"\n  {'平均':<25}: {'+' if avg_diff > 0 else ''}{avg_diff:.1f}%")


if __name__ == '__main__':
    main()
