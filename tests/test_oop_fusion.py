# -*- coding: utf-8 -*-
"""测试 vools.oop.fusion — 类融合器。"""

import pytest
from vools.oop.fusion import fuse_classes, ClassFusion, _IMMUTABLE_TYPES

__all__ = ["TestFuseClasses", "TestOverrides", "TestWrappers",
           "TestAutoWrap", "TestSingleClass", "TestClassFusion",
           "TestPickle", "TestDo", "TestCall", "TestImmutable",
           "TestErrors", "TestImport"]


class BaseA:
    def greet(self):
        return "A"

    def __repr__(self):
        return "A"


class BaseB:
    def greet(self):
        return "B"

    def bye(self):
        return "bye"

    def value(self):
        return 42


class BaseC:
    def greet(self):
        return "C"

    def __init__(self, x=0):
        self.x = x


class TestFuseClasses:
    """fuse_classes 测试。"""

    def test_basic(self):
        F = fuse_classes(BaseA, BaseB)
        obj = F()
        assert isinstance(obj, F)
        # greet 继承顺序：第一个类优先（因为 __init__ 遍历第一个找到的 __repr__）
        assert "A" in repr(obj) or "Fused" in repr(obj)

    def test_name(self):
        F = fuse_classes(BaseA, BaseB, name="MyFused")
        assert F.__name__ == "MyFused"

    def test_default_name(self):
        F = fuse_classes(BaseA, BaseB)
        assert "Fused" in F.__name__

    def test_method_copied(self):
        F = fuse_classes(BaseA, BaseB)
        obj = F()
        assert obj.bye() == "bye"

    def test_value(self):
        F = fuse_classes(BaseA, BaseB)
        obj = F()
        assert obj.value() == 42

    def test_multi_class(self):
        F = fuse_classes(BaseA, BaseB, BaseC)
        obj = F()
        assert obj.value() == 42

    def test_single_class(self):
        F = fuse_classes(BaseA)
        obj = F()
        assert obj.greet() == "A"


class TestOverrides:
    """method_overrides 测试。"""

    def test_override(self):
        def my_greet(self):
            return "X"

        F = fuse_classes(BaseA, BaseB, method_overrides={"greet": my_greet})
        obj = F()
        assert obj.greet() == "X"

    def test_override_add_new(self):
        def new_method(self):
            return "new"

        F = fuse_classes(BaseA, method_overrides={"added": new_method})
        obj = F()
        assert obj.added() == "new"

    def test_override_not_callable(self):
        with pytest.raises(TypeError):
            fuse_classes(BaseA, method_overrides={"greet": 123})


class TestWrappers:
    """method_wrappers 测试。"""

    def test_replace(self):
        F = fuse_classes(BaseB, method_wrappers={
            "value": {"replace": lambda self: 99}
        })
        obj = F()
        assert obj.value() == 99

    def test_before(self):
        calls = []

        def before(self, *a, **kw):
            calls.append("before")

        F = fuse_classes(BaseB, method_wrappers={"value": {"before": before}})
        obj = F()
        assert obj.value() == 42
        assert calls == ["before"]

    def test_after(self):
        def after(self, result):
            return result * 2

        F = fuse_classes(BaseB, method_wrappers={"value": {"after": after}})
        obj = F()
        assert obj.value() == 84

    def test_missing_method(self):
        with pytest.raises(AttributeError):
            fuse_classes(BaseB, method_wrappers={"nope": {"before": lambda self: None}})


class TestAutoWrap:
    """auto_wrap_return 测试。"""

    def test_wrap(self):
        class W:
            def make(self):
                return W()

        F = fuse_classes(W, BaseB, auto_wrap_return=True)
        obj = F()
        r = obj.make()
        assert isinstance(r, F)


class TestSingleClass:
    """单类融合测试。"""

    def test_passthrough(self):
        F = fuse_classes(BaseA)
        obj = F()
        assert isinstance(obj, F)


class TestClassFusion:
    """ClassFusion 测试。"""

    def test_basic(self):
        cf = ClassFusion(BaseA, BaseB)
        F = cf.fuse()
        obj = F()
        assert obj.bye() == "bye"

    def test_add_class(self):
        cf = ClassFusion(BaseA)
        cf.add_class(BaseB)
        F = cf.fuse()
        obj = F()
        assert obj.value() == 42

    def test_set_name(self):
        cf = ClassFusion(BaseA).set_name("Custom")
        F = cf.fuse()
        assert F.__name__ == "Custom"

    def test_auto_wrap_return(self):
        class W:
            def make(self):
                return W()
        cf = ClassFusion(W, BaseB).set_auto_wrap_return(True)
        F = cf.fuse()
        obj = F()
        assert isinstance(obj.make(), F)

    def test_override_method(self):
        cf = ClassFusion(BaseB).override_method("value", lambda self: 7)
        F = cf.fuse()
        obj = F()
        assert obj.value() == 7

    def test_wrap_method(self):
        cf = ClassFusion(BaseB).wrap_method("value", after=lambda self, r: r + 1)
        F = cf.fuse()
        obj = F()
        assert obj.value() == 43

    def test_cached_fused_class(self):
        cf = ClassFusion(BaseA)
        F1 = cf.fuse()
        F2 = cf.fuse()
        assert F1 is F2


class TestPickle:
    """__getstate__ / __setstate__ 测试。"""

    def test_getstate(self):
        cf = ClassFusion(BaseA, BaseB)
        st = cf.__getstate__()
        assert BaseA in st["_classes"]
        assert BaseB in st["_classes"]

    def test_setstate(self):
        cf = ClassFusion(BaseA)
        cf.__setstate__({"_classes": [BaseB], "_method_overrides": {}, "_method_wrappers": {}})
        assert cf._classes == [BaseB]
        assert cf._fused_class is None


class TestDo:
    """do 方法测试。"""

    def test_default(self):
        cf = ClassFusion(BaseA)
        r = cf.do(lambda x: x)
        assert r is cf

    def test_pre(self):
        cf = ClassFusion(BaseA)
        r = cf.do(lambda x: x, pre_f=lambda x: "pre")
        assert r is cf

    def test_sub(self):
        cf = ClassFusion(BaseA)
        called = []
        r = cf.do(lambda x: x, sub_f=lambda x: called.append(x))
        assert r is cf
        assert called == [cf]


class TestCall:
    """__call__ 测试。"""

    def test_call(self):
        cf = ClassFusion(BaseC)
        obj = cf(x=5)
        assert obj.x == 5


class TestImmutable:
    """不可变类型融合测试。"""

    def test_has_immutable_types(self):
        assert str in _IMMUTABLE_TYPES
        assert int in _IMMUTABLE_TYPES
        assert tuple in _IMMUTABLE_TYPES

    def test_fuse_str_single(self):
        # 单类且无定制时直接返回原类（走 _apply_rself 分支）
        F = fuse_classes(str)
        assert F is str


class TestErrors:
    """错误处理测试。"""

    def test_no_classes(self):
        with pytest.raises(ValueError):
            fuse_classes()


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.oop.fusion import __all__
        assert "fuse_classes" in __all__
        assert "ClassFusion" in __all__
