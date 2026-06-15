"""
签名缓存基准测试 —— 对比 inspect.signature() 直接调用 vs LRU 缓存

测试场景:
  1. 简单函数（def add(a, b=0) -> int）
  2. 复杂函数（多参数 + 可变参数 + 关键字参数）
  3. 类方法（含 self/cls）
  4. 内置函数（str.format / dict.get）
  5. 重复调用同一函数（模拟 curry 场景）
  6. 多线程并发调用

结论预判:
  对于 curry / overload / dispatch 等热路径，缓存在 10 次重复调用后收益显著；
  单次调用场景缓存优势不大（dict 查表开销约 50ns vs inspect 约 5-20μs）。
"""
import inspect
import time
import functools
import sys
import threading
from typing import Callable, Any

# ── 被测函数 ──────────────────────────────────────────────

def simple_func(a: int, b: int = 0) -> int:
    return a + b

def complex_func(
    a: int,
    b: str,
    *args: float,
    c: bool = True,
    d: list = None,
    **kwargs: Any,
) -> str:
    return str(a) + b

class SampleClass:
    def instance_method(self, x: float, y: float = 0.0) -> float:
        return x + y

    @classmethod
    def class_method(cls, items: list) -> int:
        return len(items)

    @staticmethod
    def static_method(a: str, b: str = "") -> str:
        return a + b

# ── 缓存实现 ──────────────────────────────────────────────

_SIG_CACHE: dict = {}

def cached_signature(func: Callable) -> inspect.Signature:
    """带缓存的 signature 获取。"""
    key = id(func)
    try:
        return _SIG_CACHE[key]
    except KeyError:
        sig = inspect.signature(func)
        _SIG_CACHE[key] = sig
        return sig

def clear_sig_cache():
    _SIG_CACHE.clear()

# ── 基准测试 ──────────────────────────────────────────────

def benchmark(
    name: str,
    func: Callable,
    n: int = 10000,
    use_cache: bool = False,
    warm: bool = False,
) -> float:
    """运行基准测试，返回总耗时（秒）。"""
    getter = cached_signature if use_cache else inspect.signature

    # warm up
    if warm:
        for _ in range(100):
            getter(func)

    # cold run
    start = time.perf_counter()
    for _ in range(n):
        getter(func)
    elapsed = time.perf_counter() - start
    return elapsed


def run_single_scenario():
    """场景 1-4: 单线程单次/重复调用"""
    scenarios = [
        ("simple_func", simple_func),
        ("complex_func", complex_func),
        ("instance_method", SampleClass.instance_method),
        ("class_method", SampleClass.class_method),
        ("static_method", SampleClass.static_method),
        ("str.format", str.format),
        ("dict.get", dict.get),
    ]

    print(f"{'场景':>20s} | {'次数':>6s} | {'直接(μs)':>10s} | {'缓存(μs)':>10s} | {'加速比':>8s}")
    print("-" * 62)

    for name, fn in scenarios:
        for n in (1, 10, 1000, 100000):
            clear_sig_cache()
            t_direct = benchmark(name, fn, n, use_cache=False)
            clear_sig_cache()
            t_cached = benchmark(name, fn, n, use_cache=True)

            per_direct = t_direct / n * 1_000_000
            per_cached = t_cached / n * 1_000_000
            speedup = per_direct / per_cached if per_cached > 0 else float("inf")

            if n <= 10:
                print(f"{name:>20s} | {n:>6d} | {per_direct:>8.2f}  | {per_cached:>8.2f}  | {speedup:>6.1f}x")
            else:
                print(f"{name:>20s} | {n:>6d} | {per_direct:>8.2f}  | {per_cached:>8.2f}  | {speedup:>6.1f}x")


def run_repeated_scenario():
    """场景 5: 模拟 curry 场景——同一个函数重复调用 signature 多次"""
    print("\n═══ 场景 5: 重复调用同一函数（模拟 curry 热路径）═══\n")

    repeats = [2, 5, 10, 50, 100]
    test_func = complex_func

    print(f"{'重复次数':>8s} | {'直接(μs)':>10s} | {'缓存(μs)':>10s} | {'节省(μs)':>10s}")
    print("-" * 46)

    for r in repeats:
        clear_sig_cache()
        t_direct = benchmark("complex", test_func, n=r, use_cache=False)
        clear_sig_cache()
        t_cached = benchmark("complex", test_func, n=r, use_cache=True)

        d = t_direct / r * 1_000_000
        c = t_cached / r * 1_000_000
        saved = (t_direct - t_cached) * 1_000_000
        print(f"{r:>8d} | {d:>8.2f}  | {c:>8.2f}  | {saved:>8.2f}")


def run_concurrent_scenario():
    """场景 6: 多线程并发调用"""
    print("\n═══ 场景 6: 多线程并发（8 线程 × 10000 次）═══\n")

    funcs = [simple_func, complex_func, SampleClass.instance_method, str.format]

    for fn in funcs:
        clear_sig_cache()
        n_per_thread = 10000
        n_threads = 8
        barrier = threading.Barrier(n_threads)

        def worker(getter, fn, results, idx):
            barrier.wait()
            start = time.perf_counter()
            for _ in range(n_per_thread):
                getter(fn)
            results[idx] = time.perf_counter() - start

        for use_cache, label in ((False, "直接"), (True, "缓存")):
            clear_sig_cache()
            getter = cached_signature if use_cache else inspect.signature
            results = [0.0] * n_threads
            threads = [
                threading.Thread(target=worker, args=(getter, fn, results, i))
                for i in range(n_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            total = sum(results)
            per_call = total / (n_per_thread * n_threads) * 1_000_000
            print(f"  {fn.__name__:>20s} | {label} | {per_call:>7.2f} μs/次 | 合计 {total:.3f}s")


def run_memory_scenario():
    """分析缓存内存占用"""
    print("\n═══ 场景 7: 缓存内存分析 ═══\n")

    # 模拟注册大量函数
    funcs = []
    for i in range(1000):
        def make_f(i):
            def f(a=i, b=0):
                return a + b
            f.__name__ = f"f_{i}"
            return f
        funcs.append(make_f(i))

    clear_sig_cache()
    start = time.perf_counter()
    for f in funcs:
        cached_signature(f)
    elapsed = time.perf_counter() - start

    # 大约估算
    import sys as _sys
    total_size = sum(_sys.getsizeof(v) for v in _SIG_CACHE.values())
    num_entries = len(_SIG_CACHE)
    avg_size = total_size / num_entries if num_entries else 0

    print(f"  注册函数数: {num_entries}")
    print(f"  总内存占用: ~{total_size / 1024:.1f} KB")
    print(f"  平均每项:  ~{avg_size:.0f} bytes")
    print(f"  构建耗时:  {elapsed * 1000:.1f} ms")


# ── 主程序 ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 62)
    print("  inspect.signature() 缓存基准测试")
    print("  Python", sys.version)
    print("=" * 62)

    run_single_scenario()
    run_repeated_scenario()
    run_concurrent_scenario()
    run_memory_scenario()

    print("\n" + "=" * 62)
    print("  结论分析见 tests/signature_cache_analysis.md")
    print("=" * 62)
