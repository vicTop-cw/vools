# -*- coding: utf-8 -*-
"""回归测试：memoize 容量边界对齐 lru_cache 语义（BUG-215）。

原 `_memoize_impl` 在任何调用都执行 `len(cache) >= maxsize` 后对可能为空的
cache `next(iter(cache))`：
- maxsize=0/负数 → 首调在 func 执行后抛 StopIteration（副作用已发生、
  结果丢失）；而 lru_cache(maxsize=0) 是合法直通语义；
- maxsize=None → `len >= None` TypeError（lru_cache 无限缓存惯用值不可用）。

修复：None 无限缓存；<=0 直通不写；>0 保持 FIFO 驱逐（此时 cache 必非空）。
"""

import pytest

from vools.curried.composition import memoize


class TestMaxsizeZeroPassthrough:
    """maxsize=0/负数：直通不缓存、结果照常返回（BUG-215 ①）。"""

    def test_zero_passthrough_no_crash(self):
        calls = []

        @memoize(maxsize=0)
        def f(x):
            calls.append(x)
            return x * 2

        assert f(5) == 10
        assert f(5) == 10          # 原实现此处（及首调）已抛 StopIteration
        assert calls == [5, 5]     # 直通：每次都真执行

    def test_negative_passthrough(self):
        g = memoize(lambda x: x + 1, maxsize=-3)
        assert g(1) == 2


class TestMaxsizeNoneUnlimited:
    """maxsize=None：无限缓存（BUG-215 ②，对齐 lru_cache(None)）。"""

    def test_none_caches_everything(self):
        n = []

        @memoize(maxsize=None)
        def h(x):
            n.append(x)
            return x

        assert h(1) == 1
        assert h(1) == 1
        assert len(n) == 1
        assert len(h.cache) == 1

        for i in range(200):       # 超过默认 128 也不驱逐
            h(i)
        assert len(h.cache) == 200


class TestPositiveFifoUnchanged:
    """maxsize>0 正常缓存 + FIFO 驱逐语义保持（防修复过度）。"""

    def test_cache_hit(self):
        n = []

        @memoize(maxsize=4)
        def f(x):
            n.append(x)
            return x * 10

        assert f(1) == 10
        assert f(1) == 10
        assert len(n) == 1

    def test_fifo_evicts_oldest(self):
        n = []

        @memoize(maxsize=2)
        def k(x):
            n.append(x)
            return x * 10

        k(1); k(2)
        k(3)                    # 驱逐 1
        assert k(1) == 10       # 重新计算
        assert n == [1, 2, 3, 1]

    def test_cache_clear(self):
        @memoize
        def f(x):
            return x

        f(1)
        assert len(f.cache) == 1
        f.cache_clear()
        assert len(f.cache) == 0