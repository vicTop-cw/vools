# -*- coding: utf-8 -*-
"""tests/serialize/test_codec.py — codec 模块回归测试"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.serialize.codec import (
    vools_default, vools_object_hook, vools_preprocess,
    pickle_encode, pickle_decode,
)
from vools.serialize.backends.json_backend import JsonBackend


class TestVoolsDefaultBytes:
    """BUG-89: vools_default 无法序列化 bytes"""

    def test_bytes_basic(self):
        """基本 bytes 序列化"""
        r = vools_default(b'hello')
        assert r == {'__vools_bytes__': True, 'data': 'aGVsbG8='}

    def test_bytes_empty(self):
        """空 bytes"""
        r = vools_default(b'')
        assert r == {'__vools_bytes__': True, 'data': ''}

    def test_bytes_null(self):
        """含空字节的 bytes"""
        r = vools_default(b'\x00\x01\xff')
        assert r['__vools_bytes__'] is True
        assert r['data']  # base64 非空

    def test_json_dumps_with_default(self):
        """json.dumps + vools_default 可序列化 bytes"""
        r = json.dumps({'data': b'hello'}, default=vools_default)
        assert '"aGVsbG8="' in r

    def test_object_hook_roundtrip(self):
        """vools_object_hook 反序列化回 bytes"""
        r = vools_object_hook({'__vools_bytes__': True, 'data': 'aGVsbG8='})
        assert r == b'hello'

    def test_full_roundtrip(self):
        """完整 json 往返"""
        s = json.dumps({'data': b'hello', 'nested': [b'a', b'b']}, default=vools_default)
        d = json.loads(s, object_hook=vools_object_hook)
        assert d == {'data': b'hello', 'nested': [b'a', b'b']}

    def test_json_backend_roundtrip(self):
        """JsonBackend 完整往返"""
        be = JsonBackend()
        r = be.dumps({'data': b'hello'})
        d = be.loads(r)
        assert d == {'data': b'hello'}


class TestVoolsDefaultTypes:
    """其他类型序列化验证"""

    def test_datetime(self):
        import datetime
        r = vools_default(datetime.datetime(2024, 1, 1))
        assert r['__vools_type__'] is True
        assert r['type'] == 'datetime.datetime'

    def test_decimal(self):
        import decimal
        r = vools_default(decimal.Decimal('3.14'))
        assert r['__vools_type__'] is True
        assert r['type'] == 'decimal.Decimal'

    def test_set(self):
        r = vools_default({1, 2, 3})
        assert r['__vools_type__'] is True
        assert r['type'] == 'set'

    def test_unsupported_custom(self):
        """未知类型仍抛 TypeError"""
        class Custom:
            pass
        try:
            vools_default(Custom())
            assert False, 'Should raise TypeError'
        except TypeError:
            pass


class TestVoolsPreprocess:
    """preprocess 边缘情况"""

    def test_bytes_passthrough(self):
        """bytes 原样透传（由 vools_default 后续处理）"""
        r = vools_preprocess(b'hello')
        assert r == b'hello'

    def test_nested_bytes(self):
        """嵌套 bytes 递归处理"""
        r = vools_preprocess({'data': b'hello', 'list': [b'a', b'b']})
        assert r == {'data': b'hello', 'list': [b'a', b'b']}

    def test_dict_recursive(self):
        """字典递归"""
        r = vools_preprocess({'a': {'b': {'c': 1}}})
        assert r == {'a': {'b': {'c': 1}}}


class TestPickleCodec:
    """pickle 编解码"""

    def test_roundtrip_basic(self):
        for obj in [None, True, False, 0, 42, -1, 3.14, 'hello',
                    [1, 2, 3], {'a': 1}, (1, 2), b'bytes', 10**100]:
            assert pickle_decode(pickle_encode(obj)) == obj

    def test_empty_decode_blocked(self):
        try:
            pickle_decode(b'')
            assert False, 'Should raise'
        except Exception:
            pass

    def test_invalid_decode_blocked(self):
        try:
            pickle_decode(b'not-a-pickle')
            assert False, 'Should raise'
        except Exception:
            pass

    def test_none_decode_blocked(self):
        try:
            pickle_decode(None)
            assert False, 'Should raise'
        except Exception:
            pass