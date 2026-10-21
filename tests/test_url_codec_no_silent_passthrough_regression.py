# -*- coding: utf-8 -*-
"""回归测试：Encoder/Decoder.url() 不静默透传（BUG-222）。

原 `_urlencode`/`_urldecode` 对非 str 输入 `return data` 静默原样透传——
bytes/dict/int 什么都不编码还让 `_apply` 把 'url' 记进 history（虚假
成功），与同场 base64/gzip 对非法输入明确抛 ValueError 的口径不一。

修复：bytes/bytearray 走 `quote_from_bytes`/`unquote`（标准库原生能力）；
其余类型抛 TypeError，经 `_apply` 统一包装 ValueError；失败不污染
data/history。
"""

import pytest

from vools.encoding.core import Decoder, Encoder


class TestUrlEncodeInputMatrix:
    """url() 编码侧输入矩阵（BUG-222 核心）。"""

    def test_str_still_works(self):
        e = Encoder('hello world')
        assert e.url().data == 'hello%20world'
        assert e.history == ['url']

    def test_bytes_now_encoded(self):
        # 修复前：b'a b\xff' 原样透传
        e = Encoder(b'a b\xff')
        e.url()
        assert e.data == 'a%20b%FF'

    def test_bytearray_encoded(self):
        e = Encoder(bytearray(b'x y'))
        e.url()
        assert e.data == 'x%20y'

    def test_dict_raises_loud(self):
        # 修复前：dict 原样透传 + history 造假
        with pytest.raises(ValueError, match="url encode expects"):
            Encoder({'a': 1}).url()

    def test_int_raises_loud(self):
        with pytest.raises(ValueError, match="url encode expects"):
            Encoder(123).url()


class TestUrlDecodeInputMatrix:
    """url() 解码侧对称。"""

    def test_str_still_works(self):
        assert Decoder('a%20b').url().data == 'a b'

    def test_bytes_matches_stdlib(self):
        import urllib.parse
        got = Decoder(b'a%20b%FF').url().data
        assert got == urllib.parse.unquote(b'a%20b%FF')

    def test_utf8_percent_sequence(self):
        assert Decoder(b'%E4%B8%AD%E6%96%87').url().data == '中文'

    def test_int_raises(self):
        with pytest.raises(ValueError, match="url decode expects"):
            Decoder(123).url()


class TestFailureHygiene:
    """失败不污染链状态。"""

    def test_failed_url_keeps_data_and_history(self):
        e = Encoder(3.14)
        with pytest.raises(ValueError):
            e.url()
        assert e.history == []
        assert e.data == 3.14


class TestRoundTrip:
    """编解码往返。"""

    def test_str_roundtrip(self):
        original = 'a b&c=中文'
        enc = Encoder(original).url()
        assert Decoder(enc.data).url().data == original