# -*- coding: utf-8 -*-
"""回归测试：Mixer._get_cached_attr 不得用类级 lru 缓存实例方法（BUG-226）。

原实现 `@lru_cache(maxsize=256)` 装饰实例方法——缓存键含 self，lru 对
self 强引用：调用过一次后实例连同混合组件永不回收（实测 del+gc 后弱引用
仍活）；且与实例级 `_attr_cache`（__getattr__ 写入、remove_extra_code
联动失效）双层错位，lru 层不感知属性变更必返回 stale 值。

修复：删除 @lru_cache，委托 __getattr__ 走原生实例级缓存，双层合一。
"""

import gc
import weakref

from vools.oop.mixer import Mixer


class _A:
    x = 1

    def go(self):
        return "A.go"


class _B:
    x = 2


class TestNoInstanceLeak:
    """BUG-226 核心：调用一次后实例仍可被回收。"""

    def test_instance_gc_after_use(self):
        m = Mixer(_A(), _B())
        wr = weakref.ref(m)
        assert m._get_cached_attr('x') == 1   # 调用一次（修复后 lru 强引用 self）
        del m
        gc.collect()
        assert wr() is None                   # 实例已回收

    def test_many_instances_not_retained(self):
        refs = []
        for _ in range(20):
            m = Mixer(_A())
            m._get_cached_attr('x')
            refs.append(weakref.ref(m))
            del m
        gc.collect()
        alive = sum(1 for r in refs if r() is not None)
        assert alive == 0                     # 20 个实例无一滞留


class TestCachingBehaviorPreserved:
    """委托 __getattr__ 后实例级缓存语义保持。"""

    def test_value_correct(self):
        m = Mixer(_A(), _B())
        assert m._get_cached_attr('x') == 1
        assert m._get_cached_attr('go')() == "A.go"

    def test_instance_level_cache_populated(self):
        m = Mixer(_A())
        m._get_cached_attr('go')
        assert 'go' in m._attr_cache          # 走实例级缓存而非类级 lru
        del m                                 # _attr_cache 随实例走，无跨实例残留

    def test_remove_extra_code_revalidates(self):
        class C:
            def hi(self):
                return "plain"

        m = Mixer(C())
        first = m._get_cached_attr('hi')
        m.remove_extra_code('hi')             # 清实例缓存（原 lru 层不感知）
        second = m._get_cached_attr('hi')
        assert second() == first() == "plain"  # 重解析正确（修复前若属性有变必 stale）