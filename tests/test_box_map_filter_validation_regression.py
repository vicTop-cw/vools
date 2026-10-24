# -*- coding: utf-8 -*-
"""回归测试：Box.map/filter 的 func 校验与报错信息（BUG-437）+ Maybe 契约。

修复前：

    Box([1, 2]).filter("x")     # TypeError: 'str' object is not callable
                                  # （看不出是 func 参数错误）
    Box("abc").map(len)         # TypeError: map 操作只适用于可迭代对象
                                  # （str 本就可迭代；实际是被有意排除）

修复后 func 非可调用抛带字段名的 TypeError；str/bytes 的报错说明真实限制
（排除以避免逐字符映射）并给出替代用法。正常 map/filter/reduce/run 与
Maybe（some/nothing/optional/maybe_map/get_or/unwrap）语义不变。
"""

import pytest

from vools.functional.box import Box
from vools.functional.maybe import Maybe, maybe_map, nothing, optional, some


class TestBoxMapFilterValidation:
    @pytest.mark.parametrize("bad", ["x", 123, None, object()])
    def test_map_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            Box([1, 2]).map(bad)
        assert "func" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", 123, None])
    def test_filter_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            Box([1, 2]).filter(bad)
        assert "func" in str(ei.value)

    @pytest.mark.parametrize("bad", ["abc", b"ab"])
    def test_str_bytes_rejected_with_accurate_message(self, bad):
        with pytest.raises(TypeError) as ei:
            Box(bad).map(lambda x: x)
        msg = str(ei.value)
        assert "str/bytes" in msg
        assert "逐字符" in msg

    def test_none_rejected(self):
        with pytest.raises(TypeError) as ei:
            Box(None).map(lambda x: x)
        assert "str/bytes" in str(ei.value)


class TestBoxNormalOps:
    def test_map(self):
        assert Box([1, 2, 3]).map(lambda x: x * 2) == [2, 4, 6]

    def test_filter(self):
        assert Box([1, 2, 3]).filter(lambda x: x > 1) == [2, 3]

    def test_reduce(self):
        assert Box([1, 2, 3]).reduce(lambda a, b: a + b) == 6

    def test_run(self):
        assert Box([1, 2, 3]).run(lambda x: len(x)) == 3


class TestMaybeContract:
    def test_some_map(self):
        assert some(1).map(lambda x: x * 2) == some(2)

    def test_nothing_map(self):
        assert nothing().map(lambda x: x * 2) == nothing()

    def test_optional(self):
        assert optional(None).is_none is True
        assert optional(1).is_none is False

    def test_get_or(self):
        assert some(1).get_or(0) == 1
        assert nothing().get_or(0) == 0

    def test_unwrap(self):
        assert some(1).unwrap() == 1
        with pytest.raises(ValueError):
            nothing().unwrap()

    def test_maybe_map(self):
        assert maybe_map({"a": 1}, "a") == some(1)
        assert maybe_map({}, "a") == nothing()
