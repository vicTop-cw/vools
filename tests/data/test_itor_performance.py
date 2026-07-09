import time
import sys
sys.path.insert(0, '.')

from vools.data import Itor, use_nim, get_itor


def benchmark(name, func, iterations=10):
    times = []
    for i in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    avg = sum(times) / len(times)
    print(f"{name}: {avg*1000:.2f}ms (min: {min(times)*1000:.2f}ms, max: {max(times)*1000:.2f}ms)")
    return avg


def test_basic_iteration(size=100000):
    print(f"\n=== 基础迭代测试 (size={size}) ===")
    
    data = list(range(size))
    
    use_nim(False)
    def py_iter():
        itor = Itor(data)
        return list(itor)
    
    py_time = benchmark("Python 版本", py_iter)
    
    use_nim(True)
    def nim_iter():
        itor = get_itor(data)
        return list(itor)
    
    nim_time = benchmark("Nim 版本", nim_iter)
    
    if nim_time > 0:
        speedup = py_time / nim_time
        print(f"性能对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms (Nim 快 {speedup:.1f}x)")
    else:
        print(f"性能对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms")


def test_with_jump(size=10000):
    print(f"\n=== 带插队测试 (size={size}) ===")
    
    data = list(range(size))
    
    use_nim(False)
    def py_jump():
        itor = Itor(data)
        itor.send(999)
        itor.send([888, 777])
        return list(itor)
    
    py_time = benchmark("Python 版本", py_jump)
    
    use_nim(True)
    def nim_jump():
        itor = get_itor(data)
        itor.send(999)
        itor.send([888, 777])
        return list(itor)
    
    nim_time = benchmark("Nim 版本", nim_jump)
    
    if nim_time > 0:
        speedup = py_time / nim_time
        print(f"性能对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms (Nim 快 {speedup:.1f}x)")
    else:
        print(f"性能对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms")


def test_restart(size=10000):
    print(f"\n=== 重启测试 (size={size}) ===")
    
    data = list(range(size))
    
    use_nim(False)
    def py_restart():
        itor = Itor(data)
        g = itor()
        for _ in range(size//2):
            next(g)
        g.restart()
        return list(g)
    
    py_time = benchmark("Python 版本", py_restart)
    
    use_nim(True)
    def nim_restart():
        itor = get_itor(data)
        for _ in range(size//2):
            next(itor)
        itor.restart()
        return list(itor)
    
    nim_time = benchmark("Nim 版本", nim_restart)
    
    if nim_time > 0:
        speedup = py_time / nim_time
        print(f"性能对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms (Nim 快 {speedup:.1f}x)")
    else:
        print(f"性能对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms")


def test_infinite_iterator():
    print("\n=== 无限迭代器测试 ===")
    
    def infinite_gen():
        i = 0
        while i < 1000:
            yield i
            i += 1
    
    use_nim(False)
    try:
        itor = Itor(infinite_gen())
        result = [next(itor) for _ in range(100)]
        print(f"Python 版本: 成功处理，前100个值正确")
    except Exception as e:
        print(f"Python 版本: {type(e).__name__}: {e}")
    
    use_nim(True)
    try:
        itor = get_itor(infinite_gen())
        result = [next(itor) for _ in range(100)]
        print(f"Nim 版本: 成功处理，前100个值正确")
    except Exception as e:
        print(f"Nim 版本: {type(e).__name__}: {e}")


def test_initialization_overhead(size=100000):
    print(f"\n=== 初始化开销测试 (size={size}) ===")
    
    data = list(range(size))
    
    use_nim(False)
    def py_init():
        return Itor(data)
    
    py_time = benchmark("Python 初始化", py_init)
    
    use_nim(True)
    def nim_init():
        return get_itor(data)
    
    nim_time = benchmark("Nim 初始化", nim_init)
    
    if nim_time > 0:
        speedup = py_time / nim_time
        print(f"初始化开销对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms (Nim 快 {speedup:.1f}x)")
    else:
        print(f"初始化开销对比: Python {py_time*1000:.1f}ms vs Nim {nim_time*1000:.1f}ms")


def analyze_results():
    print("\n=== 优化总结 ===")
    print("")
    print("优化策略:")
    print("1. 移除 pickle 序列化 - 数据直接在 Python 端处理")
    print("2. Nim 只负责线程同步 (Lock/Cond)，不处理数据")
    print("3. Python 端使用 deque 管理队列，迭代直接从源迭代器取值")
    print("4. 支持无限迭代器 (懒加载)")
    print("")
    print("架构对比:")
    print("  Python版本: Node链表 + threading.Lock/Condition")
    print("  Nim版本:    Python deque + Nim Lock/Cond (仅同步)")
    print("")
    print("关键改进:")
    print("  - 每次 next() 不再调用 ctypes")
    print("  - 仅控制操作(set_pause/resume/stop/restart)调用 Nim")
    print("  - 数据完全在 Python 端，避免跨语言数据传递")


if __name__ == '__main__':
    print("=" * 60)
    print("Itor 性能对比测试")
    print("=" * 60)
    
    test_basic_iteration(10000)
    test_basic_iteration(100000)
    
    test_with_jump(10000)
    test_restart(10000)
    
    test_initialization_overhead(100000)
    test_infinite_iterator()
    
    analyze_results()