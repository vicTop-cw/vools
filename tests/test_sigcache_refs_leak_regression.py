# -*- coding: utf-8 -*-
"""回归测试：签名缓存弱引用表内存泄漏（BUG-275）。

sigcache 用两个全局表：_SIG_CACHE（id(func)->Signature，LRU 上限 4096）与
_SIG_REFS（id(func)->weakref，BUG-113 的 id 复用防护）。原实现：
① LRU 淘汰只 `_SIG_CACHE.popitem`，从不清理 `_SIG_REFS[evicted]` → 弱引用表
   随曾缓存过的函数数无界增长（实测 5000 个函数后 _SIG_REFS=5000 而缓存
   =4096）；
② 函数被 GC 后 dead ref 永久残留（无 weakref 回调清理）。

修复：淘汰时同步 `_SIG_REFS.pop(evicted_key)`；`_remember_ref` 给 weakref
挂回调，函数回收时惰性清理两表中的对应条目（回调晚到最多一次缓存 miss）。
"""

import gc

import pytest

import vools.cache.sigcache as sc
from vools.cache.sigcache import cache_info, clear_cache, get_signature, remove_signature


@pytest.fixture(autouse=True)
def _clean():
    clear_cache()
    yield
    clear_cache()


class TestLruEvictionCleansRefs:
    def test_refs_bounded_after_eviction(self, monkeypatch):
        monkeypatch.setattr(sc, '_MAX_CACHE_SIZE', 8)
        funcs = []
        for i in range(30):
            def f(x, _i=i):
                pass
            funcs.append(f)
            get_signature(f)
        assert len(sc._SIG_CACHE) <= 8
        # 修复前：_SIG_REFS 会保持 30
        assert len(sc._SIG_REFS) <= 8

    def test_cache_and_refs_same_size(self, monkeypatch):
        monkeypatch.setattr(sc, '_MAX_CACHE_SIZE', 5)
        funcs = []
        for i in range(12):
            def f(y, _i=i):
                pass
            funcs.append(f)
            get_signature(f)
        assert len(sc._SIG_REFS) == len(sc._SIG_CACHE)


class TestGcCleansBothTables:
    def test_collected_function_cleaned(self):
        def g(x):
            pass
        get_signature(g)
        assert len(sc._SIG_CACHE) == 1 and len(sc._SIG_REFS) == 1
        del g
        gc.collect()
        # 修复前：两个表都残留 1 条
        assert len(sc._SIG_CACHE) == 0
        assert len(sc._SIG_REFS) == 0


class TestBehaviorUnchanged:
    def test_hit_returns_same_signature(self):
        def h(a, b=1):
            pass
        assert get_signature(h) is get_signature(h)

    def test_cache_info(self):
        def k():
            pass
        get_signature(k)
        info = cache_info()
        assert info['size'] == 1
        assert info['maxsize'] == sc._MAX_CACHE_SIZE

    def test_remove_signature(self):
        def m():
            pass
        get_signature(m)
        assert remove_signature(m) is True
        assert remove_signature(m) is False
        assert len(sc._SIG_REFS) == 0

    def test_clear_cache(self):
        def n():
            pass
        get_signature(n)
        clear_cache()
        assert len(sc._SIG_CACHE) == 0 and len(sc._SIG_REFS) == 0