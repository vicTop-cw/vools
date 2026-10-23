# -*- coding: utf-8 -*-
"""回归测试：serialize 装饰器的裸用法与反序列化告警（BUG-371/372）。

【BUG-371】三个装饰器只支持**带括号**写法。写成裸装饰时，被装饰对象被当作
`backend` 参数吞掉，装饰器函数替换掉原名字，直到实际使用才炸：

    @serializable
    class Bare: ...
    Bare('abc')     # AttributeError: 'str' object has no attribute 'serialize'
    # （类已变成 serializable(None) 返回的 decorator 函数）

修复：`serializable` 检测到参数是类、`serialize_method`/`deserialize_method`
检测到参数是可调用对象时，按裸装饰处理；带括号写法行为不变。

【BUG-372】`deserialize` / `deserialize_method` 在字节反序列化失败时**静默
回退**为原始 bytes（例如默认 json 后端收到 pickle 字节），调用方毫无提示。
修复：保留回退语义（参数可能只是任意二进制），但发出 RuntimeWarning。
"""

import warnings

import pytest

from vools.serialize import (
    Serializer,
    deserialize_method,
    serializable,
    serialize_method,
)


@serializable
class Bare:
    """模块级：pickle 无法序列化局部类，故定义在模块作用域。"""

    def __init__(self, name):
        self.name = name


@serializable(backend='pickle')
class Paren:
    def __init__(self, v):
        self.v = v


class TestBareDecoratorForms:
    def test_bare_serializable_keeps_class(self):
        # 修复前：Bare 已变成装饰器函数（类丢失）
        assert isinstance(Bare, type)
        back = Bare.deserialize(Bare.serialize(Bare('abc')))
        assert back.name == 'abc'

    def test_bare_serialize_method(self):
        class S:
            @serialize_method
            def state(self):
                return {'a': 1}

        raw = S().state()
        assert isinstance(raw, bytes)
        assert Serializer(backend='pickle').loads(raw) == {'a': 1}

    def test_bare_deserialize_method(self):
        class D:
            @deserialize_method
            def update(self, state):
                self.state = state

        d = D()
        d.update(Serializer(backend='pickle').dumps({'a': 1}))
        assert d.state == {'a': 1}


class TestParenthesizedFormsUnchanged:
    def test_serializable_with_backend(self):
        assert Paren.deserialize(Paren.serialize(Paren(1))).v == 1

    def test_serialize_method_with_backend(self):
        class S:
            @serialize_method(backend='json')
            def state(self):
                return {'a': 1}

        assert Serializer(backend='json').loads(S().state()) == {'a': 1}

    def test_deserialize_method_with_backend(self):
        class D:
            @deserialize_method(backend='json')
            def update(self, state):
                self.state = state

        d = D()
        d.update(b'{"a": 2}')
        assert d.state == {'a': 2}


class TestMismatchWarning:
    def test_method_mismatch_warns_and_falls_back(self):
        class M:
            @deserialize_method(backend='json')
            def take(self, data):
                self.data = data

        m = M()
        payload = Serializer(backend='pickle').dumps({'a': 1})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            m.take(payload)
        # 修复前：静默
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)
        assert m.data == payload  # 仍回退为原始 bytes

    def test_matching_backend_no_warning(self):
        class OK:
            @deserialize_method(backend='json')
            def take(self, data):
                self.data = data

        ok = OK()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            ok.take(b'{"a": 2}')
        assert not caught
        assert ok.data == {'a': 2}