#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vools.curried 性能测试套件

与 toolz 官方 curried 模块进行性能对比测试。
"""

import sys
import os
import time
import gc
import tracemalloc
from functools import reduce as functools_reduce
def measure_time(func, iterations=10000):
    """测量函数执行时间"""
    gc.disable()
    start = time.perf_counter()
    for _ in range(iterations):
        func()
    end = time.perf_counter()
    gc.enable()
    return (end - start) / iterations * 1000  # 返回毫秒


def measure_memory(func, iterations=1000):
    """测量函数内存占用"""
    gc.collect()
    tracemalloc.start()
    for _ in range(iterations):
        func()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024  # 返回 KB


def run_performance_tests():
    """运行性能测试"""
    print("=" * 70)
    print("vools.curried vs toolz.curried 性能对比测试")
    print("=" * 70)

    # 检查 toolz 是否可用
    try:
        from toolz import curried as toolz_curried
        TOOLZ_AVAILABLE = True
        print("toolz 已安装，性能测试将包括对比")
    except ImportError:
        TOOLZ_AVAILABLE = False
        print("toolz 未安装，仅测试 vools.curried")

    print()

    # 测试配置
    iterations = 50000
    memory_iterations = 1000

    # =========================================================================
    # 测试 map 函数
    # =========================================================================
    print("-" * 70)
    print("1. map 函数测试")
    print("-" * 70)

    from vools.curried import map as vools_map

    data = list(range(1000))
    vools_map_func = vools_map(lambda x: x * 2)

    def vools_map_test():
        return vools_map_func(data)

    vools_time = measure_time(vools_map_test, iterations)
    print(f"vools.map: {vools_time:.4f} ms/iter")

    if TOOLZ_AVAILABLE:
        from toolz.curried import map as toolz_map
        toolz_map_func = toolz_map(lambda x: x * 2)

        def toolz_map_test():
            return toolz_map_func(data)

        toolz_time = measure_time(toolz_map_test, iterations)
        print(f"toolz.map: {toolz_time:.4f} ms/iter")
        ratio = vools_time / toolz_time if toolz_time > 0 else float('inf')
        print(f"性能比: {ratio:.2f}x {'(vools 较慢)' if ratio > 1 else '(vools 更快)'}")

    print()

    # =========================================================================
    # 测试 filter 函数
    # =========================================================================
    print("-" * 70)
    print("2. filter 函数测试")
    print("-" * 70)

    from vools.curried import filter as vools_filter

    vools_filter_func = vools_filter(lambda x: x % 2 == 0)

    def vools_filter_test():
        return vools_filter_func(data)

    vools_time = measure_time(vools_filter_test, iterations)
    print(f"vools.filter: {vools_time:.4f} ms/iter")

    if TOOLZ_AVAILABLE:
        from toolz.curried import filter as toolz_filter
        toolz_filter_func = toolz_filter(lambda x: x % 2 == 0)

        def toolz_filter_test():
            return toolz_filter_func(data)

        toolz_time = measure_time(toolz_filter_test, iterations)
        print(f"toolz.filter: {toolz_time:.4f} ms/iter")
        ratio = vools_time / toolz_time if toolz_time > 0 else float('inf')
        print(f"性能比: {ratio:.2f}x {'(vools 较慢)' if ratio > 1 else '(vools 更快)'}")

    print()

    # =========================================================================
    # 测试 reduce 函数
    # =========================================================================
    print("-" * 70)
    print("3. reduce 函数测试")
    print("-" * 70)

    from vools.curried import reduce as vools_reduce

    vools_reduce_func = vools_reduce(lambda x, y: x + y)

    def vools_reduce_test():
        return vools_reduce_func(data)

    vools_time = measure_time(vools_reduce_test, iterations)
    print(f"vools.reduce: {vools_time:.4f} ms/iter")

    if TOOLZ_AVAILABLE:
        from toolz.curried import reduce as toolz_reduce
        toolz_reduce_func = toolz_reduce(lambda x, y: x + y)

        def toolz_reduce_test():
            return toolz_reduce_func(data)

        toolz_time = measure_time(toolz_reduce_test, iterations)
        print(f"toolz.reduce: {toolz_time:.4f} ms/iter")
        ratio = vools_time / toolz_time if toolz_time > 0 else float('inf')
        print(f"性能比: {ratio:.2f}x {'(vools 较慢)' if ratio > 1 else '(vools 更快)'}")

    print()

    # =========================================================================
    # 测试 compose 函数
    # =========================================================================
    print("-" * 70)
    print("4. compose 函数测试")
    print("-" * 70)

    from vools.curried import compose as vools_compose

    vools_composed = vools_compose(
        lambda x: x * 2,
        lambda x: x + 1,
        lambda x: x ** 2
    )

    def vools_compose_test():
        return vools_composed(5)

    vools_time = measure_time(vools_compose_test, iterations)
    print(f"vools.compose: {vools_time:.4f} ms/iter")

    if TOOLZ_AVAILABLE:
        from toolz.curried import compose as toolz_compose
        toolz_composed = toolz_compose(
            lambda x: x * 2,
            lambda x: x + 1,
            lambda x: x ** 2
        )

        def toolz_compose_test():
            return toolz_composed(5)

        toolz_time = measure_time(toolz_compose_test, iterations)
        print(f"toolz.compose: {toolz_time:.4f} ms/iter")
        ratio = vools_time / toolz_time if toolz_time > 0 else float('inf')
        print(f"性能比: {ratio:.2f}x {'(vools 较慢)' if ratio > 1 else '(vools 更快)'}")

    print()

    # =========================================================================
    # 测试 unique 函数
    # =========================================================================
    print("-" * 70)
    print("5. unique 函数测试")
    print("-" * 70)

    from vools.curried import unique as vools_unique

    unique_data = list(range(100)) * 10  # 1000 个元素，有重复

    def vools_unique_test():
        return vools_unique(unique_data)

    vools_time = measure_time(vools_unique_test, iterations)
    print(f"vools.unique: {vools_time:.4f} ms/iter")

    if TOOLZ_AVAILABLE:
        from toolz.curried import unique as toolz_unique

        def toolz_unique_test():
            return toolz_unique(unique_data)

        toolz_time = measure_time(toolz_unique_test, iterations)
        print(f"toolz.unique: {toolz_time:.4f} ms/iter")
        ratio = vools_time / toolz_time if toolz_time > 0 else float('inf')
        print(f"性能比: {ratio:.2f}x {'(vools 较慢)' if ratio > 1 else '(vools 更快)'}")

    print()

    # =========================================================================
    # 测试 groupby 函数
    # =========================================================================
    print("-" * 70)
    print("6. groupby 函数测试")
    print("-" * 70)

    from vools.curried import groupby as vools_groupby

    groupby_data = list(range(100)) * 10

    def vools_groupby_test():
        return vools_groupby(lambda x: x % 10, groupby_data)

    vools_time = measure_time(vools_groupby_test, iterations)
    print(f"vools.groupby: {vools_time:.4f} ms/iter")

    if TOOLZ_AVAILABLE:
        from toolz.curried import groupby as toolz_groupby

        def toolz_groupby_test():
            return toolz_groupby(lambda x: x % 10, groupby_data)

        toolz_time = measure_time(toolz_groupby_test, iterations)
        print(f"toolz.groupby: {toolz_time:.4f} ms/iter")
        ratio = vools_time / toolz_time if toolz_time > 0 else float('inf')
        print(f"性能比: {ratio:.2f}x {'(vools 较慢)' if ratio > 1 else '(vools 更快)'}")

    print()

    # =========================================================================
    # 内存占用测试
    # =========================================================================
    print("-" * 70)
    print("7. 内存占用测试 (KB)")
    print("-" * 70)

    from vools.curried import map as vools_map, filter as vools_filter, reduce as vools_reduce

    vools_map_func = vools_map(lambda x: x * 2)
    vools_filter_func = vools_filter(lambda x: x % 2 == 0)
    vools_reduce_func = vools_reduce(lambda x, y: x + y)

    large_data = list(range(10000))

    def vools_memory_test():
        r = vools_map_func(large_data)
        r = vools_filter_func(r)
        return vools_reduce_func(r)

    vools_memory = measure_memory(vools_memory_test, memory_iterations)
    print(f"vools 组合操作: {vools_memory:.2f} KB")

    if TOOLZ_AVAILABLE:
        from toolz.curried import map as toolz_map, filter as toolz_filter, reduce as toolz_reduce

        toolz_map_func = toolz_map(lambda x: x * 2)
        toolz_filter_func = toolz_filter(lambda x: x % 2 == 0)
        toolz_reduce_func = toolz_reduce(lambda x, y: x + y)

        def toolz_memory_test():
            r = toolz_map_func(large_data)
            r = toolz_filter_func(r)
            return toolz_reduce_func(r)

        toolz_memory = measure_memory(toolz_memory_test, memory_iterations)
        print(f"toolz 组合操作: {toolz_memory:.2f} KB")

    print()

    # =========================================================================
    # 总结
    # =========================================================================
    print("=" * 70)
    print("性能测试完成")
    print("=" * 70)

    print("\n说明:")
    print("- 测试迭代次数: map/filter/reduce/compose/unique/groupby = 50,000")
    print("- 内存测试迭代次数: 1,000")
    print("- 测试数据规模: 1,000 - 10,000 元素")
    print("\n注意: vools.curried 增加了柯里化装饰器开销，")
    print("      但提供了更强大的类型注解和更灵活的函数组合能力。")


if __name__ == "__main__":
    run_performance_tests()
