"""BUG-103: memorize.py 修复验证 — None 缓存 + 不可 pickle 参数"""
import time
from vools.cache.memorize import memorize, _MISS, TimedCache


def test_none_result_is_cached():
    """返回 None 的函数结果应被缓存（BUG-103 前每次调用都重算）"""
    call_count = [0]

    @memorize(duration=5)
    def get_none():
        call_count[0] += 1
        return None

    assert get_none() is None
    assert get_none() is None
    assert call_count[0] == 1, f"None 未被缓存，函数执行了 {call_count[0]} 次"


def test_unpicklable_args_no_crash():
    """不可 pickle 的参数不应导致装饰函数崩溃（BUG-103 前抛 TypeError）"""

    class Unpicklable:
        def __reduce__(self):
            raise TypeError("can't pickle")

    @memorize(duration=5)
    def h(x):
        return 'ok'

    assert h(Unpicklable()) == 'ok'


def test_normal_caching_still_works():
    """正常缓存语义不被破坏：同参数命中，不同参数重算"""
    call_count = [0]

    @memorize(duration=5)
    def double(x):
        call_count[0] += 1
        return x * 2

    assert double(3) == 6
    assert double(3) == 6
    assert call_count[0] == 1
    assert double(4) == 8
    assert call_count[0] == 2


def test_timed_cache_get_miss_sentinel():
    """TimedCache.get 未命中返回 _MISS 哨兵"""
    c = TimedCache(max_size=10)
    assert c.get('missing', 1.0) is _MISS


def test_timed_cache_get_none_value():
    """TimedCache 能缓存 None 值"""
    c = TimedCache(max_size=10)
    c.set('k', None)
    assert c.get('k', 1.0) is None
    assert c.get('k', 1.0) is not _MISS