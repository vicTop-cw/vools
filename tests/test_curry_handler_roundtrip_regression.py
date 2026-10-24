# -*- coding: utf-8 -*-
"""回归测试：柯里化函数（Curried）的序列化（BUG-453）。

修复前 ``Curried`` 完全不可序列化：

    dumps(curry(fn), backend='pickle')   # TypeError: cannot pickle 'mappingproxy' object
    dumps(curry(fn), backend='json')     # TypeError: Object of type Curried is not serializable

即把柯里化函数放进任务载荷 / 缓存时静默不可用。修复：新增 ``CurryHandler``
把底层函数存成 ``{'module','qualname'}`` 引用，连同 ``bound_args`` /
``is_strict`` / ``delaied`` 一起保存，反序列化重建等价 ``Curried``。
"""

import pytest

from vools.decorators import curry
from vools.serialize.backends.json_backend import JsonBackend
from vools.serialize.backends.pickle_backend import PickleBackend
from vools.serialize.callable import (
    _HANDLERS,
    CurryHandler,
    deserialize_callable,
    get_handler,
    serialize_callable,
)


def module_fn(a, b):
    return a + b


@curry
def curried_module_fn(a, b):
    return a + b


@pytest.fixture(autouse=True)
def _snapshot_handlers():
    snapshot = list(_HANDLERS)
    yield
    _HANDLERS[:] = snapshot


def _roundtrip(obj, backend):
    name, state = serialize_callable(obj, backend)
    return name, deserialize_callable(name, state, backend)


BACKENDS = [PickleBackend(), JsonBackend()]


class TestHandlerSelection:
    @pytest.mark.parametrize("obj", [
        curry(module_fn),
        curried_module_fn,
        curry(module_fn)(1),
    ])
    def test_claimed_by_curry_handler(self, obj):
        assert isinstance(get_handler(obj), CurryHandler)

    def test_handler_registered_before_decorator(self):
        names = [h.handler_name for h in _HANDLERS]
        assert names.index("CurryHandler") < names.index("DecoratorHandler")


class TestCurriedRoundtrip:
    @pytest.mark.parametrize("backend", BACKENDS)
    def test_curry_wrapped_function(self, backend):
        name, restored = _roundtrip(curry(module_fn), backend)
        assert name == "CurryHandler"
        assert type(restored).__name__ == "Curried"
        assert restored(1)(2) == 3

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_module_level_decorated(self, backend):
        _, restored = _roundtrip(curried_module_fn, backend)
        assert restored(1)(2) == 3

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_partial_application_preserved(self, backend):
        """bound_args 必须保留：部分应用状态不能丢。"""
        _, restored = _roundtrip(curry(module_fn)(1), backend)
        assert restored.bound_args == {"a": 1}
        assert restored(2) == 3


class TestFlagsPreserved:
    @pytest.mark.parametrize("backend", BACKENDS)
    def test_is_strict(self, backend):
        _, restored = _roundtrip(curry(module_fn, is_strict=True), backend)
        assert restored.is_strict is True

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_delaied(self, backend):
        _, restored = _roundtrip(curry(module_fn, delaied=True), backend)
        assert restored.delaied is True


class TestLoudFailure:
    def test_lambda_curry_fails_loudly(self):
        """lambda 无法生成引用 → 必须是响亮失败而非静默错值。"""
        with pytest.raises(Exception):
            serialize_callable(curry(lambda a, b: a + b), PickleBackend())
