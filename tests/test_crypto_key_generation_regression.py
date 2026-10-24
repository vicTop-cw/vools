# -*- coding: utf-8 -*-
"""回归测试：密钥/令牌生成长度校验（BUG-458）+ 加密工具契约。

修复前：

    generate_key(0)    # -> ''   ← 空密钥，语义上等同"无保护"，却像一次成功生成
    generate_token(0)  # -> ''   ← 空令牌
    （负值由底层 secrets 报错，只有 0 被静默接受）

修复后 length 必须 >= 1，非整数/布尔值报 TypeError。
"""

import pytest

import vools.crypto as cr


class TestKeyLengthValidation:
    @pytest.mark.parametrize("func", [cr.generate_key, cr.generate_token])
    def test_zero_length_rejected(self, func):
        with pytest.raises(ValueError) as ei:
            func(0)
        assert ">= 1" in str(ei.value)

    @pytest.mark.parametrize("func", [cr.generate_key, cr.generate_token])
    def test_negative_rejected(self, func):
        with pytest.raises(ValueError):
            func(-1)

    @pytest.mark.parametrize("bad", ["x", None, 1.5, True])
    @pytest.mark.parametrize("func", [cr.generate_key, cr.generate_token])
    def test_non_int_rejected(self, func, bad):
        with pytest.raises(TypeError) as ei:
            func(bad)
        assert "length" in str(ei.value)


class TestKeyGeneration:
    def test_default_hex_key_length(self):
        assert len(cr.generate_key()) == 64        # 32 字节 → 64 hex

    def test_key_length_proportional(self):
        for n in (1, 8, 16, 32):
            assert len(cr.generate_key(n)) == 2 * n

    def test_token_non_empty(self):
        assert len(cr.generate_token()) > 0

    def test_keys_are_random(self):
        assert cr.generate_key(32) != cr.generate_key(32)
        assert cr.generate_token() != cr.generate_token()

    def test_token_is_url_safe(self):
        import re
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", cr.generate_token(16))


class TestHashHelpers:
    def test_str_and_bytes_agree(self):
        assert cr.md5("abc") == cr.md5(b"abc")
        assert cr.sha256("abc") == cr.sha256(b"abc")

    def test_known_md5(self):
        assert cr.md5("abc") == "900150983cd24fb0d6963f7d28e17f72"

    def test_hmac_str_and_bytes_agree(self):
        assert cr.hmac_sha256("k", "m") == cr.hmac_sha256(b"k", b"m")

    @pytest.mark.parametrize("bad", [123, None])
    def test_non_buffer_input_loud(self, bad):
        with pytest.raises(TypeError):
            cr.md5(bad)


class TestCryptoRegistry:
    def test_default_algorithms_registered(self):
        algos = cr.CryptoRegistry.supported_algorithms()
        for name in ("md5", "sha1", "sha256", "sha512", "hmac_sha256"):
            assert name in algos

    def test_is_algorithm_supported(self):
        assert cr.CryptoRegistry.is_algorithm_supported("sha256") is True
        assert cr.CryptoRegistry.is_algorithm_supported("nope") is False
