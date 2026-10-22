# -*- coding: utf-8 -*-
"""回归测试：Table.sort 排序失败时的可诊断错误（BUG-294）。

原实现对排序列含 None 或混合类型时抛裸 TypeError
（`'<' not supported between instances of 'int' and 'NoneType'`）——消息里
没有列名，多列多表场景下无法定位；docstring 也未声明限制。

修复：捕获比较 TypeError，重抛 ValueError，消息含列名、涉及类型与清洗建议；
**不改变「None/混合类型不可排序」的语义**（不擅自引入 NULL 排序策略）。
"""

import pytest

from vools.data.table import Table


def _with_none():
    return Table([[1, None], [2, 10], [3, 5]], columns=['id', 'v'])


def _mixed():
    return Table([[1, 'a'], [2, 10]], columns=['id', 'v'])


class TestSortErrorDiagnostics:
    def test_none_raises_value_error_with_column(self):
        with pytest.raises(ValueError, match="'v'"):
            _with_none().sort('v')

    def test_none_desc_raises(self):
        with pytest.raises(ValueError, match='None'):
            _with_none().sort('v', reverse=True)

    def test_mixed_types_raises_with_column(self):
        with pytest.raises(ValueError, match="'v'"):
            _mixed().sort('v')

    def test_order_by_delegates_error(self):
        with pytest.raises(ValueError, match="'v'"):
            _with_none().order_by('v', desc=True)

    def test_message_mentions_remediation(self):
        with pytest.raises(ValueError) as ei:
            _with_none().sort('v')
        msg = str(ei.value)
        assert 'to_num' in msg or '填充' in msg

    def test_docstring_declares_restriction(self):
        doc = Table.sort.__doc__ or ''
        assert 'None' in doc and 'Raises' in doc


class TestSortStillWorks:
    def test_numeric_asc(self):
        t = Table([[2, 20], [1, 10], [3, 30]], columns=['id', 'v'])
        assert t.sort('v')._data == [[1, 10], [2, 20], [3, 30]]

    def test_numeric_desc(self):
        t = Table([[2, 20], [1, 10], [3, 30]], columns=['id', 'v'])
        assert t.sort('v', reverse=True)._data == [[3, 30], [2, 20], [1, 10]]

    def test_strings(self):
        t = Table([[1, 'b'], [2, 'A']], columns=['id', 'v'])
        assert t.sort('v')._data == [[2, 'A'], [1, 'b']]

    def test_unknown_column_still_index_error(self):
        with pytest.raises(ValueError):
            Table([[1, 2]], columns=['a', 'b']).sort('nope')