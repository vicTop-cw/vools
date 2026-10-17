# -*- coding: utf-8 -*-
"""测试 vools.oop.mixer。"""

import pytest
from vools.oop.mixer import Mixer, Mixer_, attr_Enum

__all__ = ["TestAttrEnum", "TestMixerInit", "TestPriority", "TestDir",
           "TestPickle", "TestDo", "TestGetAttr", "TestAddExtraCode",
           "TestRemoveExtraCode", "TestImport"]


class A:
    def foo(self):
        return "A.foo"
    x = 1


class B:
    def foo(self):
        return "B.foo"
    def bar(self):
        return "B.bar"
    x = 2


class TestAttrEnum:
    """attr_Enum 测试。"""

    def test_values(self):
        assert attr_Enum.WITH_NAME == 1
        assert attr_Enum.WITH_CLS_NAME == 2
        assert attr_Enum.WITH_STR_VALUE == 4

    def test_do(self):
        called = []
        e = attr_Enum.WITH_NAME
        r = e.do(lambda x: called.append(x))
        assert r is e
        assert called == [e]

    def test_do_pre(self):
        called = []
        e = attr_Enum.WITH_NAME
        e.do(lambda x: called.append("f"), pre_f=lambda x: called.append("pre"))
        # pre_f 返回 None 作为 rs，所以 f 收到 None
        assert called == ["pre", "f"]

    def test_do_sub(self):
        called = []
        e = attr_Enum.WITH_NAME
        e.do(lambda x: called.append("f"), sub_f=lambda x: called.append("sub"))
        assert called == ["f", "sub"]


class TestMixerInit:
    """Mixer 初始化测试。"""

    def test_empty(self):
        m = Mixer()
        assert m._objs == []
        assert m.dir_tuple is not None

    def test_two_objs(self):
        m = Mixer(A(), B())
        assert len(m._objs) == 2
        assert m._priority_map != {}


class TestPriority:
    """优先级控制测试。"""

    def test_update_priority(self):
        a = A()
        b = B()
        m = Mixer(a, b)
        m.update_priority(a, 100)
        assert m._priority_map[id(a)] == 100

    def test_update_priority_not_in(self):
        m = Mixer()
        with pytest.raises(ValueError):
            m.update_priority(A(), 5)

    def test_add_object(self):
        m = Mixer()
        m.add_object(A())
        assert len(m._objs) == 1

    def test_add_object_with_priority(self):
        m = Mixer()
        m.add_object(A(), priority=10)
        assert m._priority_map == {id(m._objs[0]): 10}

    def test_remove_object(self):
        a = A()
        m = Mixer(a)
        m.remove_object(a)
        assert a not in m._objs
        assert id(a) not in m._priority_map

    def test_remove_object_not_in(self):
        m = Mixer(A())
        m.remove_object(B())
        assert len(m._objs) == 1

    def test_get_priority_objs(self):
        a = A()
        b = B()
        m = Mixer(a, b)
        assert m.get_priority_objs() == [a, b]

    def test_get_priority_objs_without_map(self):
        m = Mixer()
        m._objs = [A()]
        result = m.get_priority_objs()
        assert len(result) == 1


class TestDir:
    """__dir__ 测试。"""

    def test_basic(self):
        m = Mixer(A())
        d = m.__dir__()
        assert len(d) > 0

    def test_dir_tuple_prop(self):
        m = Mixer(A())
        assert m.dir_tuple is not None


class TestPickle:
    """__getstate__/__setstate__ 测试。"""

    def test_getstate(self):
        m = Mixer(A())
        st = m.__getstate__()
        assert '_objs' in st
        assert '_priority_map' in st
        assert '_attr_code' in st

    def test_setstate(self):
        m = Mixer()
        m.__setstate__({'_objs': [A()], '_priority_map': {1: 0}, '_attr_code': {}})
        assert len(m._objs) == 1
        assert m.dir_tuple is not None


class TestDo:
    """do 方法测试。"""

    def test_default(self):
        m = Mixer(A())
        r = m.do(lambda x: x)
        assert r is m

    def test_pre(self):
        m = Mixer(A())
        r = m.do(lambda x: x, pre_f=lambda x: "pre")
        assert r is m

    def test_sub(self):
        m = Mixer(A())
        called = []
        r = m.do(lambda x: x, sub_f=lambda x: called.append(x))
        assert r is m
        assert called == [m]


class TestGetAttr:
    """__getattr__ 测试。"""

    def test_attr_from_a(self):
        m = Mixer(A(), B())
        assert m.x == 1

    def test_attr_from_b_only(self):
        m = Mixer(A(), B())
        assert m.bar() == "B.bar"

    def test_attr_missing(self):
        m = Mixer()
        with pytest.raises(AttributeError):
            _ = m.nonexistent


class TestAddExtraCode:
    """add_extra_code 测试。"""

    def test_result_shell(self):
        m = Mixer(A())
        m.add_extra_code("foo", result_shell=lambda r: r + "!")
        assert m.foo() == "A.foo!"

    def test_func_shell(self):
        m = Mixer(A())
        m.add_extra_code("foo", func_shell=lambda f: lambda *a, **kw: f(*a, **kw) + "!")
        assert m.foo() == "A.foo!"

    def test_partial_args(self):
        class C:
            def foo(self, a, b):
                return a + b
        m = Mixer(C())
        m.add_extra_code("foo", partial_args=(1,))
        assert m.foo(2) == 3

    def test_partial_kwargs(self):
        class C:
            def foo(self, a, b=0):
                return a + b
        m = Mixer(C())
        m.add_extra_code("foo", partial_kwargs={"b": 5})
        assert m.foo(1) == 6

    def test_empty_all(self):
        m = Mixer(A())
        with pytest.raises(ValueError):
            m.add_extra_code("foo")

    def test_bad_func_shell(self):
        m = Mixer(A())
        with pytest.raises(TypeError):
            m.add_extra_code("foo", func_shell=123)

    def test_bad_result_shell(self):
        m = Mixer(A())
        with pytest.raises(TypeError):
            m.add_extra_code("foo", result_shell=123)

    def test_bad_partial_args(self):
        m = Mixer(A())
        with pytest.raises(TypeError):
            m.add_extra_code("foo", partial_args="not_a_list")


class TestRemoveExtraCode:
    """remove_extra_code 测试。"""

    def test_remove(self):
        m = Mixer(A())
        m.add_extra_code("foo", result_shell=lambda r: r + "!")
        assert m.foo() == "A.foo!"
        m.remove_extra_code("foo")
        assert m.foo() == "A.foo"


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.oop.mixer import __all__
        assert "Mixer" in __all__
        assert "Mixer_" in __all__
        assert "attr_Enum" in __all__
