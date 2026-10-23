# -*- coding: utf-8 -*-
"""回归测试：未知列名不再被静默跳过（BUG-319）。

`Table.substr` / `split` / `concat` 原先对**未知列名静默 no-op 或产出部分结果**：

- `substr('new', 'naem', 1, 3)`：源列名拼错 → `return self`，目标列也不创建；
- `split('naem', '-', ['p1','p2'])`：同样静默；
- `concat('new', ['id','naem'])`：未知列被静默跳过，目标列被写成「其余列的拼接」
  （部分结果，无提示）。

而同一 API 的 `get_col` / `column` / `at` / `del_col` / `to_num` 对未知列抛
`KeyError`——四处不一致且失败不可见（BUG-249/250/251/253 同族残留）。

修复：三处统一走 `_get_col_index` / 显式 `KeyError`。

注：`set_ordinal` 的「未知列静默返回」是**既有并被独立回归锁定**的行为
（tests/data/test_table_bug_252_253_254_255_regression.py::
test_set_ordinal_nonexistent_col_silent），本条不动它。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def t():
    return Table([[1, 'a-b'], [2, 'c-d']], columns=['id', 'name'])


class TestUnknownColumnRaises:
    def test_substr_unknown_source_column(self, t):
        # 修复前：静默返回原表（目标列都没建）
        with pytest.raises(KeyError):
            t.substr('new', 'naem', 1, 2)

    def test_split_unknown_column(self, t):
        with pytest.raises(KeyError):
            t.split('naem', '-', ['p1', 'p2'])

    def test_concat_unknown_column_in_array(self, t):
        # 修复前：静默跳过 naem，产出"其余列拼接"的部分结果
        with pytest.raises(KeyError):
            t.concat('new', ['id', 'naem'])


class TestKnownColumnsStillWork:
    def test_substr(self, t):
        out = t.substr('new', 'name', 1, 1)
        assert list(out._columns) == ['id', 'name', 'new']
        assert out._data == [[1, 'a-b', 'a'], [2, 'c-d', 'c']]

    def test_split(self, t):
        out = t.split('name', '-', ['p1', 'p2'])
        assert list(out._columns) == ['id', 'name', 'p1', 'p2']
        assert out._data == [[1, 'a-b', 'a', 'b'], [2, 'c-d', 'c', 'd']]

    def test_concat(self, t):
        out = t.concat('new', ['id', 'name'])
        assert list(out._columns) == ['id', 'name', 'new']
        assert out._data == [[1, 'a-b', '1a-b'], [2, 'c-d', '2c-d']]


class TestSetOrdinalLockedSilent:
    def test_unknown_column_stays_silent(self, t):
        # 既有并已被独立回归锁定（BUG-255 面）：未知列静默返回 self
        assert t.set_ordinal('naem', 1) is t

    def test_ordinal_out_of_range_still_indexerror(self, t):
        with pytest.raises(IndexError):
            t.set_ordinal('name', 9)