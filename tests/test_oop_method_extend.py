# -*- coding: utf-8 -*-
"""测试 vools.oop.method_extend。"""

import pytest
from vools.oop.method_extend import extend

__all__ = ["TestInstant", "TestClass", "TestStatic", "TestProperty",
           "TestInvalid", "TestDotPath", "TestImport"]


def _add(x, y, z=3):
    return x + y + z


def _two(x, y):
    return f"{x}:{y}"


class T:
    def __init__(self, y):
        self._y = y

    @property
    def y(self):
        return self._y

    add_method = extend(_add, 'y', z=4)
    add_property = extend(_add, 1, 2, z=3, _method_type='property')
    add_static = extend(_add, 1, 2, z=3, _method_type='static')
    add_class = extend(_add, 1, 2, z=3, _method_type='class')


class TestInstant:
    """实例方法测试。"""

    def test_fixed_attr(self):
        t = T(10)
        assert t.add_method(3) == 17  # _add(10, 3, z=4)

    def test_fixed_value(self):
        class C:
            m = extend(_add, 5, z=10)
        c = C()
        assert c.m(1) == 16  # _add(5, 1, z=10)

    def test_fixed_kwarg_attr(self):
        class C:
            def __init__(self, v):
                self.v = v
            m = extend(_add, 1, 2, z='v')
        c = C(100)
        assert c.m() == 103

    def test_attr_not_found(self):
        class C:
            m = extend(_two, 'nonexistent_attr')
        c = C()
        # 'nonexistent_attr' 不是属性名，按字面值传入
        assert c.m("b") == "nonexistent_attr:b"


class TestClass:
    """类方法测试。"""

    def test_basic(self):
        assert T.add_class() == 6  # _add(1, 2, z=3)


class TestStatic:
    """静态方法测试。"""

    def test_basic(self):
        assert T.add_static() == 6  # _add(1, 2, z=3)


class TestProperty:
    """属性测试。"""

    def test_basic(self):
        t = T(10)
        assert t.add_property == 6  # _add(1, 2, z=3)

    def test_class_access(self):
        # 通过类访问时返回 property 对象
        p = T.add_property
        assert isinstance(p, property)


class TestInvalid:
    """非法参数测试。"""

    def test_bad_method_type(self):
        with pytest.raises(ValueError):
            extend(_add, 1, _method_type='invalid')


class TestDotPath:
    """点路径测试。"""

    def test_dot_path(self):
        class Inner:
            v = 10

        class Outer:
            inner = Inner()
            m = extend(_add, 'inner.v', 1, z=3)

        o = Outer()
        assert o.m() == 14  # _add(10, 1, z=3)

    def test_dot_path_not_found(self):
        class Outer:
            m = extend(_two, 'a.b.c')
        o = Outer()
        assert o.m("b") == "a.b.c:b"


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.oop.method_extend import __all__
        assert "extend" in __all__
