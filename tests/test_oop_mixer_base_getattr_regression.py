# -*- coding: utf-8 -*-
"""回归测试：Mixer_ 补上缺失的属性代理（BUG-420）。

``Mixer_`` 的文档承诺「基础混合器类，支持将多个对象的属性和方法合并，支持
按优先级访问」，但类里**没有 ``__getattr__``**（``Mixer`` 子类才有自己的实现），
因此直接用 ``Mixer_`` 时核心功能完全失效：

    m = Mixer_(A(), B())
    m.foo()   # AttributeError: 'Mixer_' object has no attribute 'foo'

修复：``Mixer_`` 实现按 ``_priority_map`` 优先级（值小者优先，即先加入者优先）
逐组件查找属性，全部未命中时抛带上下文的 ``AttributeError``；``Mixer`` 自带的
装饰器增强实现不受影响。
"""

import pytest

from vools.oop.mixer import Mixer, Mixer_


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


class TestMixerBaseProxy:
    def test_method_from_first_component(self):
        assert Mixer_(A(), B()).foo() == "A.foo"

    def test_method_from_later_component(self):
        assert Mixer_(A(), B()).bar() == "B.bar"

    def test_priority_follows_add_order(self):
        assert Mixer_(B(), A()).foo() == "B.foo"
        assert Mixer_(B(), A()).x == 2

    def test_class_attribute(self):
        assert Mixer_(A(), B()).x == 1

    def test_missing_attribute_message(self):
        with pytest.raises(AttributeError) as ei:
            Mixer_(A(), B()).nope
        assert "nope" in str(ei.value)

    def test_empty_mixer_raises(self):
        with pytest.raises(AttributeError) as ei:
            Mixer_().anything
        assert "anything" in str(ei.value)

    def test_internal_attributes_still_work(self):
        m = Mixer_(A(), B())
        assert len(m._objs) == 2
        assert m._priority_map != {}

    def test_priority_update_changes_resolution(self):
        a, b = A(), B()
        m = Mixer_(a, b)
        assert m.foo() == "A.foo"
        m.update_priority(a, 100)
        assert m.foo() == "B.foo"


class TestMixerSubclassUnaffected:
    def test_mixer_decorator_path_still_works(self):
        m = Mixer(A(), B())
        assert m.foo() == "A.foo"
        assert m.x == 1
        assert m.bar() == "B.bar"

    def test_mixer_missing_attribute_message(self):
        with pytest.raises(AttributeError) as ei:
            Mixer(A(), B()).nope
        assert "nope" in str(ei.value)
