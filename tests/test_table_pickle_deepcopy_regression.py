# -*- coding: utf-8 -*-
"""回归测试：Table/Qax/Row/Column 的 pickle 与 copy.deepcopy 往返（BUG-330）。

`Table`/`Row`/`Column` 都继承 `Seq`，而 `Seq` 定义了只保存序列元素的
`__getstate__`：

    def __getstate__(self):
        return {'_data': list(self._evaluate())}

子类未覆盖它，于是：
- **丢失子类状态**：Table 的 `_columns`/`_name`、Row 的 `_table`/`_row_index`、
  Column 的 `_table`/`_col_index`/`_col_name` 全丢；
- **行被物化成 dict**：`_evaluate()` 对 Table 产出的是行表示，往返后
  `_data` 变成 `[{'id':1,...}]` 而不是 `[[1,...]]`。

实测：`copy.deepcopy(Table(...))` 得到**无列名的畸形表**；`pickle` 同理；
`vools.serialize`（pickle/json 后端）往返损坏。

修复：Row/Column/Table 各自补显式状态协议，完整保存槽字段与 `__dict__`，
并把瞬态字段（`_active_op` lambda、`_origin` 迭代器、`_ops`）排除、恢复时给默认值；
同时兼容旧 `{'_data': [...]}` 状态。
"""

import copy
import pickle

import pytest

from vools.data.qax import Qax
from vools.data.table import Table
from vools.serialize import dumps, loads


def _table():
    return Table([[1, 'a'], [2, 'b']], columns=['id', 'name'], name='T')


class TestDeepcopy:
    def test_columns_preserved(self):
        d = copy.deepcopy(_table())
        assert d._columns == ['id', 'name']

    def test_data_preserved(self):
        d = copy.deepcopy(_table())
        assert d._data == [[1, 'a'], [2, 'b']]

    def test_name_preserved(self):
        assert copy.deepcopy(_table())._name == 'T'

    def test_copy_is_independent(self):
        t = _table()
        d = copy.deepcopy(t)
        d.set_name('X')
        d.set_cell(0, 1, 'CHANGED')
        assert t._name == 'T'
        assert t._data[0] == [1, 'a']

    def test_copy_still_chainable(self):
        d = copy.deepcopy(_table())
        assert d.set_name('Y') is d
        assert d.rows() == 2


class TestPickleRoundTrip:
    def test_table(self):
        p = pickle.loads(pickle.dumps(_table()))
        assert p._columns == ['id', 'name']
        assert p._data == [[1, 'a'], [2, 'b']]
        assert p._name == 'T'

    def test_table_usable_after_roundtrip(self):
        p = pickle.loads(pickle.dumps(_table()))
        assert p.rows() == 2
        assert p.column('name') == ['a', 'b']
        assert p.set_name('Z') is p

    def test_qax(self):
        q = Qax([[1, 'a']], columns=['id', 'name'])
        p = pickle.loads(pickle.dumps(q))
        assert type(p).__name__ == 'Qax'
        assert p._columns == ['id', 'name']
        assert p._data == [[1, 'a']]

    def test_row(self):
        row = _table().get_row(1)
        assert list(pickle.loads(pickle.dumps(row))) == [2, 'b']

    def test_column(self):
        col = _table().get_col('name')
        assert list(pickle.loads(pickle.dumps(col))) == ['a', 'b']


class TestSerializeIntegration:
    @pytest.mark.parametrize('backend', ['pickle', 'json'])
    def test_roundtrip(self, backend):
        t = _table()
        back = loads(dumps(t, backend=backend), backend=backend)
        assert back._columns == ['id', 'name']
        assert back._data == [[1, 'a'], [2, 'b']]

    def test_nested_list(self):
        t, q = _table(), Qax([[1, 'a']], columns=['id', 'name'])
        back = loads(dumps([t, q], backend='pickle'), backend='pickle')
        assert back[0]._columns == ['id', 'name']
        assert back[1]._columns == ['id', 'name']


class TestLegacyStateCompat:
    def test_old_seq_state_still_accepted(self):
        t = Table([[1, 'a']], columns=['id', 'name'])
        t.__setstate__({'_data': [[9, 'z']]})
        assert t._data == [[9, 'z']]

    def test_restored_object_has_defaults_for_transient(self):
        p = pickle.loads(pickle.dumps(_table()))
        # 瞬态字段恢复默认，不应缺失
        assert p._ops == []
        assert callable(p._active_op)