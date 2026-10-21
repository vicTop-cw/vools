# -*- coding: utf-8 -*-
"""回归测试：CodecRegistry 装饰器错位（BUG-276）。

类体中 `@classmethod` 被错放在注入的 `do` 侧效助手上：
① `get_decoders` 缺 `@classmethod` → `CodecRegistry.get_decoders()` 抛
   `TypeError: missing 1 required positional argument: 'cls'`（对称的
   `get_encoders()` 正常，API 破损且不对称）；
② `do` 变 classmethod → self 绑定为类，传给 f 的是类对象、返回类而非实例
   （do 文档语义：Apply a function for side effects, return self）。

修复：`do` 恢复实例方法、`get_decoders` 补 `@classmethod`。
"""

from vools.encoding.core import CodecRegistry, Decoder, Encoder


class TestGetDecodersClassmethod:
    def test_class_call_works(self):
        # 修复前：TypeError missing 1 required positional argument: 'cls'
        decoders = CodecRegistry.get_decoders()
        assert isinstance(decoders, dict)

    def test_symmetric_with_get_encoders(self):
        assert isinstance(CodecRegistry.__dict__['get_decoders'], classmethod)
        assert isinstance(CodecRegistry.__dict__['get_encoders'], classmethod)

    def test_instance_call_still_works(self):
        assert isinstance(CodecRegistry().get_decoders(), dict)


class TestDoInstanceMethod:
    def test_passes_instance_to_callable(self):
        # 修复前：classmethod 下传入的是 CodecRegistry 类对象
        inst = CodecRegistry()
        captured = []
        inst.do(lambda x: captured.append(x))
        assert captured and captured[0] is inst

    def test_returns_self(self):
        inst = CodecRegistry()
        assert inst.do(lambda x: None) is inst

    def test_pre_and_sub_hooks(self):
        inst = CodecRegistry()
        order = []
        inst.do(lambda x: order.append('f'),
                pre_f=lambda x: order.append('pre'),
                sub_f=lambda x: order.append('sub'))
        assert order == ['pre', 'f', 'sub']


class TestEncodingStillWorks:
    def test_roundtrip(self):
        enc = Encoder('hello').base64().data
        assert Decoder(enc).base64().data == 'hello'

    def test_json_roundtrip(self):
        enc = Encoder({'a': 1}).json().data
        assert Decoder(enc).json().data == {'a': 1}