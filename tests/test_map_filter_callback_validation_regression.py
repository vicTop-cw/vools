# -*- coding: utf-8 -*-
"""回归测试：map/filter 对非法回调静默返回空列表（BUG-444）。

修复前：``VList._run`` / ``_run_filter`` 的 ``else`` 分支直接 ``return []``：

    VList([1, 2, 3]).map(123)     # -> []   ← 静默丢数据（元素全部消失）
    VList([1, 2, 3]).filter(123)  # -> []   ← 同上

``Seq.map`` / ``Seq.filter`` 则把非法值一路带到调用点，抛
``'int' object is not callable``（看不出是哪个方法、哪个位置）。

修复后入口即抛带方法名的 TypeError；合法路径（可调用对象、表达式字符串、
``map(None)`` 打印语义）不变。
"""

import pytest

from vools.data.seq import Seq
from vools.data.vlist import VList


class TestVListMapValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, True, ["x"], object()])
    def test_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            VList([1, 2, 3]).map(bad)
        assert "VList.map" in str(ei.value)

    def test_callable_unchanged(self):
        assert list(VList([1, 2, 3]).map(lambda x: x * 2)) == [2, 4, 6]

    def test_expression_string_unchanged(self):
        assert list(VList([1, 2, 3]).map("x * 2")) == [2, 4, 6]

    def test_none_prints_and_returns_none(self, capsys):
        assert VList([1, 2, 3]).map(None) is None
        assert "1" in capsys.readouterr().out


class TestVListFilterValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, True, ["x"]])
    def test_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            VList([1, 2, 3]).filter(bad)
        assert "VList.filter" in str(ei.value)

    def test_callable_unchanged(self):
        assert list(VList([1, 2, 3]).filter(lambda x: x > 1)) == [2, 3]

    def test_expression_unchanged(self):
        assert list(VList([1, 2, 3]).filter("x > 1")) == [2, 3]
        assert list(VList([1, 2, 3]).filter("lambda x: x > 1")) == [2, 3]


class TestSeqValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, True, ["x"]])
    def test_map_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            Seq([1, 2, 3]).map(bad)
        assert "Seq.map" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, 1.5, True, ["x"]])
    def test_filter_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            Seq([1, 2, 3]).filter(bad)
        assert "Seq.filter" in str(ei.value)

    def test_valid_paths(self):
        assert list(Seq([1, 2, 3]).map(lambda x: x * 2)) == [2, 4, 6]
        assert list(Seq([1, 2, 3]).filter(lambda x: x > 1)) == [2, 3]
        assert list(Seq([1, 2, 3]).filter("x > 1")) == [2, 3]


class TestForeachInheritsGuard:
    """foreach 委托给 map/filter，因此同样受保护。"""

    def test_bad_func(self):
        with pytest.raises(TypeError):
            VList([1, 2, 3]).foreach(123)

    def test_bad_filter(self):
        with pytest.raises(TypeError):
            VList([1, 2, 3]).foreach(lambda x: x, filter_func=123)

    def test_valid(self, capsys):
        result = VList([1, 2, 3]).foreach(lambda x: x * 2, filter_func=lambda x: x > 1)
        assert list(result) == [4, 6]
