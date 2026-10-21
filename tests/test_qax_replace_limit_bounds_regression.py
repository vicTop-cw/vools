# -*- coding: utf-8 -*-
"""回归测试：QAXReplace 1-based 列号与 Table.limit 负数校验（BUG-247）。

BUG-246 同族残留（同轮修复后复查相邻 API 发现）：
① `Qax.QAXReplace(col=int)` docstring 明示「列号从1开始」，实现 `col - 1`
   无校验 → `col=0`/`-1` 经负索引**静默改最后一列**、`col>列数` 静默 no-op；
② `Table.limit(n, offset)` 的 `end = min(offset + n, len)` 在 `n<0` 时是负切片
   → `limit(-1)` 静默返回「去掉最后一行」，`QAXTop(-1)` 同样错行；
③ `Table.replace(col_num)` 0 基内部 API：`col_num=-1` 直接命中 `row[-1]`、
   越界静默 no-op。

修复：QAXReplace(int) 复用 `_check_1based`；Table.limit 对负 n/offset 抛
ValueError；Table.replace 对越界 col_num 抛 IndexError（非 int 抛 TypeError）。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


def _mk():
    return Qax([[1, 'a', 10], [2, 'b', 20], [3, 'c', 30]],
               columns=['id', 'name', 'v'])


class TestQaxReplaceCol:
    def test_zero_raises(self):
        with pytest.raises(IndexError, match="列号必须在 1..3"):
            _mk().QAXReplace(10, 99, col=0)

    def test_negative_raises(self):
        with pytest.raises(IndexError):
            _mk().QAXReplace(10, 99, col=-1)

    def test_beyond_raises(self):
        with pytest.raises(IndexError):
            _mk().QAXReplace(10, 99, col=5)

    def test_valid_int_column(self):
        t = _mk()
        t.QAXReplace(10, 99, col=3)
        assert t._data[0][2] == 99

    def test_column_by_name(self):
        t = _mk()
        t.QAXReplace(10, 88, col='v')
        assert t._data[0][2] == 88

    def test_all_columns(self):
        t = _mk()
        t.QAXReplace('a', 'A')
        assert t._data[0][1] == 'A'


class TestLimitNegative:
    def test_negative_n(self):
        with pytest.raises(ValueError, match="n 必须 >= 0"):
            _mk().limit(-1)

    def test_negative_offset(self):
        with pytest.raises(ValueError, match="offset 必须 >= 0"):
            _mk().limit(2, offset=-1)

    def test_qax_top_negative(self):
        with pytest.raises(ValueError):
            _mk().QAXTop(-1)

    def test_valid_limit(self):
        assert _mk().limit(2).rows() == 2
        assert _mk().limit(0).rows() == 0
        assert _mk().limit(2, offset=1).rows() == 2


class TestTableReplace:
    def test_negative_raises(self):
        t = Table([[1, 2]], columns=['a', 'b'])
        with pytest.raises(IndexError, match="0..1"):
            t.replace(-1, 2, 9)

    def test_beyond_raises(self):
        t = Table([[1, 2]], columns=['a', 'b'])
        with pytest.raises(IndexError):
            t.replace(5, 2, 9)

    def test_non_int_raises(self):
        t = Table([[1, 2]], columns=['a', 'b'])
        with pytest.raises(TypeError):
            t.replace(True, 2, 9)

    def test_valid(self):
        t = Table([[1, 2]], columns=['a', 'b'])
        t.replace(1, 2, 9)
        assert t._data[0] == [1, 9]