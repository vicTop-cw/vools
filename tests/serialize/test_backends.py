"""tests/serialize/test_backends.py — 序列化后端测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.serialize.backends.pickle_backend import PickleBackend
from vools.serialize.backends.json_backend import JsonBackend


class TestPickleBackend:
    """PickleBackend 测试"""

    def test_create(self):
        b = PickleBackend()
        assert b is not None

    def test_roundtrip(self):
        b = PickleBackend()
        obj = {'key': 'value', 'num': 42}
        data = b.dumps(obj)
        assert isinstance(data, bytes)
        result = b.loads(data)
        assert result == obj

    def test_hex_roundtrip(self):
        b = PickleBackend()
        obj = {'name': 'test'}
        hex_str = b.dumps_hex(obj)
        assert isinstance(hex_str, str)
        result = b.loads_hex(hex_str)
        assert result == obj

    def test_repr(self):
        b = PickleBackend()
        assert 'PickleBackend' in repr(b)


class TestJsonBackend:
    """JsonBackend 测试"""

    def test_create(self):
        b = JsonBackend()
        assert b is not None

    def test_roundtrip(self):
        b = JsonBackend()
        obj = {'key': 'value', 'num': 42}
        data = b.dumps(obj)
        assert isinstance(data, bytes)
        result = b.loads(data)
        assert result == obj

    def test_hex_roundtrip(self):
        b = JsonBackend()
        obj = {'name': 'test'}
        hex_str = b.dumps_hex(obj)
        assert isinstance(hex_str, str)
        result = b.loads_hex(hex_str)
        assert result == obj

    def test_repr(self):
        b = JsonBackend()
        assert 'JsonBackend' in repr(b)


class TestBackendContext:
    """后端上下文协议测试"""

    def test_pickle_context(self):
        from vools.serialize.context import set_context, reset_context, get_context
        b = PickleBackend()
        token = set_context('pickle', b)
        ctx = get_context()
        assert ctx is not None
        reset_context(token)

    def test_json_context(self):
        from vools.serialize.context import set_context, reset_context, get_context
        b = JsonBackend()
        token = set_context('json', b)
        ctx = get_context()
        assert ctx is not None
        reset_context(token)
