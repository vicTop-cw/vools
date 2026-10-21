# -*- coding: utf-8 -*-
"""tests/decorators/test_delay_curry_extra_args.py — delay_curry 多余位置参数校验（钉 BUG-254）

BUG-254: ``DelayCurried.__call__`` 对超出函数签名数量的位置参数静默接受，
不抛任何错误。例如 ``add(1, 2, 3)`` 对于 ``def add(a, b)`` 本应
``TypeError``，却返回 ``DelayCurried`` 对象。修复：在参数绑定前校验
``args_len <= bindable``，越界立即抛 ``TypeError``。
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.decorators.curry_delay import delay_curry, DelayCurried  # noqa: E402


class TestDelayCurryExtraArgsRejected:
    """多余位置参数必须抛 TypeError"""

    def test_extra_positional_single_call(self):
        @delay_curry
        def add(a, b):
            return a + b

        with pytest.raises(TypeError, match="Too many positional arguments"):
            add(1, 2, 3)

    def test_extra_positional_chain(self):
        @delay_curry
        def add(a, b):
            return a + b

        with pytest.raises(TypeError, match="Too many positional arguments"):
            add(1)(2, 3)

    def test_extra_positional_partial_then_over(self):
        @delay_curry
        def add3(a, b, c):
            return a + b + c

        partial = add3(1)
        assert isinstance(partial, DelayCurried)
        with pytest.raises(TypeError, match="Too many positional arguments"):
            partial(2, 3, 4)


class TestDelayCurryVarArgsStillAccepts:
    """带 *args 的函数应正常接受任意数量位置参数"""

    def test_varargs_accepts_many(self):
        @delay_curry
        def sum_all(*args):
            return sum(args)

        r = sum_all(1, 2, 3, 4)
        # 未空调用返回 DelayCurried；() 触发执行
        assert isinstance(r, DelayCurried)

    def test_varargs_then_execute(self):
        @delay_curry
        def concat(*args):
            return "-".join(str(a) for a in args)

        assert concat(1, 2, 3)() == "1-2-3"


class TestDelayCurryKwargsDuplicateStillRejected:
    """关键字参数重复赋值仍应抛 TypeError"""

    def test_duplicate_kwarg(self):
        @delay_curry
        def add(a, b):
            return a + b

        with pytest.raises(TypeError, match="重复赋值"):
            add(a=1)(a=2)


class TestDelayCurryValidChainUnchanged:
    """合法链式调用不受影响"""

    def test_full_chain(self):
        @delay_curry
        def add(a, b, c):
            return a + b + c

        assert add(1)(2)(3)() == 6

    def test_partial_then_full(self):
        @delay_curry
        def add(a, b, c):
            return a + b + c

        partial = add(1)
        assert isinstance(partial, DelayCurried)
        assert partial(2, 3)() == 6

    def test_kwargs_chain(self):
        @delay_curry
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

        assert greet("World")() == "Hello, World!"
        assert greet("World", greeting="Hi")() == "Hi, World!"
