"""
BUG-304 回归测试：memoize 对不可哈希参数（list/dict/set）的支持

原实现 cache key = (args, tuple(sorted(kwargs.items()))) 对
list/dict 等不可哈希参数抛 TypeError，memoize 无法用于常见场景。
修复后 try/except 降级：不可哈希时用 repr 做键。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.curried.core import memoize


class TestMemoizeUnhashable:
    """不可哈希参数"""

    def test_list_args(self):
        @memoize
        def concat(a, b):
            return a + b
        assert concat([1, 2], [3, 4]) == [1, 2, 3, 4]

    def test_dict_args(self):
        @memoize
        def merge(d1, d2):
            return {**d1, **d2}
        assert merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_set_args(self):
        @memoize
        def union(s1, s2):
            return s1 | s2
        assert union({1, 2}, {3}) == {1, 2, 3}

    def test_nested_unhashable(self):
        @memoize
        def get_len(items):
            return len(items)
        assert get_len([1, 2, 3]) == 3


class TestMemoizeCacheHit:
    """缓存命中验证"""

    def test_hashable_cache_hit(self):
        call_count = 0

        @memoize
        def count_calls(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        count_calls(5)
        count_calls(5)  # 应该命中缓存
        assert call_count == 1

    def test_unhashable_cache_hit(self):
        call_count = 0

        @memoize
        def count_calls_list(lst):
            nonlocal call_count
            call_count += 1
            return len(lst)

        count_calls_list([1, 2, 3])
        count_calls_list([1, 2, 3])  # repr 相同，应该命中
        assert call_count == 1

    def test_different_args_different_cache(self):
        @memoize
        def add(a, b):
            return a + b

        assert add(1, 2) == 3
        assert add(3, 4) == 7  # 不同参数，不同结果
