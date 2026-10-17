# -*- coding: utf-8 -*-
"""测试 vools.decorators.shotcut — 快捷装饰器集合。"""

import time
import warnings
import pytest

from vools.decorators.shotcut import (
    timeit, safe, throttle, debounce, singleton, deprecated,
    conditional, with_context, with_timeout, validate,
    rate_limit, cache_with_ttl, hybrid_method, classproperty, enumize,
)

__all__ = ["TestTimeit", "TestSafe", "TestThrottle", "TestDebounce",
           "TestSingleton", "TestDeprecated", "TestConditional",
           "TestWithContext", "TestWithTimeout", "TestValidate",
           "TestRateLimit", "TestCacheWithTTL", "TestHybridMethod",
           "TestClassProperty", "TestEnumize", "TestImport"]


class _FakeCM:
    """fake context manager"""
    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *a):
        self.exited = True


class TestTimeit:
    """timeit 测试。"""

    def test_without_logger(self, capsys):
        @timeit
        def f():
            return 42
        assert f() == 42
        out = capsys.readouterr().out
        assert "执行时间" in out

    def test_with_logger(self):
        class L:
            def __init__(self):
                self.msgs = []
            def info(self, msg):
                self.msgs.append(msg)
        l = L()

        @timeit(logger=l)
        def f():
            return 1
        assert f() == 1
        assert len(l.msgs) == 1

    def test_used_as_decorator(self):
        @timeit()
        def f():
            return "hi"
        assert f() == "hi"


class TestSafe:
    """safe 测试。"""

    def test_no_error(self):
        @safe
        def f():
            return "ok"
        assert f() == "ok"

    def test_with_default(self):
        @safe(default=-1)
        def f():
            raise ValueError("boom")
        assert f() == -1

    def test_without_default(self):
        @safe
        def f():
            raise ValueError("boom")
        result = f()
        assert result[0] is None
        assert isinstance(result[1], ValueError)

    def test_catch_specific_exception(self):
        @safe(exceptions=(KeyError,))
        def f():
            raise KeyError("missing")
        result = f()
        assert result[0] is None

    def test_not_catch(self):
        @safe(exceptions=(KeyError,), default="x")
        def f():
            raise ValueError("nope")
        with pytest.raises(ValueError):
            f()


class TestThrottle:
    """throttle 测试。"""

    def test_throttle_blocks(self):
        calls = [0]

        @throttle(0.5)
        def f():
            calls[0] += 1
            return calls[0]

        assert f() == 1
        assert f() is None  # throttled
        assert calls[0] == 1

    def test_throttle_passes_after_interval(self):
        calls = [0]

        @throttle(0.01)
        def f():
            calls[0] += 1
            return calls[0]

        f()
        time.sleep(0.02)
        assert f() == 2


class TestDebounce:
    """debounce 测试。"""

    def test_debounce_delays(self):
        calls = [0]

        @debounce(0.01)
        def f():
            calls[0] += 1
            return calls[0]

        f()
        f()
        f()
        assert calls[0] == 0  # not yet executed
        time.sleep(0.05)
        assert calls[0] == 1


class TestSingleton:
    """singleton 测试。"""

    def test_same_instance(self):
        @singleton
        class A:
            pass
        a1 = A()
        a2 = A()
        assert a1 is a2


class TestDeprecated:
    """deprecated 测试。"""

    def test_warns(self):
        @deprecated("use B")
        def f():
            return "hi"
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert f() == "hi"
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)

    def test_no_reason(self):
        @deprecated()
        def f():
            return 1
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            f()
            assert "已弃用" in str(w[0].message)


class TestConditional:
    """conditional 测试。"""

    def test_skip(self):
        @conditional(lambda x: x > 0, action="skip")
        def f(x):
            return x
        assert f(1) is None
        assert f(-1) == -1

    def test_warn(self):
        @conditional(lambda x: True, action="warn")
        def f(x):
            return x
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            assert f(1) == 1
            assert len(w) == 1


class TestWithContext:
    """with_context 测试。"""

    def test_runs(self):
        cm = _FakeCM()

        @with_context(cm)
        def f():
            return "hi"
        assert f() == "hi"
        assert cm.entered is True
        assert cm.exited is True


