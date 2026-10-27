# -*- coding: utf-8 -*-
"""回归测试：curry 包装错误信息重复前缀 + nth 索引校验（BUG-353）。

## 1. 重复前缀

    group_by(len)(None)   # 修复前 → TypeError: Failed to curry groupby:
                          #   Failed to curry groupby: 'NoneType' object is not iterable
    capitalize(None)      # 修复前 → CurryExecutionError: Failed to curry capitalize:
                          #   Failed to curry capitalize: 'NoneType' object has no attribute ...

根因：``Curried.__call__`` 内部 ``return result()`` 会真正执行原函数；若执行时
又抛（内层已包装过的）"Failed to curry X: ..."，外层 except 再包一次 → 前缀重复。
修复后：已是包装消息则直接透传，只保留一层前缀。

## 2. nth 索引校验

    nth("x")([1, 2])   # 修复前 → Failed to curry nth: '<' not supported between
                       #   instances of 'str' and 'int'（看不出是索引参数）
   修复后 → TypeError: ... nth 的 n 必须是整数索引，收到 str: 'x'
"""

import pytest

import vools.curried as cu


class TestNoDuplicatedCurryPrefix:
    @pytest.mark.parametrize(
        "call",
        [
            lambda: cu.group_by(len)(None),
            lambda: cu.capitalize(None),
            lambda: cu.flatten(None),
        ],
    )
    def test_prefix_appears_once(self, call):
        with pytest.raises(Exception) as ei:
            call()
        msg = str(ei.value)
        assert msg.count("Failed to curry") == 1, msg


class TestNthValidation:
    @pytest.mark.parametrize("bad", ["x", None, 1.5, True])
    def test_non_int_index(self, bad):
        with pytest.raises(TypeError) as ei:
            cu.nth(bad)([1, 2])
        assert "整数索引" in str(ei.value)

    def test_error_message_mentions_nth_once(self):
        with pytest.raises(TypeError) as ei:
            cu.nth("x")([1, 2])
        assert str(ei.value).count("Failed to curry") == 1


class TestNthBehaviourUnchanged:
    def test_first(self):
        assert cu.nth(0)([9, 8]) == 9

    def test_negative(self):
        assert cu.nth(-1)([9, 8]) == 8

    def test_out_of_range_default(self):
        assert cu.nth(99, [9, 8], "-") == "-"

    def test_out_of_range_none(self):
        assert cu.nth(99)([9, 8]) is None


class TestOtherCurriedBehaviourUnchanged:
    def test_group_by(self):
        assert cu.group_by(len)(["a", "bb"]) == {1: ["a"], 2: ["bb"]}

    def test_flatten(self):
        assert cu.flatten([[1], [2, 3]]) == [1, 2, 3]

    def test_partial_application(self):
        assert cu.add(1)(2) == 3

    def test_curry_error_still_raised(self):
        with pytest.raises((TypeError, Exception)):
            cu.group_by(len)(None)
