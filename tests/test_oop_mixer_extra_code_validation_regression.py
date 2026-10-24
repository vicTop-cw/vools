# -*- coding: utf-8 -*-
"""回归测试：Mixer.add_extra_code 入口校验（BUG-427）。

修复前：

    add_extra_code(123, func_shell=...)
        # AttributeError: 'int' object has no attribute 'startswith'（天书）
    add_extra_code('__init__', func_shell=...)
        # 静默接受（早检写的是三个下划线 "___"，dunder 名漏检），注入永不生效
    add_extra_code('  ', func_shell=...)
        # 静默接受
    add_extra_code('m', code_first=123)
        # 静默接受，调用时才抛 AttributeError
    add_extra_code('attr', result_shell=...)   # 组件已有同名属性
        # 静默失效（返回原值），文档明确"不能是属性名"

修复后入口即抛带上下文的 TypeError/ValueError；组件方法名仍可正常注入。
"""

import pytest

from vools.oop.mixer import Mixer


class A:
    def m(self):
        return "A.m"

    attr = 5

    @property
    def prop(self):
        return 7


class TestFuncNameValidation:
    @pytest.mark.parametrize("bad", [123, None, ["m"], 3.5])
    def test_non_str(self, bad):
        with pytest.raises(TypeError) as ei:
            Mixer(A()).add_extra_code(bad, func_shell=lambda f: f)
        assert "add_extra_code" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank(self, bad):
        with pytest.raises(ValueError) as ei:
            Mixer(A()).add_extra_code(bad, func_shell=lambda f: f)
        assert "func_name" in str(ei.value)

    @pytest.mark.parametrize("bad", ["__init__", "__repr__", "__getattr__"])
    def test_dunder_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            Mixer(A()).add_extra_code(bad, func_shell=lambda f: f)
        assert "魔法" in str(ei.value)


class TestCodeValidation:
    @pytest.mark.parametrize("kw", ["code_first", "code_last"])
    def test_non_str_code(self, kw):
        with pytest.raises(TypeError) as ei:
            Mixer(A()).add_extra_code("m", **{kw: 123})
        assert kw in str(ei.value)

    def test_all_none_still_value_error(self):
        with pytest.raises(ValueError):
            Mixer(A()).add_extra_code("m")


class TestAttributeNameCollision:
    def test_component_attribute_rejected(self):
        with pytest.raises(ValueError) as ei:
            Mixer(A()).add_extra_code("attr", result_shell=lambda r: r + 1)
        assert "attr" in str(ei.value)

    def test_property_rejected(self):
        with pytest.raises(ValueError):
            Mixer(A()).add_extra_code("prop", result_shell=lambda r: r + 1)


class TestValidInjectionUnchanged:
    def test_result_shell(self):
        m = Mixer(A())
        m.add_extra_code("m", result_shell=lambda r: r + "!")
        assert m.m() == "A.m!"

    def test_code_first_last(self):
        m = Mixer(A())
        m.add_extra_code("m", code_first="pass", code_last="pass")
        assert m.m() == "A.m"

    def test_normal_proxying_unaffected(self):
        assert Mixer(A()).attr == 5
        assert Mixer(A()).prop == 7
        assert Mixer(A()).m() == "A.m"
