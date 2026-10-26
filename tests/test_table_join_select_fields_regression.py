# -*- coding: utf-8 -*-
"""回归测试：Table.join 的 select_fields 零校验（BUG-503）。

修复前：

    a.join(b, select_fields=['t1.zzz'], on_str='name')
    # → 列 ['t1_zzz', 't2_city']，t1_zzz 全是 None —— **幽灵列**，无任何报错

    a.join(b, select_fields=['name', 'city'], on_str='name')
    # → 无前缀项被静默忽略、回退成全列，调用方以为做了字段裁剪

    a.join(b, select_fields=123, on_str='name')
    # → 裸 TypeError: 'int' object is not iterable

修复后：select_fields 必须是 list/tuple；每项须带 t1./self./t2./other. 前缀且列必须存在
（错误信息列出可用列）。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def tables():
    a = Table([["Alice", 30], ["Bob", 25]], columns=["name", "age"])
    b = Table([["Alice", "NYC"], ["Bob", "LA"]], columns=["name", "city"])
    return a, b


class TestSelectFieldsValidation:
    @pytest.mark.parametrize("bad", ["t1.name", 123, b"t1.name"])
    def test_wrong_container_type(self, tables, bad):
        a, b = tables
        with pytest.raises(TypeError) as ei:
            a.join(b, select_fields=bad, on_str="name")
        assert "select_fields" in str(ei.value)

    @pytest.mark.parametrize("bad_field", ["t1.zzz", "t2.zzz"])
    def test_unknown_column_no_ghost_column(self, tables, bad_field):
        a, b = tables
        with pytest.raises(KeyError) as ei:
            a.join(b, select_fields=[bad_field], on_str="name")
        assert "select_fields" in str(ei.value)
        assert "可用列" in str(ei.value)

    @pytest.mark.parametrize("bad_field", ["name", "city", "zzz", ""])
    def test_missing_prefix_rejected(self, tables, bad_field):
        a, b = tables
        with pytest.raises(ValueError) as ei:
            a.join(b, select_fields=[bad_field], on_str="name")
        assert "前缀" in str(ei.value) or "形式" in str(ei.value)

    def test_unknown_prefix(self, tables):
        a, b = tables
        with pytest.raises(ValueError) as ei:
            a.join(b, select_fields=["x.name"], on_str="name")
        assert "前缀" in str(ei.value)

    def test_empty_column_after_prefix(self, tables):
        a, b = tables
        with pytest.raises(KeyError):
            a.join(b, select_fields=["t1."], on_str="name")


class TestSelectFieldsBehaviour:
    def test_t1_t2_prefixes(self, tables):
        a, b = tables
        r = a.join(b, select_fields=["t1.name", "t2.city"], on_str="name")
        assert r.columns() == ["t1_name", "t2_city"]
        assert r._data == [["Alice", "NYC"], ["Bob", "LA"]]

    def test_self_other_prefixes(self, tables):
        a, b = tables
        r = a.join(b, select_fields=["self.age", "other.city"], on_str="name")
        assert r.columns() == ["t1_age", "t2_city"]
        assert r._data == [[30, "NYC"], [25, "LA"]]

    def test_none_keeps_all_columns(self, tables):
        a, b = tables
        r = a.join(b, on_str="name")
        assert r.columns() == ["t1_name", "t1_age", "t2_city"]


class TestJoinOtherBehaviourUnchanged:
    def test_inner_join(self, tables):
        a, b = tables
        assert a.join(b, on_str="name")._data == [
            ["Alice", 30, "NYC"], ["Bob", 25, "LA"]]

    def test_left_join(self, tables):
        a, b = tables
        assert a.join(b, on_str="name", join_type="left")._data == [
            ["Alice", 30, "Alice", "NYC"], ["Bob", 25, "Bob", "LA"]]

    def test_bad_join_type(self, tables):
        a, b = tables
        with pytest.raises(ValueError):
            a.join(b, on_str="name", join_type="bogus")

    def test_unknown_join_key(self, tables):
        a, b = tables
        with pytest.raises(KeyError):
            a.join(b, on_str="nope")

    def test_non_table_other(self, tables):
        a, _ = tables
        with pytest.raises(TypeError):
            a.join(None, on_str="name")
