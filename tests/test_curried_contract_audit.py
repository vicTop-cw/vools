# -*- coding: utf-8 -*-
"""契约测试：vools.curried（toolz 风格柯里化工具库）。

本库与 toolz **有意不同**的语义（本轮审计确认，均自洽；此文件防止将来被
"顺手改成 toolz 语义"而静默破坏调用方）：

* ``get(iterable, index, default=None)`` —— **序列下标**语义，
  不是 toolz 的 ``get(key, coll)``；因此 ``get('a', {'a': 1})`` 会响亮报错
  （CurryExecutionError），不会静默返回 None。
* ``assoc(d, **kwargs)`` —— 关键字更新，位置参数会被拒（Too many positional
  arguments），且**不改原 dict**。
* ``assoc_in(d, keys, value)`` / ``get_in(keys, d, default=None)`` —— keys 在前。
* ``cat = concat`` —— ``concat(*iterables)``，因此 ``cat([[1], [2]])`` 只做一层
  拼接返回 ``[[1], [2]]``（toolz 的 cat 会摊平）。
* ``ignore`` 来自 ``vools.decorators.control`` —— 是**装饰器工厂**，不是
  toolz 的 ``ignore = const(None)``。
"""

import pytest

import vools.curried as c


class TestDictOps:
    def test_assoc_kwargs(self):
        assert c.assoc({}, a=1) == {"a": 1}
        assert c.assoc({"a": 0}, a=1, b=2) == {"a": 1, "b": 2}

    def test_assoc_is_pure(self):
        d = {"a": 1}
        out = c.assoc(d, b=2)
        assert d == {"a": 1}
        assert out == {"a": 1, "b": 2}

    def test_assoc_positional_rejected(self):
        """toolz 的 assoc(d, key, value) 顺序在本库不适用（响亮报错）。"""
        with pytest.raises(Exception):
            c.assoc({}, "a", 1)

    def test_dissoc(self):
        assert c.dissoc({"a": 1, "b": 2}, "a") == {"b": 2}

    def test_assoc_in(self):
        assert c.assoc_in({}, ["a", "b"], 1) == {"a": {"b": 1}}

    def test_assoc_in_is_pure(self):
        d = {"a": {"b": 1}}
        out = c.assoc_in(d, ["a", "b"], 99)
        assert d == {"a": {"b": 1}}
        assert out == {"a": {"b": 99}}

    def test_get_in(self):
        assert c.get_in(["a", "b"], {"a": {"b": 5}}) == 5
        assert c.get_in(["a", "zz"], {"a": {"b": 5}}) is None
        assert c.get_in(["a", "zz"], {"a": {"b": 5}}, default=0) == 0

    def test_get_in_empty_path_returns_dict(self):
        assert c.get_in([], {"a": 1}) == {"a": 1}


class TestGetSequenceSemantics:
    def test_index(self):
        assert c.get([1, 2, 3], 1) == 2
        assert c.get("abc", 1) == "b"

    def test_default(self):
        assert c.get([1, 2, 3], 9, default="d") == "d"
        assert c.get([], 0) is None

    def test_toolz_order_is_loud(self):
        """toolz 的 get(key, coll) 顺序在本库会响亮失败（不是静默 None）。"""
        with pytest.raises(Exception):
            c.get("a", {"a": 1})


class TestSequenceOps:
    def test_first(self):
        assert c.first([1, 2]) == 1
        assert c.first([]) is None

    def test_butlast(self):
        assert list(c.butlast([1, 2, 3])) == [1, 2]

    def test_flatten_deep(self):
        assert list(c.flatten([[1, [2]], [3]])) == [1, 2, 3]

    def test_compact(self):
        assert list(c.compact([0, "", None, False, [], 1])) == [1]

    def test_concat(self):
        assert list(c.concat([1], [2, 3])) == [1, 2, 3]

    def test_cat_is_concat(self):
        assert list(c.cat([[1], [2]])) == [[1], [2]]

    def test_group_by_and_alias(self):
        assert c.group_by(len, ["a", "bb"]) == {1: ["a"], 2: ["bb"]}
        assert c.groupby(len, ["a", "bb"]) == {1: ["a"], 2: ["bb"]}

    def test_imap_ifilter(self):
        assert list(c.imap(c.inc, [1, 2])) == [2, 3]
        assert list(c.ifilter(None, [0, 1, 2])) == [1, 2]


class TestComposition:
    def test_compose_order(self):
        assert c.compose(str, c.inc)(1) == "2"

    def test_compose_left_order(self):
        assert c.compose_left(c.inc, str)(1) == "2"

    def test_identity_const_flip_apply(self):
        assert c.identity(5) == 5
        assert c.const(1)(9) == 1
        assert c.flip(c.add)(1, 2) == 3
        assert c.apply(c.add, 1, 2) == 3


