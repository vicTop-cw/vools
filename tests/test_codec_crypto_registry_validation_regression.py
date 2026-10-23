# -*- coding: utf-8 -*-
"""回归测试：编解码 / 加密算法注册表的参数校验（BUG-398）。

两个注册表原先都是「裸字典赋值」：

    class CodecRegistry:
        def register_encoder(cls, format_name, encoder):
            cls._encoders[format_name] = encoder        # 无校验

    class CryptoRegistry:
        def register_encryptor(cls, algorithm_name, encryptor):
            cls._encryptors[algorithm_name] = encryptor # 无校验

造成：

1. `encodable(None)` / `encryptable(None)` 可写入 `None` 键 → 之后
   `supported_formats()` / `supported_algorithms()` 里
   `sorted(set(...) | ...)` 把 None 与 str 比较 →
   ``TypeError: '<' not supported between instances of 'NoneType' and 'str'``
   —— 连 `Encryptor('x').encrypt('nope')` 的**错误提示路径**都被连带打崩；
2. 空串名称进入列表/错误信息；
3. 非可调用对象注册成功，直到真正使用才炸；
4. 同名重复注册**静默覆盖**（两个模块注册同名算法时后者无声生效）。

修复：名称必须非空 str、函数必须可调用（ValueError / TypeError）；
同名覆盖且函数不同 → RuntimeWarning（同一函数重复注册视为幂等，不告警）。
内置格式/算法与正常注册使用不受影响。
"""

import hashlib
import warnings

import pytest

from vools.crypto.core import (
    CryptoRegistry,
    Decryptor,
    Encryptor,
    decryptable,
    encryptable,
)
from vools.encoding.core import (
    CodecRegistry,
    Decoder,
    Encoder,
    decodable,
    encodable,
)


class TestCodecRegistryValidation:
    @pytest.mark.parametrize('bad', [None, '', '   ', 123])
    def test_bad_format_name(self, bad):
        with pytest.raises(ValueError):
            CodecRegistry.register_encoder(bad, lambda d: d)

    @pytest.mark.parametrize('bad', [None, 'not-callable', 42])
    def test_bad_encoder(self, bad):
        with pytest.raises(TypeError):
            CodecRegistry.register_encoder('fmt_bad', bad)

    def test_supported_formats_stays_stable(self):
        with pytest.raises(ValueError):
            CodecRegistry.register_encoder(None, lambda d: d)
        # 修复前：sorted() 混入 None → TypeError
        formats = CodecRegistry.supported_formats()
        assert all(isinstance(x, str) for x in formats)

    def test_duplicate_overwrite_warns(self):
        def e1(d):
            return f'E1:{d}'

        def e2(d):
            return f'E2:{d}'

        CodecRegistry.register_encoder('dup_codec', e1)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            CodecRegistry.register_encoder('dup_codec', e2)
        assert caught
        # 同一函数重复注册 → 幂等，不告警
        with warnings.catch_warnings(record=True) as caught2:
            warnings.simplefilter('always')
            CodecRegistry.register_encoder('dup_codec', e2)
        assert not caught2

    def test_normal_registration_works(self):
        @encodable('ok_codec')
        def oe(d):
            return f'OK:{d}'

        @decodable('ok_codec')
        def od(d):
            return str(d)[3:]

        assert Encoder('x').encode('ok_codec').data == 'OK:x'
        assert Decoder('OK:x').decode('ok_codec').data == 'x'


class TestCryptoRegistryValidation:
    @pytest.mark.parametrize('bad', [None, '', 123])
    def test_bad_algorithm_name(self, bad):
        with pytest.raises(ValueError):
            CryptoRegistry.register_encryptor(bad, lambda d, **k: d)

    @pytest.mark.parametrize('bad', [None, 'nope'])
    def test_bad_encryptor(self, bad):
        with pytest.raises(TypeError):
            CryptoRegistry.register_encryptor('algo_bad', bad)

    def test_unknown_algorithm_error_path_intact(self):
        # 修复前：若曾有 None 键注册，此处 sorted() 抛 TypeError 而非 ValueError
        with pytest.raises(ValueError) as ei:
            Encryptor('x').encrypt('no_such_algo_xxx')
        assert 'Supported' in str(ei.value) or 'algorithm' in str(ei.value)

    def test_supported_algorithms_all_str(self):
        assert all(isinstance(x, str) for x in CryptoRegistry.supported_algorithms())

    def test_duplicate_overwrite_warns(self):
        def c1(d, **k):
            return d

        def c2(d, **k):
            return d

        CryptoRegistry.register_encryptor('dup_algo', c1)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            CryptoRegistry.register_encryptor('dup_algo', c2)
        assert caught

    def test_normal_registration_and_builtins(self):
        @encryptable('my_algo')
        def enc(d, **k):
            return f'ENC({d})'

        @decryptable('my_algo')
        def dec(d, **k):
            return str(d)[4:-1]

        assert Encryptor('v').encrypt('my_algo').data == 'ENC(v)'
        assert Decryptor('ENC(v)').decrypt('my_algo').data == 'v'
        assert Encryptor('hello').md5().data == hashlib.md5(b'hello').hexdigest()