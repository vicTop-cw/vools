"""tests/serialize/test_config.py — 序列化配置测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.serialize.config import (
    get_default_backend, set_default_backend, clear_default_backend,
)


class TestSerializeConfig:
    """序列化配置测试"""

    def test_default_backend(self):
        backend = get_default_backend()
        assert isinstance(backend, (str, type(None)))

    def test_set_default_backend(self):
        set_default_backend('json')
        assert get_default_backend() == 'json'
        set_default_backend('pickle')
        assert get_default_backend() == 'pickle'

    def test_clear_default_backend(self):
        set_default_backend('json')
        clear_default_backend()
        assert get_default_backend() is None


class TestSerializeRegistry:
    """序列化注册表测试"""

    def test_get_backend(self):
        from vools.serialize.backends import get_backend
        backend_cls = get_backend('pickle')
        assert backend_cls is not None

    def test_register_backend(self):
        from vools.serialize.backends import get_backend, register_backend, _BACKENDS
        class CustomBackend:
            pass
        register_backend('test_custom', CustomBackend)
        assert get_backend('test_custom') is CustomBackend
        # 清理
        del _BACKENDS['test_custom']
