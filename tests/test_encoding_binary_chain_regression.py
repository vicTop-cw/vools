# -*- coding: utf-8 -*-
"""回归测试：编码链支持二进制载荷（BUG-370）。

`Decoder._b64decode` 原实现强制把解码结果按 utf-8 转成 **str**：

    base64.b64decode(data).decode('utf-8')

于是 base64 之后的**二进制解码器无法工作**——gzip / zlib / lzma / pickle 的
base64 形态不是合法 UTF-8，直接抛 `UnicodeDecodeError`；即使传
`encoding='latin-1'` 也无济于事（返回 str，下一步 gzip 仍要求 bytes），
即 binary 链**完全无法往返**：

    Decoder(Encoder('hello').gzip().base64().data).base64().gzip()
    # ValueError: Failed to apply base64: 'utf-8' codec can't decode byte 0x8b ...

修复：解码后按 encoding 尝试转 str；遇 `UnicodeDecodeError` 返回原始 bytes，
使后续二进制解码器可继续处理。文本载荷仍返回 str（docstring 中
`Decoder('aGVsbG8=').base64().data == 'hello'` 的契约不变）。
"""

import pytest

from vools.encoding.core import Decoder, Encoder


class TestTextPayloadUnchanged:
    def test_plain_base64_returns_str(self):
        assert Decoder('aGVsbG8=').base64().data == 'hello'

    def test_json_base64_chain(self):
        payload = {'a': 1, 'b': ['中文']}
        enc = Encoder(payload).json().base64().data
        assert Decoder(enc).base64().json().data == payload

    def test_url_roundtrip(self):
        enc = Encoder('a b/c?').url().data
        assert Decoder(enc).url().data == 'a b/c?'


class TestBinaryPayloadChains:
    """修复前全部抛 UnicodeDecodeError。"""

    def test_gzip(self):
        enc = Encoder('hello 中文').gzip().base64().data
        assert Decoder(enc).base64().gzip().to_str().data == 'hello 中文'

    def test_zlib(self):
        enc = Encoder('data').zlib().base64().data
        assert Decoder(enc).base64().zlib().to_str().data == 'data'

    def test_lzma(self):
        enc = Encoder('data x').lzma().base64().data
        assert Decoder(enc).base64().lzma().to_str().data == 'data x'

    def test_pickle(self):
        obj = [1, 2, {'k': '中'}]
        enc = Encoder(obj).pickle().base64().data
        assert Decoder(enc).base64().pickle().data == obj

    def test_raw_bytes(self):
        enc = Encoder(b'\x00\xff').base64().data
        assert Decoder(enc).base64().data == b'\x00\xff'


class TestErrorsStillSurface:
    def test_bad_gzip_after_base64(self):
        with pytest.raises(ValueError):
            Decoder('aGVsbG8=').base64().gzip()

    def test_bad_json(self):
        with pytest.raises(ValueError):
            Decoder('{bad').json()

    def test_unknown_custom_format(self):
        with pytest.raises(ValueError):
            Encoder('x').encode('nope-xyz')