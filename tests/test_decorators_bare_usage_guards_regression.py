# -*- coding: utf-8 -*-
"""回归测试：参数化装饰器裸用时的即时清晰报错（BUG-373）。

`@throttle` / `@debounce` / `@with_timeout` / `@cache_with_ttl` / `@deprecated`
都需要显式参数。裸用（漏写括号）时，被装饰的函数会落到**配置参数**上，
返回的装饰器替换掉原函数，直到真正调用才抛：

    TypeError: throttle.<locals>.decorator() missing 1 required positional argument

错误信息不提示写错位置（既没说是装饰器用法问题，也没说需要什么参数），
与 BUG-371（serialize 装饰器吞对象）同族。

修复：装饰期检测到配置参数位置上收到**可调用对象**（且不是 int/float/str）
时，立即抛 TypeError 并给出正确写法与收到的对象名；带参用法行为不变。
"""

import time
import warnings

import pytest

from vools.decorators import (
    cache_with_ttl,
    debounce,
    deprecated,
    throttle,
    with_timeout,
)


def _dummy():
    return 'ok'


class TestBareUsageRejectedImmediately:
    @pytest.mark.parametrize('deco,expected_hint', [
        (throttle, '@throttle(interval='),
        (debounce, '@debounce(wait='),
        (with_timeout, '@with_timeout(timeout='),
        (cache_with_ttl, '@cache_with_ttl(ttl='),
        (deprecated, '@deprecated'),
    ])
    def test_bare_raises_with_hint(self, deco, expected_hint):
        # 修复前：装饰期不报错，调用时才抛 "decorator() missing 1 required positional argument"
        with pytest.raises(TypeError) as ei:
            deco(_dummy)
        msg = str(ei.value)
        assert expected_hint in msg
        assert '裸用' in msg
        assert '_dummy' in msg  # 收到的对象名，便于定位


class TestNormalUsageUnchanged:
    def test_throttle(self):
        @throttle(interval=0.05)
        def f():
            return 'x'

        assert f() == 'x'
        # 间隔内第二次被节流
        assert f() is None

    def test_debounce(self):
        # debounce 语义：定时器延迟执行、调用恒返回 None，只有最后一次生效
        calls = []

        @debounce(wait=0.05)
        def f():
            calls.append(1)
            return 'y'

        assert f() is None
        assert f() is None
        time.sleep(0.15)
        assert len(calls) == 1

    def test_with_timeout(self):
        @with_timeout(timeout=1)
        def f():
            return 'z'

        assert f() == 'z'

    def test_cache_with_ttl(self):
        calls = []

        @cache_with_ttl(ttl=10)
        def f():
            calls.append(1)
            return 'c'

        assert f() == 'c'
        assert f() == 'c'
        assert len(calls) == 1

    def test_deprecated_without_reason(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')

            @deprecated()
            def f():
                return 'd'

            assert f() == 'd'
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_deprecated_with_reason(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')

            @deprecated(reason='use new_api')
            def f():
                return 'd'

            assert f() == 'd'
        assert any('use new_api' in str(w.message) for w in caught)