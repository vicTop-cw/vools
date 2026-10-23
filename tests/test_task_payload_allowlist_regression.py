# -*- coding: utf-8 -*-
"""回归测试：任务载荷的白名单与本库数据类型对齐（BUG-331）。

`vools/task/core/models.py` 的载荷序列化/反序列化此前不对称：

- 写入：`_dump_json` 对**任何**不可 JSON 序列化的对象都 `pickle.dumps` 成
  `__vools_pickle__:<base64>` 标记；
- 读取：`_safe_pickle_loads` 的 `_SafeUnpickler._ALLOWED` 只放行
  builtins/datetime/decimal/uuid/collections（BUG-207 的受限反序列化），
  `vools` 自己的数据类型**不在白名单** → `UnpicklingError` →
  `_restore_pickle` **静默**返回标记字符串。

实测（端到端 TaskQueue + Worker）：
    q.submit(consume, Table([[1,'a']], columns=['id','name'], name='ARG'))
    -> worker 收到的实参是 `'__vools_pickle__:...'` 字符串，
       结果 ('str', None, None, None)

修复：
1. `_SafeUnpickler._ALLOWED` 增补本库数据类型的**显式白名单**
   （vools.data.table.{Table,Row,Column}、vools.data.qax.Qax、
   vools.data.vlist.VList、vools.data.vtext.VText、vools.data.seq.{Seq,SeqBase}、
   vools.datetime.vdate_class.VDate），不放行整个 `vools.` 前缀；
2. 恢复失败不再静默——`warnings.warn(RuntimeWarning)` 明示「已按原始标记字符串返回」。

安全回归：恶意 `__reduce__` 载荷（os.system）仍被拒且会告警，不执行任何代码。
"""

import base64
import os
import pickle
import warnings

import pytest

from vools.data.qax import Qax
from vools.data.table import Table
from vools.data.vlist import VList
from vools.task.core.models import _dump_json, _load_json


def _table():
    return Table([[1, 'a'], [2, 'b']], columns=['id', 'name'], name='T')


# 任务函数必须定义在模块级：TaskQueue 以 '<module>:<name>' 路径恢复函数，
# 定义在测试方法内（__qualname__ 含 <locals>）无法按路径取回。
def _consume_table(table):
    return (type(table).__name__, getattr(table, '_columns', None),
            getattr(table, '_data', None), getattr(table, '_name', None))


def _produce_table():
    return _table()


class _CustomPayload:
    """模块级自定义类：用于验证「未在白名单的用户类」仍被拒绝。"""
    pass


class TestVoolsTypesRoundTrip:
    def test_list_of_table(self):
        back = _load_json(_dump_json([_table()]))
        assert type(back[0]).__name__ == 'Table'
        assert back[0]._columns == ['id', 'name']
        assert back[0]._data == [[1, 'a'], [2, 'b']]

    def test_dict_value_qax(self):
        back = _load_json(_dump_json({'q': Qax([[1, 'a']], columns=['id', 'name'])}))
        assert type(back['q']).__name__ == 'Qax'
        assert back['q']._columns == ['id', 'name']

    def test_vlist(self):
        back = _load_json(_dump_json(VList([1, 2, 3])))
        assert type(back).__name__ == 'VList'
        assert list(back) == [1, 2, 3]

    def test_nested_containers(self):
        back = _load_json(_dump_json({'a': [_table()], 'b': {'c': Qax([[1]], columns=['x'])}}))
        assert type(back['a'][0]).__name__ == 'Table'
        assert type(back['b']['c']).__name__ == 'Qax'

    def test_row_column(self):
        t = _table()
        back = _load_json(_dump_json([t.get_row(0), t.get_col('id')]))
        assert type(back[0]).__name__ == 'Row'
        assert type(back[1]).__name__ == 'Column'
        assert list(back[0]) == [1, 'a']
        assert list(back[1]) == [1, 2]


class TestTaskQueueEndToEnd:
    def _run(self, db, func, *args, **kwargs):
        from vools.task.core.queue import TaskQueue
        from vools.task.core.worker import Worker
        q = TaskQueue(db)
        tid = q.submit(func, *args, **kwargs)
        Worker('w1', db, lease_seconds=30)._process_one_task()
        return q.get_result(tid, timeout=10)

    def test_table_argument(self, tmp_path):
        res = self._run(str(tmp_path / 'a.db'), _consume_table, _table())
        assert list(res[:2]) == ['Table', ['id', 'name']]
        assert res[2] == [[1, 'a'], [2, 'b']]
        assert res[3] == 'T'

    def test_table_return_value(self, tmp_path):
        res = self._run(str(tmp_path / 'b.db'), _produce_table)
        assert type(res).__name__ == 'Table'
        assert res._columns == ['id', 'name']


class TestSecurityStillEnforced:
    def _evil_marker(self):
        class Evil:
            def __reduce__(self):
                return (os.system, ('echo SHOULD_NOT_RUN',))

        return '__vools_pickle__:' + base64.b64encode(
            pickle.dumps(Evil())).decode()

    def test_malicious_payload_rejected_with_warning(self):
        marker = self._evil_marker()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            back = _load_json('["' + marker + '"]')
        # 未被反序列化（仍是原始标记字符串），且给出可见告警
        assert isinstance(back[0], str)
        assert back[0].startswith('__vools_pickle__:')
        assert any(issubclass(w.category, RuntimeWarning) for w in caught)

    def test_unknown_user_class_still_rejected(self):
        marker = '__vools_pickle__:' + base64.b64encode(
            pickle.dumps(_CustomPayload())).decode()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            back = _load_json('["' + marker + '"]')
        assert isinstance(back[0], str)
        assert caught, '拒绝时应有告警，不静默降级'

    def test_allowed_stdlib_types_unaffected(self):
        import datetime
        import decimal
        back = _load_json(_dump_json([
            datetime.date(2026, 1, 2), decimal.Decimal('1.25'), {'a': 1}]))
        assert back[0] == datetime.date(2026, 1, 2)
        assert back[1] == decimal.Decimal('1.25')