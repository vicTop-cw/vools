# -*- coding: utf-8 -*-
"""测试 vools.serialize.callable.functional_handler。"""

import pytest
from vools.serialize.callable.functional_handler import FunctionalHandler
from vools.functional import Pipe, Ops, P, Box

__all__ = ["TestCanHandle", "TestGetState", "TestRestore", "TestDo",
           "TestImport"]


def _ident(x):
    return x


class TestCanHandle:
    """can_handle 测试。"""

    def test_pipe(self):
        h = FunctionalHandler()
        assert h.can_handle(Pipe(_ident))

    def test_ops(self):
        h = FunctionalHandler()
        assert h.can_handle(Ops())

    def test_p(self):
        h = FunctionalHandler()
        assert h.can_handle(P(_ident, 1, 2))

    def test_box(self):
        h = FunctionalHandler()
        assert h.can_handle(Box(42))

    def test_other(self):
        h = FunctionalHandler()
        assert not h.can_handle(42)
        assert not h.can_handle("str")
        assert not h.can_handle(object())

    def test_handles_types(self):
        assert 'Pipe' in FunctionalHandler._handles_types
        assert 'Ops' in FunctionalHandler._handles_types
        assert 'P' in FunctionalHandler._handles_types
        assert 'Box' in FunctionalHandler._handles_types


class TestGetState:
    """get_state 测试。"""

    def test_pipe(self):
        h = FunctionalHandler()
        obj = Pipe(_ident)
        st = h.get_state(obj)
        assert st["type_name"] == "Pipe"
        # BUG-451：raw_func 现在以可 pickle 的 {'module','qualname'} 引用保存
        # （旧格式把闭包 lambda 存在 'func' 里，lambda 不可 pickle → Pipe 永远
        # 无法序列化）；_ident 是模块级函数，因此应生成引用。
        assert "raw_func_ref" in st
        assert st["raw_func_ref"]["qualname"].endswith("_ident")
        assert st["args"] == ()

    def test_ops(self):
        h = FunctionalHandler()
        st = h.get_state(Ops())
        assert st["type_name"] == "Ops"

    def test_p(self):
        h = FunctionalHandler()
        obj = P(_ident, 1, 2, a=3)
        st = h.get_state(obj)
        assert st["type_name"] == "P"
        # BUG-451：func 改存引用（JSON 后端可序列化），模块级函数应生成 ref
        assert st["func_ref"]["qualname"].endswith("_ident")
        assert st["args"] == (1, 2)
        assert st["kwargs"] == {"a": 3}
        assert st["ix"] == 1

    def test_box(self):
        h = FunctionalHandler()
        obj = Box("hello")
        st = h.get_state(obj)
        assert st["type_name"] == "Box"
        assert st["value"] == "hello"


class TestRestore:
    """restore 测试。"""

    def test_pipe_with_func(self):
        h = FunctionalHandler()
        r = h.restore({"type_name": "Pipe", "func": _ident})
        assert isinstance(r, Pipe)

    def test_pipe_with_raw_func(self):
        # BUG-451：raw_func 为可调用对象时恢复为 Pipe（旧实现原样返回对象，
        # 类型丢失）。非可调用值请见 test_pipe_with_bad_raw_func。
        h = FunctionalHandler()
        r = h.restore({"type_name": "Pipe", "raw_func": _ident})
        assert isinstance(r, Pipe)

    def test_pipe_with_bad_raw_func(self):
        h = FunctionalHandler()
        with pytest.raises(TypeError):
            h.restore({"type_name": "Pipe", "raw_func": "raw"})

    def test_ops(self):
        h = FunctionalHandler()
        r = h.restore({"type_name": "Ops"})
        assert r is Ops

    def test_p(self):
        h = FunctionalHandler()
        r = h.restore({"type_name": "P", "func": _ident, "args": (1,), "kwargs": {}})
        assert isinstance(r, P)

    def test_box(self):
        h = FunctionalHandler()
        r = h.restore({"type_name": "Box", "value": 42})
        assert isinstance(r, Box)

    def test_unknown(self):
        h = FunctionalHandler()
        with pytest.raises(ValueError):
            h.restore({"type_name": "Unknown"})


class TestDo:
    """do 方法测试。"""

    def test_default(self):
        h = FunctionalHandler()
        r = h.do(lambda x: x)
        assert r is h

    def test_pre(self):
        h = FunctionalHandler()
        r = h.do(lambda x: x, pre_f=lambda x: "pre")
        assert r is h

    def test_sub(self):
        h = FunctionalHandler()
        called = []
        r = h.do(lambda x: x, sub_f=lambda x: called.append(x))
        assert r is h
        assert called == [h]


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.serialize.callable.functional_handler import __all__
        assert "FunctionalHandler" in __all__
