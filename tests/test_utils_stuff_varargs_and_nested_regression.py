# -*- coding: utf-8 -*-
"""回归测试：Stuff 执行 *args/**kwargs + 嵌套函数不再误判为方法（BUG-339/340）。

【BUG-339】`Stuff._evalate` 使**任何带可变参数的函数都无法执行**：
- 求值阶段 `compute(v): return v()` 假定每个绑定值都是无参 provider，但
  `__call__` 用 `_trans` 把实参包成 lambda，`*args` 绑定为「lambda 列表」、
  `**kwargs` 绑定为「lambda 字典」→ `'list'/'dict' object is not callable`；
- 装配阶段按形参名塞 kwargs → `f(a, *rest)` 得
  `got multiple values for argument 'a'`，`**kw` 则把形参名当真实键。
修复：`_resolve` 逐元素解析容器；按**签名顺序**装配（`*args` 展开为位置实参、
`**kwargs` 合并进关键字）。

【BUG-340】`curry_core.curry` 用 `'.' in func.__qualname__` 判定"方法"，
**嵌套/局部函数**（`outer.<locals>.f`）被误包成 `CurryDescriptor` →
`stuff(...)()` 抛 `'CurryDescriptor' object has no attribute 'bound_args'`。
修复：仅当 qualname 倒数第二段**不是 `<locals>`** 时才走描述符
（嵌套类的方法 `outer.<locals>.C.m` 仍正确走描述符）。
"""

import pytest

from vools.decorators.curry_core import Curried, CurryDescriptor, curry
from vools.utils.stuff import stuff


# —— BUG-339：模块级可变参数函数（任务函数需可被正常调用） ——
@stuff
def _only_varargs(*a):
    return a


@stuff
def _first_then_varargs(a, *rest):
    return (a, rest)


@stuff
def _only_varkw(**kw):
    return kw


@stuff
def _mixed(a, *args, **kw):
    return (a, args, kw)


class TestVarPositional:
    def test_only_varargs(self):
        # 修复前：StuffExecutionError: 'list' object is not callable
        assert _only_varargs(1, 2)() == (1, 2)
        assert _only_varargs(1)() == (1,)
        assert _only_varargs() == ()

    def test_fixed_then_varargs(self):
        # 修复前：got multiple values for argument 'a'
        assert _first_then_varargs(1, 2, 3)() == (1, (2, 3))
        assert _first_then_varargs(1)() == (1, ())

    def test_provided_varargs_list(self):
        @stuff
        def f(*a):
            return a

        f.provide(lambda: [7, 8, 9], name='a')
        assert f() == (7, 8, 9)


class TestVarKeyword:
    def test_only_varkw(self):
        # 修复前：'dict' object is not callable
        assert _only_varkw(a=1)() == {'a': 1}
        assert _only_varkw(a=1, b=2)() == {'a': 1, 'b': 2}

    def test_provided_varkw_dict(self):
        @stuff
        def f(**kw):
            return kw

        f.provide(lambda: {'x': 10, 'y': 20}, name='kw')
        assert f() == {'x': 10, 'y': 20}


class TestMixedSignature:
    def test_fixed_varargs_varkw(self):
        assert _mixed(1, 2, x=3)() == (1, (2,), {'x': 3})
        assert _mixed(1)() == (1, (), {})


class TestRegularFunctionsUnchanged:
    def test_plain(self):
        @stuff
        def f(a, b):
            return a + b

        assert f(1, 2)() == 3

    def test_providers(self):
        @stuff
        def f(a, b, c):
            return a + b + c

        f.provide(lambda: 1, name='a')
        f.provide(lambda: 2, name='b')
        f.provide(lambda: 3, name='c')
        assert f() == 6

    def test_class(self):
        @stuff
        class Calc:
            def __init__(self, a, b):
                self.a, self.b = a, b

            def total(self):
                return self.a + self.b

        Calc.provide(lambda: 3, name='a')
        Calc.provide(lambda: 4, name='b')
        assert Calc().total() == 7

    def test_defaults_and_kwargs(self):
        @stuff
        def f(a, b=10):
            return a + b

        assert f(1)() == 11
        assert f(1, 2)() == 3

        @stuff
        def g(a, b):
            return a - b

        assert g(b=2, a=5)() == 3

    def test_positional_only(self):
        @stuff
        def f(a, b, /):
            return a * b

        assert f(3, 4)() == 12


class TestNestedFunctionNotMethod:
    """BUG-340：嵌套/局部函数必须走 Curried，而不是 CurryDescriptor。"""

    def test_nested_function_stuff(self):
        def make():
            def local_fn(*a):
                return a

            return stuff(local_fn)

        s = make()
        assert isinstance(s.curried, Curried)
        assert s() == ()
        assert s(1, 2)() == (1, 2)

    def test_nested_plain_function(self):
        def make():
            def add(a, b):
                return a + b

            return stuff(add)

        assert make()(1, 2)() == 3

    def test_nested_curry_returns_curried(self):
        def make():
            @curry
            def f(a, b):
                return a - b

            return f

        f = make()
        assert isinstance(f, Curried)
        # 普通 curry 的约定：参数齐了直接求值（无需尾随 ()）；区别于 Stuff
        assert f(5)(3) == 2
        assert f(5, 3) == 2

    def test_top_level_function_not_descriptor(self):
        assert isinstance(_only_varargs.curried, Curried)


class TestClassMethodsStillDescriptors:
    """BUG-340 的修复不能破坏方法：类内方法仍应走 CurryDescriptor。"""

    def test_top_level_class_method(self):
        class C:
            @curry
            def m(self, a, b):
                return a + b

        assert isinstance(C.__dict__['m'], CurryDescriptor)
        assert C().m(1, 2) == 3

    def test_nested_class_method(self):
        def make():
            class Inner:
                @curry
                def m(self, a, b):
                    return a * b

            return Inner

        Inner = make()
        # 嵌套类的方法 qualname 为 'make.<locals>.Inner.m'，仍应是描述符
        assert isinstance(Inner.__dict__['m'], CurryDescriptor)
        assert Inner().m(3, 4) == 12