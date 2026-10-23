# -*- coding: utf-8 -*-
"""回归测试：VList.roundrobin 实例调用不再丢失接收者（BUG-367）。

原实现是 `@staticmethod`：

    @staticmethod
    def roundrobin(*iterables): ...

于是**实例调用会把接收者整个丢掉且不报错**：

    VList([1, 2]).roundrobin([3, 4])     # -> [3, 4]   （1、2 静默消失）

修复：改为实例方法，`iterables = (self, *iterables)` —— 实例调用时接收者是
第一个可迭代对象；类调用 `VList.roundrobin(a, b)` 时第一个参数充当"接收者"，
与既有用法（tests/test_vic_inherit.py）结果一致。
"""

import pytest

from vools.data.vlist import VList


class TestInstanceCall:
    def test_includes_receiver(self):
        # 修复前：[3, 4]（接收者被丢弃）
        assert list(VList([1, 2]).roundrobin([3, 4])) == [1, 3, 2, 4]

    def test_multiple_iterables(self):
        assert list(VList([1, 2]).roundrobin([3, 4], [5])) == [1, 3, 5, 2, 4]

    def test_no_extra_iterables(self):
        assert list(VList([1, 2]).roundrobin()) == [1, 2]

    def test_empty_receiver(self):
        assert list(VList([]).roundrobin([3, 4])) == [3, 4]

    def test_uneven_lengths(self):
        assert list(VList([1, 2, 3]).roundrobin(['a'])) == [1, 'a', 2, 3]

    def test_returns_vlist(self):
        assert isinstance(VList([1]).roundrobin([2]), VList)


class TestClassCallUnchanged:
    def test_class_call(self):
        assert list(VList.roundrobin([1, 2], [3, 4])) == [1, 3, 2, 4]

    def test_legacy_string_usage(self):
        # tests/test_vic_inherit.py 中锁定的既有用法
        assert VList.roundrobin('ABC', 'D', 'EF').collect() == [
            'A', 'D', 'E', 'B', 'F', 'C']

    def test_class_call_single(self):
        assert list(VList.roundrobin([1, 2])) == [1, 2]