# -*- coding: utf-8 -*-
"""回归测试：VList 上多个方法缺"回调/表达式"准入校验（BUG-508）。

``map``/``filter`` 走 ``_run``，在 BUG-444 已加入清晰校验：
    VList([1,2,3]).map(123) -> TypeError: VList.map() 的 func 需要可调用对象或表达式字符串...

但下列方法直接 ``func(item)``，传非可调用非字符串会抛裸
``TypeError: 'int' object is not callable`` —— 看不出是哪个参数：

    flat_map / flatmap / group_by / count_by / sort_by

修复：统一走 ``VList._check_func``（可调用 或 表达式字符串；sort_by 允许 None）。
"""

import pytest

from vools.data.vlist import VList


@pytest.fixture()
def vlist():
    return VList([1, 2, 3, 4])


class TestValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, None, [1]])
    def test_flat_map(self, vlist, bad):
        with pytest.raises(TypeError) as ei:
            vlist.flat_map(bad)
        assert "flat_map" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None])
    def test_flatmap_alias(self, vlist, bad):
        with pytest.raises(TypeError) as ei:
            vlist.flatmap(bad)
        assert "flatmap" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, 1.5, None])
    def test_group_by(self, vlist, bad):
        with pytest.raises(TypeError) as ei:
            vlist.group_by(bad)
        assert "key_func" in str(ei.value)
        assert "group_by" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None])
    def test_count_by(self, vlist, bad):
        with pytest.raises(TypeError) as ei:
            vlist.count_by(bad)
        assert "key_func" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, 1.5])
    def test_sort_by(self, vlist, bad):
        with pytest.raises(TypeError) as ei:
            vlist.sort_by(bad)
        assert "key_func" in str(ei.value)

    def test_map_message_still_precise(self, vlist):
        with pytest.raises(TypeError) as ei:
            vlist.map(123)
        assert "VList.map()" in str(ei.value)


class TestValidCallablesUnchanged:
    def test_flat_map(self, vlist):
        assert list(vlist.flat_map(lambda x: [x, x])) == [1, 1, 2, 2, 3, 3, 4, 4]

    def test_flat_map_expression_string(self, vlist):
        assert list(vlist.flat_map("x")) == [1, 2, 3, 4]

    def test_group_by(self, vlist):
        assert {k: list(g) for k, g in vlist.group_by(lambda x: x % 2).items()} == {
            1: [1, 3], 0: [2, 4]}

    def test_group_by_expression_string(self, vlist):
        assert {k: list(g) for k, g in vlist.group_by("x % 2").items()} == {
            1: [1, 3], 0: [2, 4]}

    def test_count_by(self, vlist):
        assert vlist.count_by(lambda x: x % 2) == {1: 2, 0: 2}

    def test_sort_by_none_allowed(self, vlist):
        assert list(vlist.sort_by()) == [1, 2, 3, 4]

    def test_sort_by_callable(self, vlist):
        assert list(vlist.sort_by(lambda x: -x)) == [4, 3, 2, 1]

    def test_sort_by_expression_string(self, vlist):
        assert list(vlist.sort_by("-x")) == [4, 3, 2, 1]


class TestVListCopyStillIndependent:
    """BUG-505 的修复不许回退。"""

    def test_copy_then_add(self):
        v = VList([1, 2, 3])
        c = v.copy()
        c.add(4)
        assert list(v) == [1, 2, 3]
        assert list(c) == [1, 2, 3, 4]