class TestArithmeticCurrying:
    def test_add_both_forms(self):
        assert c.add(1, 2) == 3
        assert c.add(1)(2) == 3

    def test_inc_dec(self):
        assert c.inc(1) == 2
        assert c.dec(1) == 0

    def test_div(self):
        assert c.div(10, 2) == 5.0

    def test_div_by_zero_is_loud(self):
        with pytest.raises(Exception):
            c.div(10, 0)


class TestDecoratorHelpers:
    def test_ignore_is_decorator_factory(self):
        assert callable(c.ignore(1))

    def test_excepts_handler(self):
        assert c.excepts(ValueError, lambda e: "err")(int)("x") == "err"


class TestNestedUpdates:
    """set_in / update_in 的参数顺序是 (keys, value/fn, d)，且都是纯函数。"""

    def test_set_in(self):
        assert c.set_in(["a", "b"], 1, {"a": {}}) == {"a": {"b": 1}}
        assert c.set_in(["a", "b"], 1, {}) == {"a": {"b": 1}}

    def test_set_in_is_pure(self):
        d = {"a": {"b": 1}}
        out = c.set_in(["a", "b"], 99, d)
        assert d == {"a": {"b": 1}}
        assert out == {"a": {"b": 99}}

    def test_update_in(self):
        assert c.update_in(["a", "b"], c.inc, {"a": {"b": 1}}) == {"a": {"b": 2}}

    def test_update_in_is_pure(self):
        d = {"a": {"b": 1}}
        out = c.update_in(["a", "b"], c.inc, d)
        assert d == {"a": {"b": 1}}
        assert out == {"a": {"b": 2}}

    def test_wrong_order_is_loud(self):
        """toolz 顺序 set_in(d, keys, value) 在本库会响亮失败，不会静默错值。"""
        with pytest.raises(Exception):
            c.set_in({"a": {}}, ["a", "b"], 1)


class TestMerge:
    def test_merge(self):
        assert c.merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
        assert c.merge({"a": 1}, {"a": 2}) == {"a": 2}      # 后者覆盖
        assert c.merge() == {}

    def test_merge_with_curried(self):
        assert c.merge_with(sum)({"a": 1, "b": 2}, {"a": 10}) == {"a": 11, "b": 2}

    def test_merge_with_positional_dicts_rejected(self):
        # merge_with 是 curry(fn) -> Callable 形态
        with pytest.raises(Exception):
            c.merge_with(sum, {"a": 1})


class TestWalk:
    """walk(fn, iterable) 是"就地副作用遍历"，返回 None（文档 -> None）。"""

    def test_side_effects_applied(self):
        seen = []
        assert c.walk(seen.append, [1, 2, 3]) is None
        assert seen == [1, 2, 3]

    def test_does_not_flatten(self):
        seen = []
        c.walk(seen.append, [[1, 2], [3]])
        assert seen == [[1, 2], [3]]


class TestPartitionSemantics:
    """partition 末组不齐；partition_all 末组补 None 到 n（BUG-213 文档契约）。"""

    def test_partition_no_padding(self):
        assert c.partition(2, [1, 2, 3, 4, 5]) == [[1, 2], [3, 4], [5]]

    def test_partition_all_pads_with_none(self):
        assert c.partition_all(2, [1, 2, 3]) == [[1, 2], [3, None]]
        assert c.partition_all(2, [1, 2, 3, 4]) == [[1, 2], [3, 4]]


class TestAccessors:
    def test_nth_second_last(self):
        assert c.nth(1, [1, 2, 3]) == 2
        assert c.second([1, 2, 3]) == 2
        assert c.last([1, 2, 3]) == 3

    def test_nth_out_of_range_is_none(self):
        assert c.nth(9, [1]) is None

    def test_unique_with_key(self):
        assert list(c.unique([1, 1, 2])) == [1, 2]
        assert list(c.iunique([1, 1, 2])) == [1, 2]
        assert list(c.unique([1, 1, 2], key=lambda x: 0)) == [1]

    def test_mapcat_pluck(self):
        assert list(c.mapcat(lambda x: [x, x], [1, 2])) == [1, 1, 2, 2]
        assert list(c.pluck("a", [{"a": 1}, {"a": 2}])) == [1, 2]

    def test_pluck_missing_key_is_loud(self):
        """本库对缺失键响亮失败（toolz 会产出 None）。"""
        with pytest.raises(Exception):
            list(c.pluck("zz", [{"a": 1}]))

