# -*- coding: utf-8 -*-
"""回归测试：register_type 的校验顺序（BUG-498）。

修复前校验顺序颠倒（先查"必须成对提供"，再查"是否可调用"）：

    register_type(C, "C1", serialize=123)          # -> ValueError: deserialize
                                                   #    function is required for type C1
    register_type(C, "C2", deserialize="x")        # -> ValueError: serialize function
                                                   #    is required for type C2

两条都在**指错参数**：真正的病根是传入的回调不可调用，不是"缺另一个"。

修复后先校验已提供的回调可调用（带参数名），再检查成对提供；
`type_`/`name` 的既有校验与注册往返行为不变（唯一名字避免全局注册冲突）。
"""

import pytest

import vools.serialize as se


def make_cls(tag):
    """动态生成唯一类，避免全局注册表跨用例冲突。"""
    return type(f"Reg{tag}", (), {"__init__": lambda self, v=1: setattr(self, "v", v)})


class TestValidationOrder:
    def test_non_callable_serialize_without_deserialize(self):
        cls = make_cls("A1")
        with pytest.raises(TypeError) as ei:
            se.register_type(cls, "UT-A1", serialize=123)
        assert "serialize" in str(ei.value)

    def test_non_callable_deserialize_without_serialize(self):
        cls = make_cls("A2")
        with pytest.raises(TypeError) as ei:
            se.register_type(cls, "UT-A2", deserialize="x")
        assert "deserialize" in str(ei.value)

    def test_non_callable_serialize_with_deserialize(self):
        cls = make_cls("A3")
        with pytest.raises(TypeError) as ei:
            se.register_type(cls, "UT-A3", serialize=123, deserialize=lambda v: cls(v))
        assert "serialize" in str(ei.value)

    def test_missing_deserialize_points_at_deserialize(self):
        cls = make_cls("A4")
        with pytest.raises(ValueError) as ei:
            se.register_type(cls, "UT-A4", serialize=lambda c: c.v)
        assert "deserialize" in str(ei.value)

    def test_missing_serialize_points_at_serialize(self):
        cls = make_cls("A5")
        with pytest.raises(ValueError) as ei:
            se.register_type(cls, "UT-A5", deserialize=lambda v: cls(v))
        assert "serialize" in str(ei.value)


class TestExistingValidationUnchanged:
    def test_non_type(self):
        with pytest.raises(TypeError) as ei:
            se.register_type(123)
        assert "type_" in str(ei.value)

    def test_name_wrong_type(self):
        cls = make_cls("B1")
        with pytest.raises(TypeError) as ei:
            se.register_type(cls, name=123)
        assert "name" in str(ei.value)

    def test_name_empty(self):
        cls = make_cls("B2")
        with pytest.raises(ValueError):
            se.register_type(cls, "")


class TestRegistrationBehaviour:
    def test_roundtrip_with_handlers(self):
        cls = make_cls("C1")
        se.register_type(
            cls, "UT-C1",
            serialize=lambda c: c.v,
            deserialize=lambda v: cls(v),
        )
        # 注册类型走 JSON 后端（pickle 后端要求类本身可 pickle；动态类不可）
        back = se.loads(se.dumps(cls(7), backend="json"), backend="json")
        assert back.v == 7
        assert type(back) is cls

    def test_get_type_handler(self):
        cls = make_cls("D1")
        se.register_type(
            cls, "UT-D1",
            serialize=lambda c: c.v,
            deserialize=lambda v: cls(v),
        )
        name, handler = se.get_type_handler(cls(1))
        assert name == "UT-D1"
        assert callable(handler)

    def test_get_type_deserializer(self):
        cls = make_cls("E1")
        se.register_type(
            cls, "UT-E1",
            serialize=lambda c: c.v,
            deserialize=lambda v: cls(v),
        )
        assert callable(se.get_type_deserializer("UT-E1"))
        assert se.get_type_deserializer("UT-NOT-REGISTERED") is None

    def test_duplicate_name_rejected(self):
        cls1 = make_cls("F1")
        cls2 = make_cls("F2")
        se.register_type(cls1, "UT-DUP", serialize=lambda c: 1, deserialize=lambda v: cls1(v))
        with pytest.raises(ValueError):
            se.register_type(cls2, "UT-DUP", serialize=lambda c: 2, deserialize=lambda v: cls2(v))