class TestWithTimeout:
    """with_timeout 测试。"""

    def test_fast(self):
        @with_timeout(1)
        def f():
            return "ok"
        assert f() == "ok"

    def test_timeout_raises(self):
        @with_timeout(0.1)
        def f():
            time.sleep(1)
            return "ok"
        with pytest.raises(TimeoutError):
            f()

    def test_exception_propagates(self):
        @with_timeout(1)
        def f():
            raise ValueError("boom")
        with pytest.raises(ValueError):
            f()


class TestValidate:
    """validate 测试。"""

    def test_valid(self):
        @validate(x=lambda v: v > 0)
        def f(x):
            return x
        assert f(1) == 1

    def test_invalid(self):
        @validate(x=lambda v: v > 0)
        def f(x):
            return x
        with pytest.raises(ValueError):
            f(0)

    def test_missing_param(self):
        @validate(y=lambda v: v > 0)
        def f(x):
            return x
        assert f(1) == 1


class TestRateLimit:
    """rate_limit 测试。"""

    def test_limit_hit(self):
        calls = [0]

        @rate_limit(2, 60)
        def f():
            calls[0] += 1
            return calls[0]

        assert f() == 1
        assert f() == 2
        assert f() is None  # rate limited
        assert calls[0] == 2

    def test_reset(self):
        calls = [0]

        @rate_limit(1, 0.01)
        def f():
            calls[0] += 1
            return calls[0]

        assert f() == 1
        assert f() is None
        time.sleep(0.02)
        assert f() == 2

    def test_with_logger(self):
        class L:
            def __init__(self):
                self.msgs = []
            def info(self, m):
                self.msgs.append(m)
            def warning(self, m):
                self.msgs.append(m)
        l = L()

        @rate_limit(100, 60, logger=l)
        def f():
            return "hi"
        assert f() == "hi"
        assert len(l.msgs) >= 2


class TestCacheWithTTL:
    """cache_with_ttl 测试。"""

    def test_caches(self):
        calls = [0]

        @cache_with_ttl(10)
        def f(x):
            calls[0] += 1
            return calls[0]

        assert f(1) == 1
        assert f(1) == 1  # cached
        assert calls[0] == 1

    def test_diff_args(self):
        calls = [0]

        @cache_with_ttl(10)
        def f(x):
            calls[0] += 1
            return calls[0]

        assert f(1) == 1
        assert f(2) == 2
        assert calls[0] == 2

    def test_expires(self):
        calls = [0]

        @cache_with_ttl(0.01)
        def f(x):
            calls[0] += 1
            return calls[0]

        f(1)
        time.sleep(0.02)
        f(1)
        assert calls[0] == 2


class TestHybridMethod:
    """hybrid_method 测试。"""

    def test_instance_call(self):
        class A:
            @hybrid_method
            def foo(self, *a, **kw):
                return "instance", self, a, kw
        a = A()
        result = a.foo(1, x=2)
        assert result[0] == "instance"

    def test_class_call(self):
        class A:
            @hybrid_method
            def foo(cls, *a, **kw):
                return "class", cls, a, kw
        result = A.foo(A)
        assert result[0] == "class"


class TestClassProperty:
    """classproperty 测试。"""

    def test_property(self):
        class A:
            @classproperty
            def name(cls):
                return "A"
        assert A.name.fget(A) == "A"


class TestEnumize:
    """enumize 测试。"""

    def test_values(self):
        @enumize("red", "green", "blue")
        class C:
            pass
        assert C.RED == 0
        assert C.GREEN == 1
        assert C.BLUE == 2
        assert C._values == ("red", "green", "blue")


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.decorators.shotcut import __all__
        assert "timeit" in __all__
        assert "safe" in __all__
        assert "throttle" in __all__
        assert "debounce" in __all__
        assert "singleton" in __all__
        assert "deprecated" in __all__
        assert "conditional" in __all__
        assert "with_context" in __all__
        assert "with_timeout" in __all__
        assert "validate" in __all__
        assert "rate_limit" in __all__
        assert "cache_with_ttl" in __all__
        assert "hybrid_method" in __all__
        assert "classproperty" in __all__
        assert "enumize" in __all__
