# -*- coding: utf-8 -*-
"""回归测试：Excel 列号互转的输入校验（BUG-338）。

原实现没有任何校验，非法输入会**静默产出垃圾值**：

    excel_column_to_number('A1')   -> 11       # '1' 也被按 ord-64 计算
    excel_column_to_number('0')    -> -16
    excel_column_to_number(' A')   -> -831
    excel_column_to_number('中文')  -> 544601
    excel_number_to_column(0)      -> ''       # 静默空串
    excel_number_to_column(-1)     -> ''

非字母字符/非法列号会静默变成"看似有效"的数字或空串，下游按列号定位会错列。
修复：`col` 必须是纯 ASCII 字母、`num` 必须是正整数，否则显式报错。

合法映射（含 1-based 与往返）行为不变。
"""

import pytest

from vools.utils.tools import excel_column_to_number, excel_number_to_column


class TestColumnToNumberValid:
    @pytest.mark.parametrize('col,expected', [
        ('A', 1), ('B', 2), ('Z', 26),
        ('AA', 27), ('AB', 28), ('AZ', 52), ('BA', 53),
        ('ZZ', 702), ('AAA', 703), ('XFD', 16384),
        ('a', 1), ('aa', 27),
    ])
    def test_valid(self, col, expected):
        assert excel_column_to_number(col) == expected


class TestColumnToNumberInvalid:
    @pytest.mark.parametrize('bad', ['', 'A1', '0', ' A', 'A ', '中文', 'A-B', '1A'])
    def test_invalid_letters_raise(self, bad):
        # 修复前：返回 11 / -16 / -831 / 544601 等垃圾值
        with pytest.raises(ValueError):
            excel_column_to_number(bad)

    @pytest.mark.parametrize('bad', [None, 1, 1.5, ['A']])
    def test_non_str_raises_typeerror(self, bad):
        with pytest.raises(TypeError):
            excel_column_to_number(bad)


class TestNumberToColumnValid:
    @pytest.mark.parametrize('num,expected', [
        (1, 'A'), (2, 'B'), (26, 'Z'),
        (27, 'AA'), (28, 'AB'), (52, 'AZ'), (53, 'BA'),
        (702, 'ZZ'), (703, 'AAA'), (16384, 'XFD'),
    ])
    def test_valid(self, num, expected):
        assert excel_number_to_column(num) == expected


class TestNumberToColumnInvalid:
    @pytest.mark.parametrize('bad', [0, -1, -26])
    def test_non_positive_raises(self, bad):
        # 修复前：静默返回空串 ''
        with pytest.raises(ValueError):
            excel_number_to_column(bad)

    @pytest.mark.parametrize('bad', [1.5, '5', None, True])
    def test_non_int_raises(self, bad):
        with pytest.raises(TypeError):
            excel_number_to_column(bad)


class TestRoundTrip:
    @pytest.mark.parametrize('num', [1, 26, 27, 52, 53, 500, 702, 703, 16384])
    def test_roundtrip(self, num):
        assert excel_column_to_number(excel_number_to_column(num)) == num

    @pytest.mark.parametrize('col', ['A', 'Z', 'AA', 'ZZ', 'XFD'])
    def test_roundtrip_back(self, col):
        assert excel_number_to_column(excel_column_to_number(col)) == col