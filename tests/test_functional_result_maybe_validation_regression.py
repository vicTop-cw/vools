# -*- coding: utf-8 -*-
"""回归测试：Result 回调零校验 + Maybe/Result bind 透传裸值（BUG-357）。

## 1. Result 缺回调校验（与 Maybe 不一致）

    Success(2).map(None)      # 修复前 → TypeError: 'NoneType' object is not callable
    Success(2).bind(123)      # 修复前 → TypeError: 'int' object is not callable
    Failure("e").map_err(None)# 同上
    # 而 Maybe 早在 BUG-438 就有 "Maybe.map() 的回调必须可调用，收到 ..."

## 2. bind/flat_map 不校验返回类型（monad 契约）

    Some(1).flat_map(lambda x: x + 1)     # 修复前 → 2（裸 int 被原样透传！）
    Success(2).bind(lambda x: x * 2)      # 修复前 → 4（裸 int）
    # 下游再链式调用才 AttributeError，错误离病因很远

修复：Result 增加 _require_callable（map/map_err/bind/flat_map 全部使用）；
Maybe.bind / Result.bind 校验回调返回值为对应包装类型。
"""

import pytest

from vools.functional.maybe import Maybe, Nothing_, Some
from vools.functional.result import Failure, Result, Success


class TestResultCallbackValidation:
    @pytest.mark.parametrize("bad", [None, 123, "x"])
    def test_map(self, bad):
        with pytest.raises(TypeError) as ei:
            Success(2).map(bad)
        assert "Result.map()" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_bind(self, bad):
        with pytest.raises(TypeError) as ei:
            Success(2).bind(bad)
        assert "Result.bind()" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_flat_map(self, bad):
        with pytest.raises(TypeError) as ei:
            Success(2).flat_map(bad)
        assert "Result.bind()" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_map_err(self, bad):
        with pytest.raises(TypeError) as ei:
            Failure("e").map_err(bad)
        assert "Result.map_err()" in str(ei.value)


class TestResultBindReturnType:
    def test_bind_must_return_result(self):
        with pytest.raises(TypeError) as ei:
            Success(2).bind(lambda x: x * 2)
        assert "必须返回 Result 实例" in str(ei.value)

    def test_flat_map_must_return_result(self):
        with pytest.raises(TypeError):
            Success(2).flat_map(lambda x: x)

    def test_bind_valid(self):
        assert Success(2).bind(lambda x: Success(x * 2)) == Success(4)


class TestMaybeBindReturnType:
    def test_bind_must_return_maybe(self):
        with pytest.raises(TypeError) as ei:
            Some(1).bind(lambda x: x + 1)
        assert "必须返回 Maybe 实例" in str(ei.value)

    def test_flat_map_must_return_maybe(self):
        with pytest.raises(TypeError):
            Some(1).flat_map(lambda x: x + 1)

    def test_bind_valid(self):
        assert Some(1).bind(lambda x: Some(x + 1)) == Some(2)

    def test_nothing_short_circuits(self):
        # is_none 是 property（不是方法）
        assert Nothing_().bind(lambda x: Some(x)).is_none is True


class TestBehaviourUnchanged:
    def test_result_map(self):
        assert Success(2).map(str) == Success("2")

    def test_result_map_err(self):
        assert Failure("e").map_err(str) == Failure("e")

    def test_failure_short_circuits(self):
        assert Failure("e").bind(lambda x: Success(x)) == Failure("e")

    def test_maybe_map_on_none(self):
        assert Nothing_().map(lambda x: x).is_none is True

    def test_maybe_some_map(self):
        assert Some(1).map(str).get_or(None) == "1"

    def test_result_from_unsafe(self):
        # from_unsafe(fn) 立即调用 fn() 并包装结果（不返回函数）
        assert Result.from_unsafe(lambda: 2).get_or(0) == 2
        assert Result.from_unsafe(lambda: 1 / 0).is_failure is True
