# -*- coding: utf-8 -*-
"""回归测试：Maybe 回调参数校验（BUG-438）。

修复前 ``map/filter/bind/flat_map/or_else/unwrap_or_else/map_or/if_some/
if_none`` 的回调零校验：

    some(1).filter('x')    # TypeError: 'str' object is not callable
                           # （看不出是回调参数错误）
    nothing().filter('x')  # **静默返回 Nothing**（回调不会被调用，非法回调
                           # 被悄悄接受，调用方以为"过滤成功"）
    some(1).or_else(123)   # 静默返回 Some(1)（回调未被调用）

修复后入口即抛带方法名的 TypeError；合法回调（含 Nothing 路径）行为不变。
"""

import pytest

from vools.functional.maybe import Maybe, nothing, optional, some


class TestCallbackValidation:
    @pytest.mark.parametrize("method,call", [
        ("map", lambda m: m.map("x")),
        ("filter", lambda m: m.filter("x")),
        ("bind", lambda m: m.bind(123)),
        ("flat_map", lambda m: m.flat_map(123)),
        ("or_else", lambda m: m.or_else(123)),
        ("unwrap_or_else", lambda m: m.unwrap_or_else(123)),
        ("map_or", lambda m: m.map_or(123, 0)),
        ("if_some", lambda m: m.if_some(123)),
        ("if_none", lambda m: m.if_none(123)),
    ])
    @pytest.mark.parametrize("maybe", [some(1), nothing()])
    def test_non_callable(self, method, call, maybe):
        with pytest.raises(TypeError) as ei:
            call(maybe)
        assert method in str(ei.value)


class TestNormalBehaviour:
    def test_map(self):
        assert some(1).map(lambda x: x * 2) == some(2)

    def test_filter_keeps(self):
        assert some(1).filter(lambda x: x > 0) == some(1)

    def test_filter_drops(self):
        assert some(1).filter(lambda x: x > 5) == nothing()

    def test_filter_on_nothing(self):
        assert nothing().filter(lambda x: True) == nothing()

    def test_bind(self):
        assert some(1).bind(lambda x: some(x + 1)) == some(2)
        assert nothing().bind(lambda x: some(x + 1)) == nothing()

    def test_flat_map(self):
        assert some(1).flat_map(lambda x: some(x + 1)) == some(2)

    def test_or_else(self):
        assert nothing().or_else(lambda: some(9)) == some(9)
        assert some(1).or_else(lambda: some(9)) == some(1)

    def test_unwrap_or_else(self):
        assert nothing().unwrap_or_else(lambda: 0) == 0
        assert some(1).unwrap_or_else(lambda: 0) == 1

    def test_map_or(self):
        assert some(1).map_or(lambda x: x * 2, 0) == 2
        assert nothing().map_or(lambda x: x * 2, 0) == 0

    def test_if_some_if_none(self):
        calls = []
        some(1).if_some(lambda x: calls.append(("some", x)))
        nothing().if_none(lambda: calls.append(("none",)))
        assert calls == [("some", 1), ("none",)]

    def test_from_optional(self):
        assert Maybe.from_optional(None) == nothing()
        assert Maybe.from_optional(1) == some(1)

    def test_optional_and_maybe_map(self):
        assert optional(None).is_none is True
        assert optional(1).is_none is False
