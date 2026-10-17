# -*- coding: utf-8 -*-
"""测试 vools.serialize.callable.decorator_handler。"""

import functools
import pytest
from vools.serialize.callable.decorator_handler import DecoratorHandler

__all__ = ["TestCanHandle", "TestGetState", "TestRestore", "TestDo",
           "TestImport"]


def my_deco(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        return f(*a, **kw)
    wrapper._vools_decorator = "test_deco"
    return wrapper


@my_deco
def decorated_func(x):
    return x * 2


def plain_func(x):
    return x


class CallableNoCode:
    """可调用但没有 __code__ 的对象"""
    __name__ = "CallableNoCode"


class TestCanHandle:
    """can_handle 测试。"""

    def test_decorated(self):
        h = DecoratorHandler()
        assert h.can_handle(decorated_func)

    def test_plain_function(self):
        h = DecoratorHandler()
        assert not h.can_handle(plain_func)

    def test_non_callable(self):
        h = DecoratorHandler()
        assert not h.can_handle(42)

    def test_with_wrapped_only(self):
        h = DecoratorHandler()
        def inner(x):
            return x
        obj = functools.wraps(inner)(lambda x: x)
        assert h.can_handle(obj)


class TestGetState:
    """get_state 测试。"""

    def test_decorated(self):
        h = DecoratorHandler()
        st = h.get_state(decorated_func)
        assert st["name"] == "decorated_func"
        assert "__wrapped__" in st
        assert "_vools_decorator" in st
        assert "original_func" in st

    def test_no_wrapped(self):
        h = DecoratorHandler()
        obj = functools.wraps(plain_func)(lambda x: x)
        st = h.get_state(obj)
        assert "name" in st
        assert "module" in st


class TestRestore:
    """restore 测试。"""

    def test_with_original(self):
        h = DecoratorHandler()
        st = {"name": "decorated_func", "original_func": decorated_func,
              "_vools_decorator": "test_deco"}
        r = h.restore(st)
        assert r(3) == 6
        assert r._vools_decorator == "test_deco"

    def test_no_original(self):
        h = DecoratorHandler()
        with pytest.raises(ValueError):
            h.restore({"name": "unknown"})


class TestDo:
    """do 方法测试。"""

    def test_default(self):
        h = DecoratorHandler()
        r = h.do(lambda x: x)
        assert r is h

    def test_pre(self):
        h = DecoratorHandler()
        r = h.do(lambda x: x, pre_f=lambda x: "pre")
        assert r is h

    def test_sub(self):
        h = DecoratorHandler()
        called = []
        r = h.do(lambda x: x, sub_f=lambda x: called.append(x))
        assert r is h
        assert called == [h]


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.serialize.callable.decorator_handler import __all__
        assert "DecoratorHandler" in __all__
