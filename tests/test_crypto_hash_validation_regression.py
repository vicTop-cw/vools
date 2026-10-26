# -*- coding: utf-8 -*-
"""回归测试：crypto 哈希/HMAC 入参零校验（BUG-516）。

修复前：

    md5(None)               # TypeError: object supporting the buffer API required
    md5(123)                # 同上（看不出是哪个参数、期望什么类型）
    hmac_sha256("a", None)  # TypeError: key: expected bytes or bytearray, but got 'NoneType'
    hmac_sha256(None, "k")  # **静默算出摘要**（hmac.new 把 None 当空消息），
                            #   与 md5(None) 报错的行为不一致，调用方无法察觉消息丢失

修复后：哈希/HMAC 的 data 与 key 都要求 str/bytes/bytearray/memoryview；错误带参数名。
已知摘要值保持不变（回归防篡改）。
"""

import pytest

import vools.crypto as cr

KNOWN_MD5_ABC = "900150983cd24fb0d6963f7d28e17f72"
KNOWN_SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
KNOWN_HMAC = "2d93cbc1be167bcb1637a4a23cbff01a7878f0c50ee833954ea5221bb1b8c628"


class TestHashValidation:
    @pytest.mark.parametrize("fn_name", ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"])
    @pytest.mark.parametrize("bad", [None, 123, 1.5, {"a": 1}, [1]])
    def test_rejects_non_data(self, fn_name, bad):
        fn = getattr(cr, fn_name)
        with pytest.raises(TypeError) as ei:
            fn(bad)
        assert "data" in str(ei.value)


class TestHashValuesUnchanged:
    def test_md5_str_and_bytes(self):
        assert cr.md5("abc") == KNOWN_MD5_ABC
        assert cr.md5(b"abc") == KNOWN_MD5_ABC

    def test_bytearray_and_memoryview(self):
        assert cr.md5(bytearray(b"abc")) == KNOWN_MD5_ABC
        assert cr.md5(memoryview(b"abc")) == KNOWN_MD5_ABC

    def test_sha256(self):
        assert cr.sha256("abc") == KNOWN_SHA256_ABC


class TestHmacValidation:
    @pytest.mark.parametrize("fn_name", ["hmac_md5", "hmac_sha1", "hmac_sha256"])
    @pytest.mark.parametrize("bad", [None, 123, {"a": 1}])
    def test_bad_data(self, fn_name, bad):
        fn = getattr(cr, fn_name)
        with pytest.raises(TypeError) as ei:
            fn(bad, "key")
        assert "data" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123, {"a": 1}])
    def test_bad_key(self, bad):
        with pytest.raises(TypeError) as ei:
            cr.hmac_sha256("data", bad)
        assert "key" in str(ei.value)

    def test_none_data_no_longer_silent(self):
        """修复前 hmac_sha256(None, "k") 会静默返回空消息摘要。"""
        with pytest.raises(TypeError):
            cr.hmac_sha256(None, "k")


class TestHmacValuesUnchanged:
    def test_known_value(self):
        assert cr.hmac_sha256("msg", "key") == KNOWN_HMAC

    def test_str_and_bytes_equivalent(self):
        assert cr.hmac_sha256("msg", "key") == cr.hmac_sha256(b"msg", b"key")

    def test_bytearray(self):
        assert cr.hmac_sha256(bytearray(b"msg"), bytearray(b"key")) == KNOWN_HMAC


class TestGenerateKeyUnchanged:
    def test_default_length(self):
        assert len(cr.generate_key()) == 64

    def test_custom_length(self):
        assert len(cr.generate_key(16)) == 32

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive(self, bad):
        with pytest.raises(ValueError):
            cr.generate_key(bad)

    def test_wrong_type(self):
        with pytest.raises(TypeError):
            cr.generate_key("x")
