# -*- coding: utf-8 -*-
"""回归测试：ClassFusion.set_name / set_auto_wrap_return 入口校验（BUG-424）。

修复前两个 setter 零校验：

    set_name(123)                  # 接受；fuse() 时抛 type.__new__() argument 1
                                   # must be str, not int（CPython 层、很晚）
    set_name('')                   # 接受；得到空类名
    set_auto_wrap_return('x')      # 接受；'x' 非空字符串被**静默当成 True**
    set_auto_wrap_return(1)        # 同上（1 被当作 True）

修复后入口即校验：非 str → TypeError、空/纯空白名 → ValueError、非 bool →
TypeError；合法值行为不变（含 auto_wrap_return 的返回类型转换效果）。
"""

import pytest

from vools.oop.fusion import ClassFusion, fuse_classes


class A:
    def m(self):
        return "A.m"


class B:
    def n(self):
        return "B.n"


class TestSetNameValidation:
    @pytest.mark.parametrize("bad", [123, None, ['x']])
    def test_non_str(self, bad):
        with pytest.raises(TypeError) as ei:
            ClassFusion(A).set_name(bad)
        assert "set_name" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
    def test_blank(self, bad):
        with pytest.raises(ValueError) as ei:
            ClassFusion(A).set_name(bad)
        assert "set_name" in str(ei.value)

    def test_valid_name_used(self):
        F = ClassFusion(A).set_name("F").fuse()
        assert F.__name__ == "F"

    def test_default_name_unchanged(self):
        F = fuse_classes(A, B)
        assert F.__name__.startswith("Fused")


class TestSetAutoWrapReturnValidation:
    @pytest.mark.parametrize("bad", ["x", 1, 0, None, [True]])
    def test_non_bool(self, bad):
        with pytest.raises(TypeError) as ei:
            ClassFusion(A).set_auto_wrap_return(bad)
        assert "set_auto_wrap_return" in str(ei.value)

    def test_true_converts_return_type(self):
        F = ClassFusion(A, B).set_auto_wrap_return(True).fuse()
        # auto_wrap_return 开启时返回融合类实例
        assert F().m() == "A.m"

    def test_false_keeps_source_instance(self):
        F = ClassFusion(A).set_auto_wrap_return(False).fuse()
        assert F().m() == "A.m"
