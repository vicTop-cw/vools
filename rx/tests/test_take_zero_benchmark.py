"""直接测试take(0)的性能瓶颈"""
import timeit
import vools.reactive as rx

# 测试1: 直接创建tuple的时间
tuple_creation = timeit.timeit('tuple(range(10000))', number=100)
print(f"创建tuple(range(10000))耗时: {tuple_creation / 100 * 1000000:.2f}µs")

# 测试2: rx.of(*range(10000))的tuple创建 + Observable创建时间
of_creation = timeit.timeit('rx.of(*range(10000))', setup='import vools.reactive as rx', number=100)
print(f"rx.of(*range(10000))创建Observable耗时: {of_creation / 100 * 1000000:.2f}µs")

# 测试3: 直接使用from_iterable(range(10000))避免tuple展开
from_iterable_creation = timeit.timeit('rx.Observable.from_iterable(range(10000))', 
                                       setup='import vools.reactive as rx', number=100)
print(f"from_iterable(range(10000))创建Observable耗时: {from_iterable_creation / 100 * 1000000:.2f}µs")

# 测试4: from_iterable(range(10000)).pipe(take(0))的订阅时间
from_iterable_take_zero = timeit.timeit(
    'rx.Observable.from_iterable(range(10000)).pipe(rx.take(0)).subscribe(on_next=lambda x: None)',
    setup='import vools.reactive as rx', number=100
)
print(f"from_iterable(range(10000)).pipe(take(0))订阅耗时: {from_iterable_take_zero / 100 * 1000000:.2f}µs")

# 测试5: rx.of(*range(10000)).pipe(take(0))的完整时间
of_take_zero = timeit.timeit(
    'rx.of(*range(10000)).pipe(rx.take(0)).subscribe(on_next=lambda x: None)',
    setup='import vools.reactive as rx', number=100
)
print(f"rx.of(*range(10000)).pipe(take(0))订阅耗时: {of_take_zero / 100 * 1000000:.2f}µs")

print("\n=== 性能瓶颈分析 ===")
print(f"tuple创建开销: {tuple_creation / 100 * 1000000:.2f}µs")
print(f"rx.of完整流程开销: {of_creation / 100 * 1000000:.2f}µs")
print(f"from_iterable优化后订阅开销: {from_iterable_take_zero / 100 * 1000000:.2f}µs")
print(f"性能差异: {of_take_zero - from_iterable_take_zero / 100 * 1000000:.2f}µs")

print("\n建议: 使用Observable.from_iterable(range(n))代替rx.of(*range(n))以避免tuple创建开销")
