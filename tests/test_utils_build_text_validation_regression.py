# -*- coding: utf-8 -*-
"""回归测试：build_text 的 dct/lst/max_iter_num 参数校验（BUG-356）。

修复前：

    build_text("x={a}", dct=123)          # 静默忽略 dct → 返回 "x={a}"（以为已替换）
    build_text("x", lst=123)              # 晚期由 transferCols 抛 TypeError（错误指不到参数）
    build_text("x", lst="ab")             # 字符串被逐字符当成列表元素
    build_text("x", dct={"a": 1}, max_iter_num="x")
        # TypeError: '>' not supported between instances of 'str' and 'int'
    build_text("x", dct={"a": 1}, max_iter_num=-1)
        # 静默当成"不迭代"，占位符原样返回

修复：dct 需映射（或 None）、lst 需可迭代（非字符串）或 None、max_iter_num 需非负整数
（0 保留"不迭代"语义）。
"""

import pytest

from vools.utils.tools import build_text


class TestDctValidation:
    @pytest.mark.parametrize("bad", [123, [1], "ab"])
    def test_non_mapping(self, bad):
        with pytest.raises(TypeError) as ei:
            build_text("x={a}", dct=bad)
        assert "dct" in str(ei.value)


class TestLstValidation:
    @pytest.mark.parametrize("bad", [123, "ab", b"ab"])
    def test_non_iterable_or_string(self, bad):
        with pytest.raises(TypeError) as ei:
            build_text("x={item}", lst=bad)
        assert "lst" in str(ei.value)


class TestMaxIterNumValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            build_text("x={a}", dct={"a": 1}, max_iter_num=bad)
        assert "max_iter_num" in str(ei.value)

    def test_negative(self):
        with pytest.raises(ValueError):
            build_text("x={a}", dct={"a": 1}, max_iter_num=-1)


class TestBehaviourUnchanged:
    def test_dict_substitution(self):
        assert build_text("x={a}", dct={"a": 1}) == "x=1"

    def test_nested_placeholder_loop(self):
        assert build_text("{a}", dct={"a": "{b}", "b": "ok"}) == "ok"

    def test_list_expansion(self):
        assert build_text("x={item}", lst=[1, 2]) == "x=1\n ,x=2"

    def test_custom_check_key(self):
        assert build_text("v={v}", dct={"v": 9}, check_key="v") == "v=9"

    def test_custom_sep(self):
        assert build_text("{item}", lst=["a", "b"], sep="|") == "a|b"

    def test_zero_iterations_keeps_template(self):
        assert build_text("x={a}", dct={"a": 1}, max_iter_num=0) == "x={a}"

    def test_empty_template(self):
        assert build_text() == ""

    def test_plain_text(self):
        assert build_text("hello") == "hello"

    def test_none_inputs(self):
        assert build_text("x", dct=None, lst=None) == "x"
