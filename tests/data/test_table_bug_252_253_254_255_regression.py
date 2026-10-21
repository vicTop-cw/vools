"""
BUG-252/253/254/255 回归测试 — Table/Qax 行列边界行为。
"""
import pytest
from vools.data import Table, Qax


# ─── BUG-252: max/min 在无匹配数据时应返回 None，而非 Table(empty) ───


class TestMaxMinEmptyReturn:
    def test_max_empty_table_returns_none(self):
        t = Table([], columns=['a', 'b'])
        assert t.max('a') is None

    def test_min_empty_table_returns_none(self):
        t = Table([], columns=['a', 'b'])
        assert t.min('a') is None

    def test_max_non_numeric_column_returns_none(self):
        t = Table([['x', 'y']], columns=['a', 'b'])
        assert t.max('a') is None

    def test_min_non_numeric_column_returns_none(self):
        t = Table([['x', 'y']], columns=['a', 'b'])
        assert t.min('a') is None

    def test_max_with_valid_numbers_still_works(self):
        t = Table([[1, 2], [3, 4]], columns=['a', 'b'])
        assert t.max('a') == 3

    def test_min_with_valid_numbers_still_works(self):
        t = Table([[1, 2], [3, 4]], columns=['a', 'b'])
        assert t.min('a') == 1


# ─── BUG-253: to_num/to_str/to_date 整数列索引越界应抛 IndexError ───


class TestToIntRangeValidation:
    def test_to_num_valid_zero(self):
        t = Table([['1', '2', '3']], columns=['a', 'b', 'c'])
        result = t.to_num(0)
        assert result.to_list() == [[1, '2', '3']]

    def test_to_num_negative_raises(self):
        t = Table([['1', '2', '3']], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 -1'):
            t.to_num(-1)

    def test_to_num_out_of_range_raises(self):
        t = Table([['1', '2', '3']], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 3'):
            t.to_num(3)

    def test_to_str_negative_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 -1'):
            t.to_str(-1)

    def test_to_str_out_of_range_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 3'):
            t.to_str(3)

    def test_to_date_negative_raises(self):
        t = Table([['2024-01-01']], columns=['a'])
        with pytest.raises(IndexError, match='收到 -1'):
            t.to_date(-1)

    def test_to_date_out_of_range_raises(self):
        t = Table([['2024-01-01']], columns=['a'])
        with pytest.raises(IndexError, match='收到 1'):
            t.to_date(1)


# ─── BUG-254: set_col_name 负索引 / 越界应抛 IndexError ───


class TestSetColNameRangeValidation:
    def test_set_col_name_valid_zero(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        result = t.set_col_name(0, 'x')
        assert result.columns() == ['x', 'b', 'c']

    def test_set_col_name_negative_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 -1'):
            t.set_col_name(-1, 'x')

    def test_set_col_name_out_of_range_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 3'):
            t.set_col_name(3, 'x')


# ─── BUG-255: set_ordinal 越界应抛 IndexError，而非静默钳制 ───


class TestSetOrdinalRangeValidation:
    def test_set_ordinal_valid_zero(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        result = t.set_ordinal('a', 0)
        assert result.columns() == ['a', 'b', 'c']

    def test_set_ordinal_valid_move_to_end(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        result = t.set_ordinal('a', 2)
        assert result.columns() == ['b', 'c', 'a']

    def test_set_ordinal_negative_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 -1'):
            t.set_ordinal('a', -1)

    def test_set_ordinal_out_of_range_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 3'):
            t.set_ordinal('a', 3)

    def test_set_ordinal_nonexistent_col_silent(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        # 列名不存在时保持 silent（与 Qax.SetOrdinal 行为一致）
        result = t.set_ordinal('nonexistent', 0)
        assert result.columns() == ['a', 'b', 'c']


# ─── BUG-253 补充：del_col 整数列索引同步受 _get_col_index 校验保护 ───


class TestDelColRangeValidation:
    def test_del_col_valid_zero(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        result = t.del_col(0)
        assert result.columns() == ['b', 'c']

    def test_del_col_negative_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 -1'):
            t.del_col(-1)

    def test_del_col_out_of_range_raises(self):
        t = Table([[1, 2, 3]], columns=['a', 'b', 'c'])
        with pytest.raises(IndexError, match='收到 3'):
            t.del_col(3)


# ─── BUG-252 补充：Qax.max/min 通过 Table 也应返回 None ───


class TestQaxMaxMinEmpty:
    def test_qax_max_empty_returns_none(self):
        q = Qax([], columns=['a', 'b'])
        assert q.QAXMax('a') is None

    def test_qax_min_empty_returns_none(self):
        q = Qax([], columns=['a', 'b'])
        assert q.QAXMin('a') is None
