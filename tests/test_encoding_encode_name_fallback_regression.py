# -*- coding: utf-8 -*-
"""回归测试：Encoder.encode / Decoder.decode 支持 Python 编码名（BUG-312）。

`Encoder`/`Decoder` 的**类文档**曾承诺：
    - encode(encoding='utf-8', errors='strict'): 字符串转字节
    - decode(encoding='utf-8', errors='strict'): 字节转字符串
但实现只查 `CodecRegistry` 的已注册格式名，`Encoder('中文').encode('utf-8')`
直接 `ValueError: Unknown encoder format: utf-8`——文档承诺的能力不可用
（真正的文本↔字节方法叫 `to_bytes` / `to_str`，文档把方法名写错了）。

修复（双管齐下）：
1. 类文档更正为 `to_bytes` / `to_str`，并说明 encode/decode 也接受编码名；
2. `encode`/`decode` 在格式未注册但名称是合法 Python 编码时回退到
   `to_bytes`/`to_str`（两种文档写法都成立），非法名仍报错。
"""

import pytest

from vools.encoding.core import Decoder, Encoder

ZH = '中文'


class TestEncodingNameFallback:
    def test_encoder_utf8(self):
        # 修复前：ValueError: Unknown encoder format: utf-8
        assert Encoder(ZH).encode('utf-8').data == ZH.encode('utf-8')

    def test_encoder_gbk(self):
        assert Encoder(ZH).encode('gbk').data == ZH.encode('gbk')

    def test_decoder_utf8(self):
        assert Decoder(ZH.encode('utf-8')).decode('utf-8').data == ZH

    def test_encoder_errors_kwarg(self):
        assert Encoder(ZH).encode('gbk', errors='strict').data == ZH.encode('gbk')


class TestRegistryStillWins:
    def test_registered_format_unchanged(self):
        # 已注册格式必须仍走注册表（json 序列化）
        out = Encoder({'a': 1}).encode('json').data
        assert out is not None
        assert Decoder(out).decode('json').data == {'a': 1}

    def test_unknown_name_still_raises(self):
        with pytest.raises(ValueError, match='Unknown encoder format'):
            Encoder('x').encode('no-such-format-xyz')

    def test_unknown_decoder_still_raises(self):
        with pytest.raises(ValueError, match='Unknown decoder format'):
            Decoder(b'x').decode('no-such-format-xyz')


class TestToBytesToStrUnchanged:
    def test_to_bytes(self):
        assert Encoder(ZH).to_bytes().data == ZH.encode('utf-8')
        assert Encoder(ZH).to_bytes('gbk').data == ZH.encode('gbk')

    def test_to_str(self):
        assert Decoder(ZH.encode('utf-8')).to_str().data == ZH
        assert Decoder(b'\xff').to_str('utf-8', 'replace').data == '\ufffd'


class TestClassDocsNameRealMethods:
    def test_encoder_doc_mentions_to_bytes(self):
        doc = Encoder.__doc__ or ''
        assert 'to_bytes' in doc
        # 原文档把能力错写成 encode(encoding=...)，不应再作为"唯一写法"出现
        assert "encode(encoding='utf-8'" not in doc

    def test_decoder_doc_mentions_to_str(self):
        doc = Decoder.__doc__ or ''
        assert 'to_str' in doc
        assert "decode(encoding='utf-8'" not in doc