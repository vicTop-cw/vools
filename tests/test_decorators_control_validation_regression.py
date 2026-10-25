# -*- coding: utf-8 -*-
"""回归测试：excepts/silent 参数校验（BUG-477）。

修复前零校验：

    @excepts("x", handler)          # 直到**异常发生时**才抛
                                    # "catching classes that do not inherit from BaseException…"
    @excepts(ValueError, 123)       # 异常时抛 "'int' object is not callable"
    silent(123)                     # 返回 wrapper，把 123 当函数调

修复后装饰期即拒绝：exc_type 必须是异常类（或非空异常类元组），handler 必须
可调用，silent 的 fn 必须可调用或 None。
"""

import pytest

import vools.decorators.control as ctl


class TestExceptsValidation:
    @pytest.mark.parametrize("bad", ["x", None, 123, object()])
    def test_bad_exc_type(self, bad):
        with pytest.raises(TypeError) as ei:
            ctl.excepts(bad, lambda e: None)
        assert "exc_type" in str(ei.value)

    def test_empty_tuple(self):
        with pytest.raises(TypeError):
            ctl.excepts((), lambda e: None)

    def test_tuple_with_non_exception(self):
        with pytest.raises(TypeError) as ei:
            ctl.excepts((ValueError, "x"), lambda e: None)
        assert "exc_type" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "x", [1]])
    def test_bad_handler(self, bad):
        with pytest.raises(TypeError) as ei:
            ctl.excepts(ValueError, bad)
        assert "handler" in str(ei.value)

    def test_error_at_decoration_not_at_raise(self):
        """修复前是"异常发生时才炸"，现在装饰期就拦。"""
        with pytest.raises(TypeError):
            ctl.excepts("x", lambda e: None)


class TestExceptsSemantics:
    def test_handles_matching_exception(self):
        @ctl.excepts(ValueError, lambda e: f"handled:{e}")
        def f(x):
            if x < 0:
                raise ValueError("neg")
            return x

        assert f(1) == 1
        assert f(-1) == "handled:neg"

    def test_other_exceptions_propagate(self):
        @ctl.excepts(ValueError, lambda e: "h")
        def f():
            raise KeyError("k")

        with pytest.raises(KeyError):
            f()

    def test_exception_tuple(self):
        @ctl.excepts((ValueError, KeyError), lambda e: "tuple-handled")
        def f():
            raise KeyError("k")

        assert f() == "tuple-handled"


class TestSilentValidation:
    @pytest.mark.parametrize("bad", [123, "x", [1], 1.5])
    def test_non_callable_fn(self, bad):
        with pytest.raises(TypeError) as ei:
            ctl.silent(bad)
        assert "fn" in str(ei.value)

    def test_none_returns_decorator(self):
        assert callable(ctl.silent())
        assert callable(ctl.silent(default=1))


class TestSilentSemanticsUnchanged:
    def test_returns_default_on_exception(self):
        @ctl.silent(default="d")
        def f():
            raise RuntimeError("boom")

        assert f() == "d"

    def test_returns_value_normally(self):
        @ctl.silent
        def f(x):
            return x * 2

        assert f(3) == 6

    def test_bare_decorator_default_none(self):
        @ctl.silent
        def f():
            raise ValueError("x")

        assert f() is None
