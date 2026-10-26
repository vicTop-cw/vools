# -*- coding: utf-8 -*-
"""回归测试：encoding.core 的 encodable/decodable 格式名零校验（BUG-517）。

修复前：

    @encodable(None)      # 静默把编码器注册到无意义键（None）上，
    @encodable(123)       # 随后 CodecRegistry.get_encoder("正常名") 永远拿不到
    @encodable("")        # 同理

修复后：format_name 必须是非空字符串，装饰期即 ValueError（带函数名与实参）。

注意 Encoder/Decoder 的正确用法是 ``Encoder(data).encode(format)``
（encodable 的装饰器注册的是**格式处理函数**，两者不是一回事）。
"""

import pytest

import vools.encoding.core as ec


class TestEncodableValidation:
    @pytest.mark.parametrize("bad", [None, 123, "", "   "])
    def test_bad_format_name(self, bad):
        with pytest.raises(ValueError) as ei:
            ec.encodable(bad)
        assert "format_name" in str(ei.value)
        assert "encodable" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123, ""])
    def test_decodable_bad_format_name(self, bad):
        with pytest.raises(ValueError) as ei:
            ec.decodable(bad)
        assert "format_name" in str(ei.value)
        assert "decodable" in str(ei.value)


class TestEncodableRegistrationUnchanged:
    def test_register_and_retrieve(self):
        @ec.encodable("ut-fmt-517")
        def enc(data):
            return b"encoded"

        assert ec.CodecRegistry.get_encoder("ut-fmt-517") is enc

    def test_decodable_register_and_retrieve(self):
        @ec.decodable("ut-fmt-517")
        def dec(data):
            return "decoded"

        assert ec.CodecRegistry.get_decoder("ut-fmt-517") is dec

    def test_decorator_returns_function_unchanged(self):
        def enc(data):
            return b"x"

        assert ec.encodable("ut-fmt-517b")(enc) is enc


class TestEncoderDecoderUsage:
    @pytest.mark.parametrize("fmt", ["base64", "zlib", "gzip", "lzma", "pickle"])
    def test_encode_returns_encoder(self, fmt):
        assert isinstance(ec.Encoder(b"hi").encode(fmt), ec.Encoder)

    def test_json_bytes_rejected(self):
        with pytest.raises(ValueError):
            ec.Encoder(b"hi").encode("json")

    def test_unknown_format_loud(self):
        with pytest.raises(ValueError) as ei:
            ec.Encoder(b"hi").encode("bogus")
        assert "Unknown encoder format" in str(ei.value)
        assert "base64" in str(ei.value)


class TestStuffNotAffected:
    def test_stuff_none_returns_decorator(self):
        """stuff(None) 返回装饰器是文档行为（'若为 None 返回装饰器'）。"""
        import importlib

        st = importlib.import_module("vools.utils.stuff")
        assert callable(st.stuff(None))

    def test_stuff_non_callable_rejected(self):
        import importlib

        st = importlib.import_module("vools.utils.stuff")
        with pytest.raises(TypeError):
            st.stuff(123)
