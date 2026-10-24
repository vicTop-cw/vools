# -*- coding: utf-8 -*-
"""回归测试：callable 处理器注册与选择（BUG-446/447）。

**BUG-446**：``register_handler`` 零校验——``register_handler(123)`` 把 int 追加
进模块级 ``_HANDLERS``，此后**任何** ``get_handler()`` 调用都抛
``AttributeError: 'int' object has no attribute 'can_handle'``（进程内所有
callable 序列化被破坏）。修复后非 ``CallableHandler`` 实例被拒，同一实例重复
注册幂等。

**BUG-447**：``DecoratorHandler.can_handle`` 的第三个条件
``hasattr(__name__) and not hasattr(__code__)`` 把所有 C 实现的 callable
（``print``/``len`` 等 builtins）误认领为"被装饰器包装的函数"，``restore``
必然抛 ``ValueError: Cannot restore decorated function``。修复后仅认领带
``__wrapped__``（functools.wraps）或 ``_vools_decorator`` 标记的对象；
builtins 回退到 ``raw`` 序列化路径。
"""

import functools

import pytest

from vools.serialize.callable import (
    CallableHandler,
    DecoratorHandler,
    _HANDLERS,
    deserialize_callable,
    get_handler,
    register_handler,
    serialize_callable,
)
from vools.serialize.backends.pickle_backend import PickleBackend


def module_fn(x):
    return x * 2


def _deco(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        return fn(*a, **k)
    return wrapper


@_deco
def decorated(x):
    return x + 1


@pytest.fixture(autouse=True)
def _snapshot_handlers():
    snapshot = list(_HANDLERS)
    yield
    _HANDLERS[:] = snapshot


class TestRegisterHandlerValidation:
    @pytest.mark.parametrize("bad", [123, None, "x", object(), type])
    def test_non_handler_rejected(self, bad):
        before = len(_HANDLERS)
        with pytest.raises(TypeError) as ei:
            register_handler(bad)
        assert "CallableHandler" in str(ei.value)
        assert len(_HANDLERS) == before

    def test_registry_not_poisoned(self):
        """BUG-446：失败的注册不得破坏后续 get_handler。"""
        with pytest.raises(TypeError):
            register_handler(123)
        assert get_handler(module_fn) is None   # 不抛 AttributeError
        assert isinstance(get_handler(decorated), DecoratorHandler)

    def test_valid_registration(self):
        handler = DecoratorHandler()
        before = len(_HANDLERS)
        register_handler(handler)
        assert len(_HANDLERS) == before + 1
        assert handler in _HANDLERS

    def test_idempotent_same_instance(self):
        handler = DecoratorHandler()
        register_handler(handler)
        after_first = len(_HANDLERS)
        register_handler(handler)
        assert len(_HANDLERS) == after_first


class TestHandlerSelection:
    @pytest.mark.parametrize("obj", [len, print, min, max, sum])
    def test_builtins_not_claimed(self, obj):
        """BUG-447：builtins 不应被 DecoratorHandler 认领。"""
        assert get_handler(obj) is None

    def test_decorated_function_claimed(self):
        assert isinstance(get_handler(decorated), DecoratorHandler)

    @pytest.mark.parametrize("obj", [module_fn, lambda x: x + 1])
    def test_plain_functions_unclaimed(self, obj):
        assert get_handler(obj) is None

    def test_non_callable_unclaimed(self):
        assert get_handler(123) is None


class TestRoundTripWithPickle:
    def test_builtin_roundtrip(self):
        be = PickleBackend()
        name, state = serialize_callable(print, be)
        assert name == "raw"
        restored = deserialize_callable(name, state, be)
        assert callable(restored)

    def test_module_function_roundtrip(self):
        be = PickleBackend()
        name, state = serialize_callable(module_fn, be)
        assert name == "raw"
        restored = deserialize_callable(name, state, be)
        assert restored(2) == 4

    def test_builtin_restore_no_longer_raises_decorator_error(self):
        """BUG-447：不应再抛 Cannot restore decorated function。"""
        be = PickleBackend()
        name, state = serialize_callable(len, be)
        assert name == "raw"
        restored = deserialize_callable(name, state, be)
        assert restored([1, 2]) == 2
