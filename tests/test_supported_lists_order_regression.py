# -*- coding: utf-8 -*-
"""回归测试：supported_formats / supported_algorithms 顺序稳定（BUG-337）。

原实现：

    return list(set(cls._encoders.keys()) | set(cls._decoders.keys()))
    return list(set(cls._encryptors.keys()) | set(cls._decryptors.keys()))

`set` 的迭代顺序依赖字符串哈希，而 Python 默认 **PYTHONHASHSEED 随机化**，
因此同一进程启动多次会得到不同顺序：

    formats: ['zlib','json','lzma','base64','gzip','pickle','url']
    下一进程 -> ['url','gzip','base64','pickle','lzma','json','zlib']

这两个列表会出现在**错误信息**（如「Supported formats: [...]」）与 UI 列表中，
应当稳定、可复现。修复：统一按字母序 `sorted(...)` 返回。
"""

import pytest

from vools.crypto.core import CryptoRegistry
from vools.encoding.core import CodecRegistry


class TestCodecSupportedFormats:
    def test_sorted(self):
        formats = CodecRegistry.supported_formats()
        assert formats == sorted(formats)

    def test_stable_across_calls(self):
        results = {tuple(CodecRegistry.supported_formats()) for _ in range(20)}
        assert len(results) == 1

    def test_contains_expected(self):
        formats = CodecRegistry.supported_formats()
        for name in ('base64', 'gzip', 'json', 'lzma', 'pickle', 'url', 'zlib'):
            assert name in formats

    def test_registration_reflected(self):
        @staticmethod
        def _enc(data):
            return data

        CodecRegistry.register_encoder('zz_test_fmt', _enc)
        assert 'zz_test_fmt' in CodecRegistry.supported_formats()
        # 仍保持有序
        formats = CodecRegistry.supported_formats()
        assert formats == sorted(formats)


class TestCryptoSupportedAlgorithms:
    @pytest.mark.parametrize('call', [
        lambda: CryptoRegistry.supported_algorithms(),
    ])
    def test_sorted(self, call):
        algs = call()
        assert algs == sorted(algs)

    def test_stable_across_calls(self):
        results = {tuple(CryptoRegistry.supported_algorithms()) for _ in range(20)}
        assert len(results) == 1

    def test_contains_expected(self):
        algs = CryptoRegistry.supported_algorithms()
        for name in ('md5', 'sha1', 'sha256'):
            assert name in algs


class TestErrorMessageUsesStableOrder:
    def test_encoding_unknown_format_message(self):
        from vools.encoding.core import Encoder

        with pytest.raises(ValueError) as ei:
            Encoder('x').encode('no-such-format-xyz')
        msg = str(ei.value)
        # 错误信息里列出的支持格式应与 supported_formats() 一致（稳定序）
        assert 'base64' in msg and 'zlib' in msg
        assert msg.index('base64') < msg.index('zlib')