"""tests/serialize/test_core.py — Serializer 核心类测试"""
import pytest
import sys
import os
import pickle
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.serialize import Serializer
from vools.serialize.backends.pickle_backend import PickleBackend
from vools.serialize.backends.json_backend import JsonBackend
from vools.serialize.backends.msgpack_backend import MsgpackBackend


class TestSerializer:
    """Serializer 测试"""

    def test_create_with_pickle(self):
        s = Serializer(backend='pickle')
        assert s.backend_name == 'pickle'
        assert isinstance(s._backend, PickleBackend)

    def test_create_with_json(self):
        s = Serializer(backend='json')
        assert s.backend_name == 'json'
        assert isinstance(s._backend, JsonBackend)

    def test_create_default(self):
        s = Serializer()
        assert s.backend_name in ('pickle', 'json')

    def test_repr(self):
        s = Serializer(backend='pickle')
        assert 'pickle' in repr(s)

    def test_pickle_roundtrip(self):
        s = Serializer(backend='pickle')
        obj = {'key': 'value', 'num': 42, 'nested': [1, 2, 3]}
        data = s.dumps(obj)
        result = s.loads(data)
        assert result == obj

    def test_pickle_hex_roundtrip(self):
        s = Serializer(backend='pickle')
        obj = {'name': 'test', 'count': 10}
        hex_str = s.dumps_hex(obj)
        assert isinstance(hex_str, str)
        result = s.loads_hex(hex_str)
        assert result == obj

    def test_json_roundtrip(self):
        s = Serializer(backend='json')
        obj = {'key': 'value', 'num': 42}
        data = s.dumps(obj)
        result = s.loads(data)
        assert result == obj

    def test_json_hex_roundtrip(self):
        s = Serializer(backend='json')
        obj = {'name': 'test'}
        hex_str = s.dumps_hex(obj)
        result = s.loads_hex(hex_str)
        assert result == obj

    def test_pickle_complex_types(self):
        s = Serializer(backend='pickle')
        obj = {'set': {1, 2, 3}, 'tuple': (4, 5, 6), 'bytes': b'raw'}
        data = s.dumps(obj)
        result = s.loads(data)
        assert result['set'] == {1, 2, 3}
        assert result['tuple'] == (4, 5, 6)
        assert result['bytes'] == b'raw'

    def test_pickle_empty(self):
        s = Serializer(backend='pickle')
        obj = {}
        data = s.dumps(obj)
        result = s.loads(data)
        assert result == {}

    def test_pickle_none(self):
        s = Serializer(backend='pickle')
        data = s.dumps(None)
        result = s.loads(data)
        assert result is None

    def test_do_method(self):
        s = Serializer(backend='pickle')
        results = []
        s.do(f=lambda x: results.append(x))
        assert len(results) == 1


class TestMsgpackSerializer:
    """Msgpack Serializer 测试"""

    def test_roundtrip(self):
        try:
            s = Serializer(backend='msgpack')
            obj = {'key': 'value', 'num': 42}
            data = s.dumps(obj)
            result = s.loads(data)
            assert result == obj
        except ImportError:
            pytest.skip('msgpack not installed')
