"""测试range iterator创建和from_iterable订阅开销"""
import timeit
import vools.reactive as rx

# 测试1: 创建range iterator的开销
iter_creation = timeit.timeit('iter(range(10000))', number=1000)
print(f"创建iter(range(10000))耗时: {iter_creation / 1000 * 1000000:.2f}µs")

# 测试2: from_iterable(range(10000))直接订阅（无操作符）
from_iterable_direct = timeit.timeit(
    'rx.Observable.from_iterable(range(10000)).subscribe(on_next=lambda x: None)',
    setup='import vools.reactive as rx', number=100
)
print(f"from_iterable(range(10000)).subscribe()完整流程耗时: {from_iterable_direct / 100 * 1000000:.2f}µs")

# 测试3: from_iterable(range(0))订阅（空range）
from_iterable_empty = timeit.timeit(
    'rx.Observable.from_iterable(range(0)).subscribe(on_next=lambda x: None)',
    setup='import vools.reactive as rx', number=1000
)
print(f"from_iterable(range(0)).subscribe()耗时: {from_iterable_empty / 1000 * 1000000:.2f}µs")

# 测试4: from_iterable([])订阅（空列表）
from_iterable_empty_list = timeit.timeit(
    'rx.Observable.from_iterable([]).subscribe(on_next=lambda x: None)',
    setup='import vools.reactive as rx', number=1000
)
print(f"from_iterable([]).subscribe()耗时: {from_iterable_empty_list / 1000 * 1000000:.2f}µs")

# 测试5: 手动空Observable创建
manual_empty = timeit.timeit(
    '''
def subscribe(observer):
    observer.on_completed()
    return rx.Subscription(lambda: None)
rx.Observable(subscribe).subscribe(on_next=lambda x: None)
''',
    setup='import vools.reactive as rx', number=1000
)
print(f"手动空Observable.subscribe()耗时: {manual_empty / 1000 * 1000000:.2f}µs")

print("\n=== 性能瓶颈根源分析 ===")
print(f"iter(range(10000))创建: {iter_creation / 1000 * 1000000:.2f}µs")
print(f"from_iterable(range(10000))完整订阅: {from_iterable_direct / 100 * 1000000:.2f}µs")
print(f"差异说明: range iterator创建几乎为0，问题在subscribe函数本身")

print("\n建议: from_iterable subscribe函数优化 - 减少Subscription创建开销")
