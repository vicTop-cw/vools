# -*- coding: utf-8 -*-
"""回归测试：FunctionalHandler 的处理器选择与往返（BUG-450/451）。

**BUG-450**：``get_handler`` 是"首个匹配者胜"，而 ``_HANDLERS`` 顺序为
``[DecoratorHandler, FunctionalHandler]``；``Box`` 与 ``Pipe`` **恰好都暴露
``__wrapped__``**（``functools.wraps`` 写入），于是被 ``DecoratorHandler`` 抢先
认领：

    serialize_callable(Box(1))     # handler='DecoratorHandler'
    deserialize_callable(...)      # -> 普通 function（Box 类型与行为静默丢失）

修复：先注册更专用的 ``FunctionalHandler``（只认 Pipe/Ops/P/Box 固定类型集）。

**BUG-451**：``Pipe`` 的部分应用参数只存在于 ``__init__`` 的闭包 lambda 里，
状态无法获取 → 序列化必然失败；``P`` 的 ``ix`` 在 ``restore`` 中被忽略 →
``P(..., ix=2)`` 恢复后变回 ``ix=1``（管道插入位置静默错位）。
"""

import pytest

from vools.functional import Box, P, Pipe
from vools.functional.pipe_ops import Ops
from vools.serialize.backends.json_backend import JsonBackend
from vools.serialize.backends.pickle_backend import PickleBackend
from vools.serialize.callable import (
    _HANDLERS,
    DecoratorHandler,
    FunctionalHandler,
    deserialize_callable,
    get_handler,
    serialize_callable,
)


def module_fn(x):
    return x * 10


def add_fn(x, y):
    return x + y


def add3(x, a, b):
    return x + a + b


@pytest.fixture(autouse=True)
def _snapshot_handlers():
    snapshot = list(_HANDLERS)
    yield
    _HANDLERS[:] = snapshot


def _roundtrip(obj, backend):
    name, state = serialize_callable(obj, backend)
    return name, deserialize_callable(name, state, backend)


class TestHandlerSelection:
    """BUG-450：函数式对象必须由 FunctionalHandler 认领。"""

    @pytest.mark.parametrize("obj", [Box(1), Pipe(module_fn), P(module_fn)])
    def test_claimed_by_functional(self, obj):
        assert isinstance(get_handler(obj), FunctionalHandler)

    def test_decorated_function_still_decorator_handler(self):
        import functools

        def deco(fn):
            @functools.wraps(fn)
            def wrapper(*a, **k):
                return fn(*a, **k)
            return wrapper

        @deco
        def target(x):
            return x

        assert isinstance(get_handler(target), DecoratorHandler)

    def test_ops_not_claimed(self):
        assert get_handler(Ops) is None


class TestBoxRoundtrip:
    @pytest.mark.parametrize("backend", [PickleBackend(), JsonBackend()])
    def test_type_and_value(self, backend):
        handler, restored = _roundtrip(Box(42), backend)
        assert handler == "FunctionalHandler"
        assert isinstance(restored, Box)
        assert restored.run(lambda v: v) == 42


class TestPRoundtrip:
    @pytest.mark.parametrize("backend", [PickleBackend(), JsonBackend()])
    def test_type_and_pipe_behaviour(self, backend):
        handler, restored = _roundtrip(P(module_fn), backend)
        assert handler == "FunctionalHandler"
        assert isinstance(restored, P)
        assert (3 | restored) == 30

    @pytest.mark.parametrize("backend", [PickleBackend(), JsonBackend()])
    def test_args_preserved(self, backend):
        _, restored = _roundtrip(P(add_fn, 1), backend)
        assert (5 | restored) == 6

    @pytest.mark.parametrize("backend", [PickleBackend(), JsonBackend()])
    def test_ix_preserved(self, backend):
        """BUG-451：ix 不丢失。"""
        _, restored = _roundtrip(P(add_fn, ix=2), backend)
        assert restored.ix == 2


class TestPipeRoundtrip:
    @pytest.mark.parametrize("backend", [PickleBackend(), JsonBackend()])
    def test_type_preserved(self, backend):
        handler, restored = _roundtrip(Pipe(module_fn), backend)
        assert handler == "FunctionalHandler"
        assert isinstance(restored, Pipe)

    def test_raw_func_preserved(self):
        _, restored = _roundtrip(Pipe(module_fn), JsonBackend())
        assert restored.raw_func is module_fn

    def test_partial_args_preserved(self):
        # add3 是模块级函数（局部函数的 qualname 含 <locals>，无法生成引用）
        _, restored = _roundtrip(Pipe(add3, 1, 2), JsonBackend())
        assert restored.args == (1, 2)

    def test_lambda_pipe_fails_loudly(self):
        """lambda 不可 pickle —— 必须是响亮失败而非静默错值。"""
        with pytest.raises(Exception):
            serialize_callable(Pipe(lambda x: x + 1), PickleBackend())
