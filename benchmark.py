"""
benchmark.py - Nim vs Python 性能基准测试
"""
import time
import statistics


def bench(name, fn, *args, n_iter=1000):
    """运行 n_iter 次取中位数"""
    times = []
    for _ in range(5):  # 5 轮取最佳
        t0 = time.perf_counter()
        for _ in range(n_iter):
            fn(*args)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    best = min(times)
    print(f'  {name:40s}  best={best*1000:8.3f}ms  ({n_iter} iters)')
    return best


def main():
    # 测试数据
    big_int = list(range(10000))
    big_str = [f'item_{i}' for i in range(1000)]
    big_bytes = b'Hello, world! ' * 1000

    print('=' * 70)
    print('Nim vs Python 性能基准')
    print('=' * 70)

    # ========== Crypto ==========
    print('\n--- Crypto (MD5/SHA) ---')
    from vools._nim_crypto import md5 as nim_md5, sha1 as nim_sha1, sha256 as nim_sha256
    import hashlib

    def py_md5(b): return hashlib.md5(b).hexdigest()
    def py_sha1(b): return hashlib.sha1(b).hexdigest()
    def py_sha256(b): return hashlib.sha256(b).hexdigest()

    bench('Python hashlib.md5', py_md5, big_bytes, n_iter=1000)
    bench('Nim md5', nim_md5, big_bytes, n_iter=1000)
    bench('Python hashlib.sha1', py_sha1, big_bytes, n_iter=1000)
    bench('Nim sha1', nim_sha1, big_bytes, n_iter=1000)
    bench('Python hashlib.sha256', py_sha256, big_bytes, n_iter=1000)
    bench('Nim sha256', nim_sha256, big_bytes, n_iter=1000)

    # ========== Seq ==========
    print('\n--- Seq Operations ---')
    from vools._nim_seq import (seq_map_int, seq_filter_int, seq_reduce_sum_int,
                                  seq_sort_int, seq_unique_int)

    bench('Python list * 2', lambda x: [v * 2 for v in x], big_int, n_iter=100)
    bench('Nim seq_map_int * 2', seq_map_int, big_int, 2, n_iter=100)
    bench('Python filter > 5000', lambda x: [v for v in x if v > 5000], big_int, n_iter=100)
    bench('Nim seq_filter_int > 5000', seq_filter_int, big_int, 5000, n_iter=100)
    bench('Python sum', sum, big_int, n_iter=1000)
    bench('Nim seq_reduce_sum_int', seq_reduce_sum_int, big_int, n_iter=1000)
    bench('Python sorted', lambda x: sorted(x), big_int, n_iter=100)
    bench('Nim seq_sort_int asc', seq_sort_int, big_int, 0, n_iter=100)

    # ========== Curried (统计) ==========
    print('\n--- Math/Stats ---')
    from vools._nim_curried import (sum_int as nim_sum, mean_int as nim_mean,
                                      stddev_int as nim_stddev, distinct_int as nim_distinct,
                                      l2norm_int as nim_l2norm, dot_int as nim_dot)
    import math

    def py_mean(x): return sum(x) / len(x) if x else 0.0
    def py_stddev(x):
        if not x: return 0.0
        m = sum(x) / len(x)
        return math.sqrt(sum((v - m) ** 2 for v in x) / len(x))
    def py_distinct(x):
        seen = set(); r = []
        for v in x:
            if v not in seen: seen.add(v); r.append(v)
        return r
    def py_l2norm(x): return math.sqrt(sum(v * v for v in x))
    def py_dot(a, b): return sum(x * y for x, y in zip(a, b))

    bench('Python sum', sum, big_int, n_iter=1000)
    bench('Nim sum_int', nim_sum, big_int, n_iter=1000)
    bench('Python mean', py_mean, big_int, n_iter=1000)
    bench('Nim mean_int', nim_mean, big_int, n_iter=1000)
    bench('Python stddev', py_stddev, big_int, n_iter=200)
    bench('Nim stddev_int', nim_stddev, big_int, n_iter=200)
    bench('Python l2norm', py_l2norm, big_int, n_iter=200)
    bench('Nim l2norm_int', nim_l2norm, big_int, n_iter=200)
    bench('Python dot product', py_dot, big_int, big_int, n_iter=200)
    bench('Nim dot_int', nim_dot, big_int, big_int, n_iter=200)

    # ========== Datetime ==========
    print('\n--- Datetime ---')
    from vools._nim_datetime import (range_days as nim_range, days_between as nim_days_between,
                                        is_leap_year as nim_leap)
    from datetime import date, timedelta

    def py_range(start_y, start_m, start_d, count):
        return [(date(start_y, start_m, start_d) + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(count)]
    def py_days_between(y1, m1, d1, y2, m2, d2):
        return (date(y2, m2, d2) - date(y1, m1, d1)).days
    def py_leap(y): return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)

    bench('Python range 365 days', py_range, 2024, 1, 1, 365, n_iter=20)
    bench('Nim range 365 days', nim_range, 2024, 1, 1, 365, n_iter=20)
    bench('Python days_between', py_days_between, 2020, 1, 1, 2024, 12, 31, n_iter=10000)
    bench('Nim days_between', nim_days_between, 2020, 1, 1, 2024, 12, 31, n_iter=10000)
    bench('Python is_leap_year', py_leap, 2024, n_iter=10000)
    bench('Nim is_leap_year', nim_leap, 2024, n_iter=10000)

    print('\n' + '=' * 70)
    print('基准测试完成')
    print('=' * 70)


if __name__ == '__main__':
    main()
