# -*- coding: utf-8 -*-
"""回归测试：Qax 转换/计算/列属性类 1-based 越界（BUG-250 + BUG-251）。

第 7 族（1-based API 越界静默错值）收口后的全文件扫描补遗：

BUG-250 —— 转换类三方法 int 分支裸 `col - 1`：
- `QAXColToNum(0)` 经负索引对**最后一列**执行 to_num，无法转数字的值变 None
  （静默数据损毁，最严重）；
- `QAXColToStr(0)` / `QAXColToDate(0)` 同样操作最后一列（转换结果看似正常，
  掩盖了错误列）；负数操作倒数第二列；越界静默 no-op。

BUG-251 —— 计算/列属性三方法：
- `QAXCompute(0, 'sum')` 对最后一列求和并返回数字（静默算错列）；
  `QAXCompute(-1, ...)` 计算失败时静默返回 Table 对象而非数字；
- `SetOrdinal(0, 2)` 实际移动的是最后一列；
  `SetOrdinal('name', 0)` / `('name', -1)` 经负索引把列静默移到最前；
- `SetColName(0/-1/越界)` 静默 no-op。

修复：统一复用 `_check_1based`（列 1..列数 / 新位置 1..列数 → IndexError）。
"""

import pytest

from vools.data.qax import Qax


def _mk():
    return Qax([[1, '10', '2024-01-01'], [2, '20', '2024-02-01']],
               columns=['id', 'num', 'dt'])


class TestColToNumBounds:
    @pytest.mark.parametrize("bad", [0, -1, 4])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(IndexError, match="列号必须在 1..3"):
            _mk().QAXColToNum(bad)

    def test_valid_int(self):
        t = _mk()
        t.QAXColToNum(2)
        assert t._data[0][1] == 10

    def test_valid_name(self):
        t = _mk()
        t.QAXColToNum('num')
        assert t._data[0][1] == 10


class TestColToStrBounds:
    @pytest.mark.parametrize("bad", [0, -1, 4])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(IndexError):
            _mk().QAXColToStr(bad)

    def test_valid(self):
        t = _mk()
        t.QAXColToStr(1)
        assert t._data[0][0] == '1'


class TestColToDateBounds:
    @pytest.mark.parametrize("bad", [0, -1, 4])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(IndexError):
            _mk().QAXColToDate(bad)

    def test_valid(self):
        t = _mk()
        t.QAXColToDate(3)
        assert hasattr(t._data[0][2], 'year')


class TestComputeBounds:
    @pytest.mark.parametrize("bad", [0, -1, 4])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(IndexError):
            _mk().QAXCompute(bad, 'sum')

    def test_valid_int_col(self):
        t = Qax([[1, 10], [2, 20]], columns=['id', 'v'])
        assert t.QAXCompute(2, 'sum') == 30
        assert t.QAXCompute(1, 'sum') == 3


class TestSetColNameBounds:
    @pytest.mark.parametrize("bad", [0, -1, 4])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(IndexError):
            _mk().SetColName(bad, 'r')

    def test_valid_int(self):
        t = _mk()
        t.SetColName(1, 'renamed')
        assert t.QAXColNames()[0] == 'renamed'

    def test_valid_name(self):
        t = _mk()
        t.SetColName('dt', 'date')
        assert t.QAXColNames() == ['id', 'num', 'date']


class TestSetOrdinalBounds:
    @pytest.mark.parametrize("col", [0, -1, 4])
    def test_col_out_of_range_raises(self, col):
        with pytest.raises(IndexError):
            _mk().SetOrdinal(col, 2)

    @pytest.mark.parametrize("new_index", [0, -1, 4])
    def test_new_index_out_of_range_raises(self, new_index):
        with pytest.raises(IndexError):
            _mk().SetOrdinal(1, new_index)

    def test_valid_move_to_end(self):
        t = _mk()
        t.SetOrdinal(1, 3)
        assert t.QAXColNames() == ['num', 'dt', 'id']

    def test_valid_name_first(self):
        t = _mk()
        t.SetOrdinal('num', 1)
        assert t.QAXColNames() == ['num', 'id', 'dt']