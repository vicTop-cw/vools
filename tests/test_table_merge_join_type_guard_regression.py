# -*- coding: utf-8 -*-
"""回归测试：Table.merge / Table.join 的 other 类型校验（BUG-393）。

`merge(list)` / `join(dict)` 等非表入参时，原实现直接访问 `other._columns`
或 `other._name`，抛出裸 `AttributeError`：

    a.merge([[1, 2]])
    # AttributeError: 'list' object has no attribute '_columns'

错误信息看不出是「参数类型错了」，也与其它入口（类型错误一律 TypeError +
期望/实际类型）不一致。修复：入口校验 `isinstance(other, Table)`
（Qax 继承 Table，故 Qax 仍可用），否则 TypeError。

正常纵向/横向合并、与 Qax 的合并/连接行为不变。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


@pytest.fixture()
def table():
    return Table([[1, 'a'], [2, 'b']], columns=['id', 'x'], name='t1')


class TestInvalidOther:
    @pytest.mark.parametrize('bad', [
        [[1, 2]], {'a': 1}, 'abc', 42, None,
    ])
    def test_merge_rejects(self, table, bad):
        with pytest.raises(TypeError) as ei:
            table.merge(bad)
        assert 'Table' in str(ei.value)

    @pytest.mark.parametrize('bad', [
        [[1, 2]], {'a': 1}, 'abc', 42, None,
    ])
    def test_join_rejects(self, table, bad):
        with pytest.raises(TypeError) as ei:
            table.join(bad, on_str='t1.id = t2.id')
        assert 'Table' in str(ei.value)


class TestValidPathsUnchanged:
    def test_merge_vertical(self, table):
        other = Table([[3, 'c']], columns=['id', 'x'])
        assert table.merge(other)._data == [[1, 'a'], [2, 'b'], [3, 'c']]

    def test_merge_horizontal(self, table):
        other = Table([[10], [20]], columns=['score'])
        assert table.merge(other, vertical=False)._data == [
            [1, 'a', 10], [2, 'b', 20]]

    def test_merge_qax(self, table):
        q = Qax([[2, 'y']], columns=['id', 'w'])
        # 列并集 + 行追加（非按键匹配）
        assert table.merge(q)._data == [
            [1, 'a', None], [2, 'b', None], [2, None, 'y']]

    def test_join_qax(self, table):
        q = Qax([[2, 'y']], columns=['id', 'w'])
        r = table.join(q, on_str='t1.id = t2.id')
        assert r._columns == ['t1_id', 't1_x', 't2_w']
        assert r._data == [[2, 'b', 'y']]

    def test_join_auto_common_column(self, table):
        other = Table([[2, 'z']], columns=['id', 'z'])
        assert table.join(other)._columns == ['t1_id', 't1_x', 't2_z']