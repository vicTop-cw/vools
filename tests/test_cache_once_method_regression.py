# -*- coding: utf-8 -*-
"""回归测试：@once 支持实例方法（BUG-382）。

`_OnceWrapper` 是普通可调用对象、**没有实现 `__get__`**，因此：

    class A:
        @once
        def compute(self): ...
    A().compute()
    # TypeError: A.compute() missing 1 required positional argument: 'self'

即 `@once` 用在实例方法上完全不可用（文档只把「函数/类」列为对象，但方法是
最常见的「只执行一次」场景，且同类 `memorize` 明确支持方法）。

修复：为 `_OnceWrapper` 增加描述符协议 `__get__`，按**实例**缓存结果
（`weakref.WeakKeyDictionary`，实例回收后缓存自动释放，不会强引用泄漏）；
支持 `force=True`；不可弱引用的实例退化为不缓存。类访问 `Cls.method` 仍返回
包装器本身。

普通函数（全局只执行一次）、类装饰（单例）、`force`、异常不缓存等既有语义
保持不变。
"""

import gc
import weakref

import pytest

from vools.cache.once import once


class TestMethodDecoration:
    def test_method_runs_once_per_instance(self):
        class A:
            def __init__(self, n):
                self.n = n
                self.calls = 0

            @once
            def compute(self):
                self.calls += 1
                return f'A{self.n}-{self.calls}'

        a1, a2 = A(1), A(2)
        # 修复前：TypeError: missing 1 required positional argument: 'self'
        assert a1.compute() == 'A1-1'
        assert a1.compute() == 'A1-1'
        assert a2.compute() == 'A2-1'
        assert a1.calls == 1
        assert a2.calls == 1

    def test_method_force(self):
        class A:
            def __init__(self):
                self.calls = 0

            @once
            def compute(self):
                self.calls += 1
                return self.calls

        a = A()
        assert a.compute() == 1
        assert a.compute(force=True) == 2
        assert a.compute() == 2

    def test_class_access_returns_wrapper(self):
        class A:
            @once
            def compute(self):
                return 1

        assert hasattr(A.__dict__['compute'], '__call__')
        assert A.__dict__['compute'].__class__.__name__ == '_OnceWrapper'

    def test_instance_cache_released(self):
        class B:
            @once
            def m(self):
                return 1

        b = B()
        b.m()
        ref = weakref.ref(b)
        del b
        gc.collect()
        assert ref() is None

    def test_exception_not_cached_in_method(self):
        class C:
            def __init__(self):
                self.calls = 0

            @once
            def boom(self):
                self.calls += 1
                raise ValueError('x')

        c = C()
        for _ in range(2):
            with pytest.raises(ValueError):
                c.boom()
        assert c.calls == 2


class TestFunctionSemanticsUnchanged:
    def test_function_runs_once(self):
        calls = []

        @once
        def f():
            calls.append(1)
            return 42

        assert f() == 42
        assert f() == 42
        assert len(calls) == 1

    def test_function_force(self):
        calls = []

        @once
        def f():
            calls.append(1)
            return len(calls)

        assert f() == 1
        assert f(force=True) == 2

    def test_function_exception_retried(self):
        calls = []

        @once
        def f():
            calls.append(1)
            raise ValueError('boom')

        for _ in range(2):
            with pytest.raises(ValueError):
                f()
        assert len(calls) == 2


class TestClassDecorationUnchanged:
    def test_singleton(self):
        @once
        class Single:
            def __init__(self, v):
                self.v = v

        assert Single(1) is Single(2)

    def test_force_default_validation(self):
        with pytest.raises(TypeError):
            once(force_default='yes')