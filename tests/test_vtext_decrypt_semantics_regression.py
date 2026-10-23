# -*- coding: utf-8 -*-
"""回归测试：VText.decrypt 的失败语义与 way 校验（BUG-394）。

原实现三处静默：

1. **非法 `way` 被静默忽略**：密文带前缀（`F:`/`A:`/`E:`）时前缀优先，
   传 `way='des'` 依然"解密成功"——
       VText('A:...').decrypt('des', key='k')   # 修复前：返回明文，无报错
2. **错误密钥 / 损坏密文** → 静默返回空 VText，调用方无法与"空文本"区分；
3. 文档写"解密失败回退原文/空串"，实现**一律空串**，无前缀的普通文本也被吞成空串。

修复：
- `way` 先校验 ∈ {None, 'xor', 'fernet', 'aes'}，否则 ValueError；
- 带前缀（确为密文）解密失败 → 回退空串 + RuntimeWarning（可见）；
- 无前缀（本来不是密文）→ 回退**原文**（文档的另一种回退），无告警。
"""

import warnings

import pytest

from vools.data.vtext import VText


@pytest.fixture()
def aes_cipher():
    return str(VText('secret 中文').encrypt('aes', key='k'))


class TestRoundTrip:
    def test_aes(self, aes_cipher):
        assert str(VText(aes_cipher).decrypt('aes', key='k')) == 'secret 中文'

    def test_auto_detect_prefix(self, aes_cipher):
        assert str(VText(aes_cipher).decrypt(key='k')) == 'secret 中文'

    def test_xor(self):
        c = str(VText('hello').encrypt(key='k'))
        assert str(VText(c).decrypt(key='k')) == 'hello'

    def test_roundtrip_no_warning(self, aes_cipher):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            VText(aes_cipher).decrypt('aes', key='k')
        assert not caught


class TestInvalidWay:
    @pytest.mark.parametrize('way', ['des', 'rsa', 'md5', 'bogus'])
    def test_rejected(self, aes_cipher, way):
        with pytest.raises(ValueError) as ei:
            VText(aes_cipher).decrypt(way, key='k')
        assert '未知解密方式' in str(ei.value)

    def test_valid_ways_accepted(self, aes_cipher):
        # 大小写/空白容错
        assert str(VText(aes_cipher).decrypt('AES', key='k')) == 'secret 中文'
        assert str(VText(aes_cipher).decrypt(' aes ', key='k')) == 'secret 中文'


class TestFailureVisibility:
    def test_wrong_key_yields_empty_with_warning(self, aes_cipher):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            out = VText(aes_cipher).decrypt('aes', key='wrong')
        assert str(out) == ''
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)

    def test_corrupted_cipher_warns(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            out = VText('A:!!!not-base64').decrypt('aes', key='k')
        assert str(out) == ''
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)


class TestNonCiphertextFallsBackToOriginal:
    def test_plain_text_returned_as_is(self):
        # 修复前：返回空串
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            out = VText('plain text').decrypt('xor', key='k')
        assert str(out) == 'plain text'
        assert not caught

    def test_empty_text(self):
        assert str(VText('').decrypt('aes')) == ''

    def test_chinese_plain(self):
        assert str(VText('中文').decrypt(key='k')) == '中文'


class TestEncryptUnchanged:
    @pytest.mark.parametrize('way,prefix', [
        (None, 'E:'), ('xor', 'E:'), ('aes', 'A:'), ('AES', 'A:'),
    ])
    def test_prefixes(self, way, prefix):
        out = str(VText('x').encrypt(way, key='k'))
        assert out.startswith(prefix)

    def test_unknown_way(self):
        with pytest.raises(ValueError):
            VText('x').encrypt('des', key='k')