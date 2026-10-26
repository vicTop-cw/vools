# -*- coding: utf-8 -*-
"""审计锁定：create_fake 接受**任意对象**（含非可调用）是设计契约。

本轮一度把 `create_fake(123)/create_fake(None)` 判为"静默接受非可调用对象"并加了
TypeError 校验 —— **前提是错的**：既有 ``tests/test_oop_calltype.py::TestCreateFake::
test_none`` 明确锁定 ``create_fake(None)()`` 返回 ``NOT_CALLABLE_INSTANCE_ATTR``。

即 create_fake 是**类型探针工厂**（不是签名镜像工厂）：它复制目标的签名（拿不到就
空签名），调用时返回 ``get_callable_type(func)`` 的分类值，因此对任意对象（包括
不可调用对象）都必须可用——用于断言"这个对象会被识别成什么调用类型"。

本文件把该契约固化为回归，防止后续再被误"修复"。
"""

import inspect

import pytest

from vools.oop.calltype import CallableType, create_fake, get_callable_type


class TestCreateFakeIsTypeProbeFactory:
    @pytest.mark.parametrize("obj,expected", [
        (None, CallableType.NOT_CALLABLE_INSTANCE_ATTR),
        (123, CallableType.NOT_CALLABLE_INSTANCE_ATTR),
        (1.5, CallableType.NOT_CALLABLE_INSTANCE_ATTR),
    ])
    def test_non_callable_objects_produce_probe(self, obj, expected):
        wrapper = create_fake(obj)
        assert callable(wrapper)
        assert wrapper() == expected

    def test_function_probe(self):
        def f(x):
            return x

        assert create_fake(f)() == CallableType.CALLABLE_FUNCTION

    def test_class_probe(self):
        class C:
            pass

        assert create_fake(C)() == CallableType.CALLABLE_CLASS

    def test_probe_value_matches_get_callable_type(self):
        def f(x):
            return x

        assert create_fake(f)() == get_callable_type(f)


class TestCreateFakeSignatureUnchanged:
    def test_function_signature_preserved(self):
        def target(a, b=1, *, c=None):
            return a + b

        wrapper = create_fake(target)
        assert list(inspect.signature(wrapper).parameters) == ["a", "b", "c"]
        assert wrapper.__name__ == "target"

    def test_class_uses_init_signature(self):
        class C:
            def __init__(self, a, b=2):
                pass

        wrapper = create_fake(C)
        assert list(inspect.signature(wrapper).parameters) == ["self", "a", "b"]

    def test_uninspectable_falls_back_to_empty_signature(self):
        wrapper = create_fake(None)
        assert list(inspect.signature(wrapper).parameters) == []
