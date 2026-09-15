"""tests/serialize/test_context.py — 序列化上下文测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.serialize.context import (
    SerializeContext, get_context, get_protocol,
    set_context, reset_context, get_current_serializer,
)


class TestSerializeContext:
    """SerializeContext 数据类测试"""

    def test_context_creation(self):
        ctx = SerializeContext(protocol='pickle', serializer=None)
        assert ctx.protocol == 'pickle'
        assert ctx.serializer is None

    def test_context_with_serializer(self):
        from vools.serialize.core import Serializer
        s = Serializer(backend='pickle')
        ctx = SerializeContext(protocol='pickle', serializer=s)
        assert ctx.serializer is s


class TestContextManagement:
    """上下文管理测试"""

    def test_set_and_get_context(self):
        token = set_context('json', None)
        ctx = get_context()
        assert ctx is not None
        assert ctx.protocol == 'json'
        reset_context(token)

    def test_get_protocol(self):
        token = set_context('pickle', None)
        protocol = get_protocol()
        assert protocol == 'pickle'
        reset_context(token)

    def test_get_current_serializer(self):
        from vools.serialize.core import Serializer
        s = Serializer(backend='pickle')
        token = set_context('pickle', s)
        current = get_current_serializer()
        assert current is s
        reset_context(token)

    def test_reset_context(self):
        token = set_context('json', None)
        reset_context(token)
        ctx = get_context()
        # 重置后应为 None 或默认值
        assert ctx is None or ctx.protocol != 'json'

    def test_nested_context(self):
        token1 = set_context('pickle', None)
        token2 = set_context('json', None)
        ctx = get_context()
        assert ctx.protocol == 'json'
        reset_context(token2)
        ctx = get_context()
        assert ctx.protocol == 'pickle'
        reset_context(token1)
