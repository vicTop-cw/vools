# -*- coding: utf-8 -*-
"""回归测试：@curry_class 对 __slots__ 类 + delay_curry 校验（BUG-479）。

修复前：

    @curry_class
    class S:
        __slots__ = ('v',)
        def m(self, a, b): ...

    S()   # AttributeError: 'S' object attribute 'm' is read-only
          #   —— curry_class 在 new_init 里 setattr(self, name, curried)，
          #      __slots__ 类没有实例 __dict__，装饰期静默通过、**实例化才崩**

    delay_curry(123)      # -> 静默返回 wrapper（调用期才炸）
    DelayCurried(123)     # -> AttributeError: 'int' object has no attribute '__module__'

修复后：@curry_class 在**装饰期**显式拒绝无实例 __dict__ 的类（并给出补救建议）；
delay_curry/DelayCurried 要求可调用对象。slots+__dict__ 与普通类行为不变。
"""

import pytest

import vools.decorators as d


class TestCurryClassSlotsGuard:
    def test_slots_without_dict_rejected_at_decoration(self):
        """修复前是"实例化才崩"，现在装饰期就拒绝。"""
        with pytest.raises(TypeError) as ei:
            @d.curry_class
            class S:
                __slots__ = ("v",)

                def m(self, a, b):
                    return a + b
        assert "curry_class" in str(ei.value)
        assert "__dict__" in str(ei.value) or "__slots__" in str(ei.value)

    def test_slots_with_dict_allowed(self):
        @d.curry_class
        class S:
            __slots__ = ("v", "__dict__")

            def m(self, a, b):
                return a + b

        assert S().m(1)(2) == 3

    def test_plain_class_unchanged(self):
        @d.curry_class
        class T:
            def add(self, a, b, c):
                return a + b + c

        t = T()
        assert t.add(1).add(2).add(3) == 6
        assert t.add(1, 2, 3) == 6

    def test_non_class_rejected(self):
        with pytest.raises(TypeError):
            d.curry_class(123)


class TestDelayCurryValidation:
    @pytest.mark.parametrize("bad", [123, None, "x", [1]])
    def test_delay_curry_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            d.delay_curry(bad)
        assert "func" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None, "x"])
    def test_delay_curried_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            d.DelayCurried(bad)
        assert "func" in str(ei.value)


class TestDelayCurrySemanticsUnchanged:
    def test_requires_empty_call(self):
        @d.delay_curry
        def add3(a, b, c):
            return a + b + c

        assert add3(1)(2)(3)() == 6      # 文档语义：满参后需空调用触发
        assert add3(1, 2, 3)() == 6
        assert type(add3(1)(2)).__name__ == "DelayCurried"

    def test_not_triggered_without_empty_call(self):
        @d.delay_curry
        def add3(a, b, c):
            return a + b + c

        result = add3(1)(2)(3)
        assert type(result).__name__ == "DelayCurried"
