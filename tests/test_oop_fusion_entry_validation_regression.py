# -*- coding: utf-8 -*-
"""回归测试：ClassFusion 的 override/wrap/add_class 入口校验（BUG-423）。

修复前这些入口**零校验**，问题只在 ``fuse()`` 阶段才暴露（甚至完全不暴露）：

    override_method('m', 123)          # fuse() 时才抛 TypeError: must be callable
    wrap_method('m')                   # 静默 no-op（三个回调全 None），调用方以为包装生效
    wrap_method('m', before='x')       # fuse() 时才抛 'str' object is not callable
    wrap_method('nope', before=fn)     # fuse() 时才抛 Method 'nope' not found
    add_class(123) / ClassFusion(123)  # 非类一路走到 fuse() 报“至少需要一个类”

修复后：非法参数在**调用点**即抛带上下文的 TypeError/ValueError；``wrap_method``
至少需要一个回调；方法必须已注册（wrap 早于 add_class 时无法校验，仅校验回调）。
"""

import pytest

from vools.oop.fusion import ClassFusion, fuse_classes


class A:
    def m(self):
        return "A.m"


class B:
    def m(self):
        return "B.m"


class TestOverrideMethodValidation:
    @pytest.mark.parametrize("bad", [123, "x", None])
    def test_non_callable_impl(self, bad):
        with pytest.raises(TypeError) as ei:
            ClassFusion().add_class(A).override_method("m", bad)
        assert "m" in str(ei.value)

    def test_valid_override_still_works(self):
        F = ClassFusion(A).override_method("m", lambda self: "ov").fuse()
        assert F().m() == "ov"

    def test_override_can_add_new_method(self):
        F = ClassFusion(A).override_method("new", lambda self: "new").fuse()
        assert F().new() == "new"


class TestWrapMethodValidation:
    def test_all_none_rejected(self):
        with pytest.raises(ValueError) as ei:
            ClassFusion().add_class(A).wrap_method("m")
        assert "before" in str(ei.value)

    @pytest.mark.parametrize("kw", ["before", "after", "replace"])
    def test_non_callable_callback(self, kw):
        kwargs = {kw: "not-callable"}
        with pytest.raises(TypeError) as ei:
            ClassFusion().add_class(A).wrap_method("m", **kwargs)
        assert kw in str(ei.value)

    def test_unknown_method_rejected(self):
        with pytest.raises(ValueError) as ei:
            ClassFusion().add_class(A).wrap_method("nope", before=lambda s: None)
        msg = str(ei.value)
        assert "nope" in msg and "m" in msg   # 提示可用方法

    def test_valid_wrapper_still_works(self):
        F = ClassFusion(A).wrap_method("m", after=lambda s, r: r + "!").fuse()
        assert F().m() == "A.m!"

    def test_wrap_before_add_class_only_checks_callbacks(self):
        # 尚未 add_class 时无法校验方法是否存在，但回调仍会被校验
        cf = ClassFusion().wrap_method("m", before=lambda s: None)
        cf.add_class(A)
        assert cf.fuse()().m() == "A.m"


class TestClassValidation:
    def test_add_class_non_class(self):
        with pytest.raises(TypeError) as ei:
            ClassFusion().add_class(123)
        assert "add_class" in str(ei.value)

    def test_init_non_class(self):
        with pytest.raises(TypeError) as ei:
            ClassFusion(123)
        assert "ClassFusion" in str(ei.value)

    def test_empty_still_allowed(self):
        cf = ClassFusion()
        assert cf._classes == []
        with pytest.raises(ValueError):
            cf.fuse()          # fuse_classes 的既有契约：至少一个类


class TestFuseClassesDirectValidationUnchanged:
    def test_non_callable_override_still_type_error(self):
        with pytest.raises(TypeError):
            fuse_classes(A, method_overrides={"m": 123})

    def test_unknown_wrapper_still_attribute_error(self):
        with pytest.raises(AttributeError):
            fuse_classes(A, method_wrappers={"nope": {"before": lambda s: None}})
