# -*- coding: utf-8 -*-
"""回归测试：serialize 三个装饰器的 backend 参数校验（BUG-354）。

修复前：

    serializable(123)          # 静默返回装饰器（backend=123）
    serialize_method(123)      # 同上
    deserialize_method(123)    # 同上
    # 真正报错发生在**每次调用**：Serializer(backend=123) → "Unknown backend: 123"
    # —— 错误离装饰点很远，而且每调用一次才暴露一次

修复：工厂期校验 backend 必须 str 或 None（裸装饰路径传入的可调用对象由现有
BUG-371 分支先行处理）；错误信息列出可用后端。

合法路径不变：@serializable(backend='pickle') 的 serialize/deserialize、
@serialize_method(backend='json')、@deserialize_method(backend='json')、
裸 @serialize_method、backend=None 走全局默认。
"""

import pytest

import vools.serialize as sr
from vools.serialize.decorators import deserialize_method, serializable, serialize_method


class TestBackendValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, ["json"], {"b": 1}])
    def test_serializable(self, bad):
        with pytest.raises(TypeError) as ei:
            serializable(bad)
        assert "backend" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, 1.5])
    def test_serialize_method(self, bad):
        with pytest.raises(TypeError) as ei:
            serialize_method(bad)
        assert "backend" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, 1.5])
    def test_deserialize_method(self, bad):
        with pytest.raises(TypeError) as ei:
            deserialize_method(bad)
        assert "backend" in str(ei.value)


# 注意：pickle 需要模块级可寻址的类（函数内定义的本地类无法 pickle），
# 因此可 pickle 的测试类放在模块层。
@serializable(backend="pickle")
class PicklablePoint:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class TestBehaviourUnchanged:
    def test_serializable_pickle_roundtrip(self):
        restored = PicklablePoint.deserialize(PicklablePoint.serialize(PicklablePoint(1, 2)))
        assert (restored.x, restored.y) == (1, 2)

    def test_serializable_bare(self):
        class Plain:
            def __init__(self, v):
                self.v = v

        decorated = serializable(Plain)
        assert decorated is Plain
        assert hasattr(Plain, "serialize") and hasattr(Plain, "deserialize")

    def test_serializable_none_backend_uses_default(self):
        assert callable(serializable(None))

    def test_serialize_method_json(self):
        class Service:
            @serialize_method(backend="json")
            def state(self):
                return {"status": "ok"}

        raw = Service().state()
        assert isinstance(raw, bytes)
        assert sr.loads(raw, "json") == {"status": "ok"}

    def test_deserialize_method_json(self):
        class Service:
            @deserialize_method(backend="json")
            def load(self, raw):
                return raw

        assert Service().load(b'{"status": "ok"}') == {"status": "ok"}

    def test_bare_serialize_method(self):
        def method(self):
            return 1

        wrapped = serialize_method(method)
        assert callable(wrapped)
        assert wrapped.__name__ == "method"
