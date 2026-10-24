# -*- coding: utf-8 -*-
"""回归测试：fuse_classes 应同时复制类属性（BUG-421）。

``fuse_classes`` 原先只调用 :func:`_copy_methods_from_parents`，**类属性**
（``x = 1``）在融合后静默消失：

    class A:
        def m(self): ...
        x = 1
    class B:
        y = 2

    F = fuse_classes(A, B)
    F.x   # 修复前 AttributeError（没有任何提示）

修复：新增 :func:`_copy_class_attributes_from_parents`，在**方法复制之后**
复制父类直接定义的非 dunder 类属性（同名跳过 → 方法优先；多个类同名属性
先出现者优先）。
"""

import pytest

from vools.oop.fusion import fuse_classes, ClassFusion


class A:
    def m(self):
        return "A.m"

    x = 1
    CONST = "A.const"


class B:
    def m(self):
        return "B.m"

    def p(self):
        return "B.p"

    y = 2
    x = 99


class C:
    z = 3


class WithAttr:
    value = 1


class WithMethod:
    def value(self):
        return "method"


class TestFuseClassesAttributes:
    def test_attributes_copied(self):
        F = fuse_classes(A, B)
        assert F.x == 1          # A 优先
        assert F.y == 2
        assert F.CONST == "A.const"

    def test_priority_follows_class_order(self):
        assert fuse_classes(B, A).x == 99

    def test_third_class_attribute(self):
        assert fuse_classes(A, B, C).z == 3

    def test_methods_still_work(self):
        F = fuse_classes(A, B)
        obj = F()
        assert obj.m() == "A.m"
        assert obj.p() == "B.p"

    def test_method_priority_over_attribute(self):
        """同名属性与方法冲突时，方法优先（属性复制在后且跳过已有名）。"""
        F = fuse_classes(WithAttr, WithMethod)
        assert F().value() == "method"

    def test_same_name_attribute_first_wins(self):
        assert fuse_classes(A, B).x == 1
        assert fuse_classes(B, A).x == 99


class TestClassFusionAttributes:
    def test_classfusion_path(self):
        F = ClassFusion().add_class(A).add_class(B).set_name("CF").fuse()
        assert F.x == 1
        assert F.y == 2
        assert F.m(F()) == "A.m"


class TestUnchangedBehaviours:
    def test_single_class_returns_class(self):
        F = fuse_classes(A)
        assert isinstance(F, type)
        assert F().m() == "A.m"
        assert F.x == 1

    def test_immutable_single_class(self):
        assert fuse_classes(int) is int
        assert fuse_classes(str) is str

    def test_method_override_still_works(self):
        F = fuse_classes(A, B, method_overrides={"m": lambda self: "overridden"})
        assert F().m() == "overridden"
