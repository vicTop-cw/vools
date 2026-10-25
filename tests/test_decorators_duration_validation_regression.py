# -*- coding: utf-8 -*-
"""回归测试：debounce/cache_with_ttl 的时间参数校验（BUG-473）。

BUG-373 只拦住了"裸用装饰器"（把函数当 wait/ttl 传），但**数值本身**仍零校验：

    debounce(wait=-1)          # 装饰期静默通过；Timer(-1) 立即触发，防抖语义被放大
    debounce(wait='x')         # 调用时才抛 threading.Timer 的类型错误
    cache_with_ttl(ttl=-1)     # 装饰期静默通过；每项立即过期（永不命中，静默错配置）
    cache_with_ttl(ttl='x')    # 调用时抛 "'>' not supported between 'float' and 'str'"

修复后：非数值 → TypeError；debounce 的 wait 允许 0（立即触发）但拒绝负值；
cache_with_ttl 的 ttl 必须 > 0。
"""

import time

import pytest

import vools.decorators as d


class TestDebounceValidation:
    @pytest.mark.parametrize("bad", ["x", None, [1], True])
    def test_non_numeric(self, bad):
        with pytest.raises(TypeError) as ei:
            d.debounce(wait=bad)
        assert "wait" in str(ei.value)

    def test_negative_rejected(self):
        with pytest.raises(ValueError) as ei:
            d.debounce(wait=-1)
        assert "wait" in str(ei.value)

    def test_zero_allowed(self):
        assert callable(d.debounce(wait=0))

    def test_behaviour_unchanged(self):
        calls = []

        @d.debounce(wait=0.05)
        def f(x):
            calls.append(x)

        assert f(7) is None        # 防抖：立即返回 None
        time.sleep(0.2)
        assert calls == [7]        # 定时器到点后执行


class TestCacheTtlValidation:
    @pytest.mark.parametrize("bad", ["x", None, [1], True])
    def test_non_numeric(self, bad):
        with pytest.raises(TypeError) as ei:
            d.cache_with_ttl(ttl=bad)
        assert "ttl" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1, -0.5])
    def test_non_positive_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            d.cache_with_ttl(ttl=bad)
        assert "ttl" in str(ei.value)

    def test_positive_allowed_and_caches(self):
        calls = []

        @d.cache_with_ttl(ttl=60)
        def f(x):
            calls.append(x)
            return x * 2

        assert f(2) == 4
        assert f(2) == 4
        assert calls == [2]        # 第二次命中缓存

    def test_distinct_args_cached_separately(self):
        calls = []

        @d.cache_with_ttl(ttl=60)
        def f(x):
            calls.append(x)
            return x * 2

        assert f(2) == 4
        assert f(3) == 6
        assert calls == [2, 3]


class TestBareDecoratorStillGuarded:
    """BUG-373 的裸用守卫保持。"""

    def test_debounce_bare(self):
        with pytest.raises(TypeError):
            d.debounce(lambda x: x)

    def test_cache_with_ttl_bare(self):
        with pytest.raises(TypeError):
            d.cache_with_ttl(lambda x: x)
