# -*- coding: utf-8 -*-
"""回归测试：Qax.SetColName 对未知列名抛 KeyError（BUG-320）。

原实现在 `oldName` 是不存在的**列名**时 `except ValueError: return self`
静默 no-op——改名没发生且无任何信号：

    Qax([[1,'a']], columns=['id','name']).SetColName('nope', 'x')
    # 返回 self，列仍为 ['id','name']

同文件其它带列名的方法对未知列均抛 KeyError（QAXColToNum/QAXColToStr/
QAXColToDate/GetCol/DelCol/QAXSplit/QAXConcat/QAXReplace），且 BUG-319 已把
Table.substr/split/concat 的同类静默改为 KeyError——本条补齐 Qax 侧残留。

注：int 列号越界仍抛 IndexError（BUG-251 语义，保持不变）；
QAXColIndex 未知列返回 -1 是 docstring 明写的约定，不在本条改动范围。
"""

import pytest

from vools.data.qax import Qax


@pytest.fixture()
def q():
    return Qax([[1, 'a'], [2, 'b']], columns=['id', 'name'])


class TestUnknownColumnNameRaises:
    def test_unknown_name(self, q):
        # 修复前：静默返回 self，列名不变
        with pytest.raises(KeyError):
            q.SetColName('nope', 'x')

    def test_error_message_contains_name(self, q):
        with pytest.raises(KeyError) as ei:
            q.SetColName('nope', 'x')
        assert 'nope' in str(ei.value)


class TestValidRenamesStillWork:
    def test_by_name(self, q):
        assert q.SetColName('name', 'title') is q
        assert q._columns == ['id', 'title']

    def test_by_one_based_index(self, q):
        assert q.SetColName(2, 'title') is q
        assert q._columns == ['id', 'title']


class TestIntBoundsUnchanged:
    @pytest.mark.parametrize('bad', [0, -1, 9])
    def test_index_out_of_range(self, q, bad):
        with pytest.raises(IndexError):
            q.SetColName(bad, 'x')


class TestSiblingConsistency:
    @pytest.mark.parametrize('call', [
        lambda q: q.DelCol('nope'),
        lambda q: q.GetCol('nope'),
        lambda q: q.QAXColToNum('nope'),
        lambda q: q.QAXColToStr('nope'),
        lambda q: q.QAXColToDate('nope'),
    ])
    def test_siblings_raise_keyerror(self, q, call):
        with pytest.raises(KeyError):
            call(q)

    def test_col_index_sentinel_documented(self, q):
        # QAXColIndex 未知列返回 -1 是文档化约定，不应改成抛错
        assert q.QAXColIndex('nope') == -1
        assert q.QAXColIndex('name') == 2