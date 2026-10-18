# -*- coding: utf-8 -*-
"""测试 vools.decorators.curry_core。

重点覆盖 CurryDescriptor.__get__ 对实例首参名的处理（BUG-183）：
柯里化实例方法无论首参名是 'self'/'this'/任意名，实例访问后首个参数
都应已被 __get__ 消费并从 required_args/params 中剔除。
"""

import pytest

from vools.decorators.curry_core import curry, Curried, is_curried

__all__ = [
    "TestDescriptorSelfName", "TestDescriptorThisName",
    "TestMultiStepCurry", "TestDescriptorClassmethod", "TestCurryErrors",
]


class TestDescriptorSelfName:
    """首参名为 self 的常规柯里化实例方法。"""

    def test_call_direct(self):
        class Foo:
            def __init__(self, v):
                self.v = v

            @curry
            def bar(self, x, y):
                return self.v + x + y

        assert Foo(1).bar(2, 3) == 6

    def test_call_step(self):
        class Foo:
            def __init__(self, v):
                self.v = v

            @curry
            def bar(self, x, y):
                return self.v + x + y

        assert Foo(1).bar(2)(3) == 6

    def test_bound_args_omits_self(self):
        class Foo:
            def __init__(self, v):
                self.v = v

            @curry
            def bar(self, x, y):
                return self.v + x + y

        got = Foo(1).bar(2)
        assert isinstance(got, Curried)
        assert 'self' not in got.bound_args
        assert got.is_ready is False


class TestDescriptorThisName:
    """首参名不是 self（如 'this'）时 BUG-183 回归。"""

    def test_call_direct(self):
        class Foo:
            def __init__(self, v):
                self.v = v

            @curry
            def bar(this, x, y):
                return this.v + x + y

        assert Foo(1).bar(2, 3) == 6

    def test_call_step(self):
        class Foo:
            def __init__(self, v):
                self.v = v

            @curry
            def bar(this, x, y):
                return this.v + x + y

        assert Foo(1).bar(2)(3) == 6

    def test_bound_args_omits_this(self):
        class Foo:
            def __init__(self, v):
                self.v = v

            @curry
            def bar(this, x, y):
                return this.v + x + y

        got = Foo(1).bar(2)
        assert isinstance(got, Curried)
        assert 'this' not in got.bound_args
        assert 'this' not in got.required_args

    def test_three_args(self):
        class Foo:
            def __init__(self, v):
                self.v = v

            @curry
            def baz(this, x, y, z):
                return this.v + x + y + z

        assert Foo(1).baz(2)(3)(4) == 10
        assert Foo(1).baz(2, 3)(4) == 10


class TestMultiStepCurry:
    """多步柯里化与关键字参数。"""

    def test_mixed(self):
        @curry
        def f(a, b, c):
            return a + b + c

        assert f(1)(2)(3) == 6
        assert f(1, 2)(3) == 6
        assert f(1)(c=3)(2) == 6

    def test_kwargs_only(self):
        @curry
        def f(a, b=1):
            return a + b

        assert f(a=2) == 3
        assert f(2) == 3


class TestDescriptorClassmethod:
    """classmethod 委托的柯里化。"""

    def test_classmethod_delegation(self):
        class Foo:
            @classmethod
            @curry
            def cm(cls, x, y):
                return cls.__name__ + str(x + y)

        assert Foo.cm(1)(2) == "Foo3"


class TestCurryErrors:
    """柯里化错误路径。"""

    def test_cannot_curry_curried(self):
        @curry
        def f(a):
            return a

        with pytest.raises(TypeError):
            curry(f)

    def test_too_many_positional(self):
        @curry
        def f(a, b):
            return a + b

        with pytest.raises(TypeError):
            f(1, 2, 3)

    def test_is_curried(self):
        @curry
        def f(a):
            return a

        assert is_curried(f)
        assert not is_curried(lambda x: x)