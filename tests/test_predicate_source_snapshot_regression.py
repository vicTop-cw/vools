# -*- coding: utf-8 -*-
"""回归测试：谓词工厂对一次性源定格 + issubclass_ 类元组契约（BUG-216/217）。

- BUG-216：`is_in`/`is_not_in` 原闭包持有一次性迭代器，谓词每次查询推进
  迭代器，耗尽后静默错答（`is_not_in` 恒 True=语义反转）。修复为构造时
  `list(iterable)` 物化快照。
- BUG-217：`issubclass_` docstring 承诺「类或类元组」，原实现元组被
  isclass 短路恒静默 False。修复为元组分支：每元素都是 cls 子类才 True。
"""

import pytest

from vools.curried.predicate import is_in, is_not_in, issubclass_


class TestInPredicateReusable:
    """BUG-216：谓词可多次查询，一次性源不产生错答。"""

    def test_generator_source_multiple_queries(self):
        pred = is_in(x for x in [1, 2, 3])
        assert pred(2) is True
        assert pred(1) is True    # 原实现：扫描越过后静默 False
        assert pred(3) is True
        assert pred(5) is False

    def test_not_in_generator_no_inversion(self):
        not_pred = is_not_in(x for x in [1, 2, 3])
        assert not_pred(5) is True
        assert not_pred(1) is False  # 原实现：耗尽后恒 True（反转）

    def test_reentrant_sources_unchanged(self):
        assert is_in([1, 2, 3])(2) is True
        assert is_in([1, 2, 3])(9) is False
        assert is_in({"a": 1})("a") is True       # dict 查键语义保持
        assert is_in("hello")("e") is True
        assert is_not_in((1, 2))(3) is True

    def test_unhashable_elements(self):
        pred = is_in([[1], [2]])
        assert pred([2]) is True
        assert pred([3]) is False

    def test_map_source(self):
        pred = is_in(map(str, [1, 2, 3]))
        assert pred("1") is True and pred("3") is True and pred("9") is False


class TestIssubclassTuple:
    """BUG-217：类元组契约兑现。"""

    def test_all_subclasses_true(self):
        assert issubclass_((int, str))(object) is True
        assert issubclass_((int, float))(object) is True

    def test_any_not_subclass_false(self):
        assert issubclass_((int, str))(int) is False   # str 不是 int 子类

    def test_single_class_unchanged(self):
        assert issubclass_(int)(object) is True
        assert issubclass_(object)(int) is False

    def test_non_class_still_false(self):
        assert issubclass_(5)(object) is False        # 原"非类静默 False"保留

    def test_empty_tuple_vacuous(self):
        assert issubclass_(())(object) is True        # all([]) 真空真

    def test_tuple_with_non_class_false(self):
        assert issubclass_((int, 5))(object) is False