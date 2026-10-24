# -*- coding: utf-8 -*-
"""回归测试：DecoratorHandler 的认领/恢复对称性与可往返性（BUG-448/449）。

**BUG-448**：``can_handle`` 认领只带 ``_vools_decorator`` 标记的对象，但
``get_state`` 不写 ``original_func`` → ``restore`` 必然抛
``ValueError: Cannot restore decorated function``（能序列化却不能反序列化）。

**BUG-449**：``get_state`` 把原始函数**对象**放进状态；而 ``functools.wraps``
之后模块级同名属性已被 wrapper 占用，pickle 按引用序列化会抛
``PicklingError: it's not the same object as <module>.<name>`` ——即"最典型的
被装饰函数"根本无法往返。修复：优先存 ``{'module','qualname'}`` 引用（可
pickle / 可 JSON），restore 时按引用重新导入。
"""

import functools

import pytest

from vools.serialize.backends.json_backend import JsonBackend
from vools.serialize.backends.pickle_backend import PickleBackend
from vools.serialize.callable import (
    _HANDLERS,
    DecoratorHandler,
    deserialize_callable,
    get_handler,
    serialize_callable,
)


def plain_fn(x):
    return x + 10


def marked_fn(x):
    return x * 3


marked_fn._vools_decorator = "my_marker"


def _deco(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        return fn(*a, **k)
    return wrapper


@_deco
def wrapped_fn(x):
    return x + 1


@pytest.fixture(autouse=True)
def _snapshot_handlers():
    snapshot = list(_HANDLERS)
    yield
    _HANDLERS[:] = snapshot


def _roundtrip(obj, backend):
    name, state = serialize_callable(obj, backend)
    return name, deserialize_callable(name, state, backend)


class TestMarkedFunctionRoundtrip:
    """BUG-448：_vools_decorator 标记对象必须能恢复。"""

    def test_get_state_has_ref(self):
        state = DecoratorHandler().get_state(marked_fn)
        assert state.get("original_ref") == {
            "module": __name__, "qualname": "marked_fn"}

    def test_pickle_roundtrip(self):
        handler, restored = _roundtrip(marked_fn, PickleBackend())
        assert handler == "DecoratorHandler"
        assert callable(restored)
        assert restored(2) == 6

    def test_json_roundtrip(self):
        handler, restored = _roundtrip(marked_fn, JsonBackend())
        assert handler == "DecoratorHandler"
        assert restored(2) == 6


class TestWrapsDecoratedRoundtrip:
    """BUG-449：典型 functools.wraps 装饰函数必须能往返（pickle/JSON 均可）。"""

    def test_pickle_roundtrip(self):
        handler, restored = _roundtrip(wrapped_fn, PickleBackend())
        assert handler == "DecoratorHandler"
        assert callable(restored)
        assert restored(2) == 3

    def test_json_roundtrip(self):
        handler, restored = _roundtrip(wrapped_fn, JsonBackend())
        assert handler == "DecoratorHandler"
        assert restored(2) == 3

    def test_state_has_no_unpicklable_object(self):
        state = DecoratorHandler().get_state(wrapped_fn)
        assert "__wrapped__" not in state   # 被引用替代
        assert isinstance(state["original_ref"], dict)


class TestFallbackPaths:
    def test_plain_function_uses_raw(self):
        handler, restored = _roundtrip(plain_fn, PickleBackend())
        assert handler == "raw"
        assert restored(2) == 12

    @pytest.mark.parametrize("obj", [print, len, min])
    def test_builtins_use_raw(self, obj):
        """BUG-447 的回归：builtins 不再被 DecoratorHandler 认领。"""
        assert get_handler(obj) is None
        handler, restored = _roundtrip(obj, PickleBackend())
        assert handler == "raw"
        assert callable(restored)

    def test_unresolvable_keeps_object(self):
        """无法生成 module+qualname 引用时退回对象（此处 lambda 不可 pickle → 响亮失败）。"""
        decorated_lambda = _deco(lambda x: x * 2)
        state = DecoratorHandler().get_state(decorated_lambda)
        assert "original_ref" not in state or state["original_ref"] is None
        assert "original_func" in state or "__wrapped__" in state
