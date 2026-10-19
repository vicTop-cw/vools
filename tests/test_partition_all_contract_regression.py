# -*- coding: utf-8 -*-
"""回归测试：partition_all 末组补齐到 n（BUG-213）。

原 `_partition_all` 与 `_partition` 逐字相同——`partition_all` 的 docstring
承诺「所有组都有相同大小」（toolz 惯例末组补 None），实际末组畸形不满，
与 partition 零差异、正文契约与 Example 自相矛盾。

修复：`_partition_all` 末组以 None 补齐到 n；`partition` 语义保持不变。
"""

from vools.curried.collection import partition, partition_all


class TestPartitionAllSameSize:
    """partition_all 组组等长（BUG-213 核心契约）。"""

    def test_remainder_padded(self):
        assert partition_all(3, range(10)) == [
            [0, 1, 2], [3, 4, 5], [6, 7, 8], [9, None, None]]

    def test_remainder_padded_2(self):
        assert partition_all(2, ['a', 'b', 'c']) == [['a', 'b'], ['c', None]]

    def test_even_not_padded(self):
        assert partition_all(3, range(9)) == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]

    def test_all_groups_size_n(self):
        n = 4
        for batch in partition_all(n, range(17)):
            assert len(batch) == n

    def test_empty(self):
        assert partition_all(3, []) == []

    def test_single_short(self):
        assert partition_all(3, [7]) == [[7, None, None]]


class TestPartitionUnchanged:
    """partition 保持"末组可不满足"的原语义（防修复串扰）。"""

    def test_remainder_not_padded(self):
        assert partition(3, range(10)) == [
            [0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

    def test_odd_short_group(self):
        assert partition(2, ['a', 'b', 'c']) == [['a', 'b'], ['c']]

    def test_empty(self):
        assert partition(3, []) == []


class TestSemanticsNowDiffer:
    """两函数不再是零差异别名（BUG-213 的 API 面症状）。"""

    def test_not_identical_output(self):
        assert partition_all(3, range(10)) != partition(3, range(10))