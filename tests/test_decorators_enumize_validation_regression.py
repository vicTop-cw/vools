# -*- coding: utf-8 -*-
"""回归测试：enumize 枚举值零校验（BUG-525）。

修复前：

    @enumize(1, 2)        # 装饰期抛裸 AttributeError: 'int' object has no attribute 'upper'
    enumerate = enumize() # 空调用 → 装饰器什么都不做（静默 no-op），_values=()
    @enumize("a", "a")    # 重复值静默覆盖 → A=1（而不是报错）
    @enumize("a-b")       # setattr(cls, "A-B", 0) 成功但点号取不到 → 属性不可达

修复后：至少一个值；每个值必须是非空字符串；大写后必须是合法标识符；不允许重复。
合法用法（red/green/blue、user_name 等）行为不变。
"""

import importlib

import pytest

sc = importlib.import_module("vools.decorators.shotcut")


class TestEnumizeValidation:
    def test_empty_values(self):
        with pytest.raises(ValueError) as ei:
            sc.enumize()
        assert "至少一个" in str(ei.value)

    @pytest.mark.parametrize("bad", [1, None, 1.5, ["a"]])
    def test_non_str_value(self, bad):
        with pytest.raises(TypeError) as ei:
            sc.enumize(bad)
        assert "枚举值" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_value(self, bad):
        with pytest.raises(TypeError):
            sc.enumize(bad)

    def test_duplicate_value(self):
        with pytest.raises(ValueError) as ei:
            sc.enumize("a", "a")
        assert "重复" in str(ei.value)

    def test_duplicate_after_upper(self):
        with pytest.raises(ValueError):
            sc.enumize("a", "A")

    @pytest.mark.parametrize("bad", ["a-b", "a b", "1a", "a.b"])
    def test_invalid_identifier(self, bad):
        with pytest.raises(ValueError) as ei:
            sc.enumize(bad)
        assert "标识符" in str(ei.value)


class TestEnumizeBehaviourUnchanged:
    def test_basic_values(self):
        @sc.enumize("red", "green", "blue")
        class C:
            pass

        assert C.RED == 0
        assert C.GREEN == 1
        assert C.BLUE == 2
        assert C._values == ("red", "green", "blue")

    def test_underscore_value(self):
        @sc.enumize("user_name")
        class D:
            pass

        assert D.USER_NAME == 0

    def test_single_value(self):
        @sc.enumize("only")
        class E:
            pass

        assert E.ONLY == 0
        assert E._values == ("only",)

    def test_returns_same_class(self):
        class F:
            pass

        assert sc.enumize("x")(F) is F
