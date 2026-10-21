# -*- coding: utf-8 -*-
"""回归测试：QAXSubstr length=0 与 QAXConcat sep 空字段（BUG-249）。

① `QAXSubstr(length=0)`：`end_pos = ... if length else None` 是假值陷阱——
   合法的 0 长度被当成「不限制」→ 返回整条尾部字符串（'abcdef'/'bcdef'），
   应为空串；base `Table.substr` 的 `if end_pos:` 同样吞掉 end_pos=0。
② `QAXConcat(sep=...)`：拼接时过滤空字符串字段 → 分隔符数量与列数脱钩
   （('a','','c') + '-' → 'a-c'，期望 'a--c'），后续按分隔符 split 会列错位。
   同时删除其 sep 分支建临时列→拷贝→又从原列读→删列的纯死代码。
"""

import pytest

from vools.data.qax import Qax


def _mks():
    return Qax([['abcdef'], ['xyz']], columns=['s'])


class TestSubstrZeroLength:
    def test_zero_length_empty_string(self):
        t = _mks()
        t.QAXSubstr('s', 1, 0, new_col='r')
        assert t.GetCol('r') == ['', '']

    def test_zero_length_with_start(self):
        t = _mks()
        t.QAXSubstr('s', 2, 0, new_col='r')
        assert t.GetCol('r') == ['', '']

    def test_normal_length(self):
        t = _mks()
        t.QAXSubstr('s', 1, 3, new_col='r')
        assert t.GetCol('r') == ['abc', 'xyz']

    def test_length_none_takes_rest(self):
        t = _mks()
        t.QAXSubstr('s', 2, None, new_col='r')
        assert t.GetCol('r') == ['bcdef', 'yz']

    def test_start_with_length(self):
        t = _mks()
        t.QAXSubstr('s', 2, 3, new_col='r')
        assert t.GetCol('r') == ['bcd', 'yz']


class TestConcatSeparator:
    def test_empty_field_keeps_placeholder(self):
        t = Qax([['a', '', 'c'], ['x', 'y', 'z']],
                columns=['c1', 'c2', 'c3'])
        t.QAXConcat(['c1', 'c2', 'c3'], 'joined', sep='-')
        assert t.GetCol('joined') == ['a--c', 'x-y-z']

    def test_none_renders_empty(self):
        t = Qax([[None, 'b', 'c']], columns=['c1', 'c2', 'c3'])
        t.QAXConcat(['c1', 'c2', 'c3'], 'joined', sep='-')
        assert t.GetCol('joined') == ['-b-c']

    def test_no_sep_unchanged(self):
        t = Qax([['a', 'b'], ['c', 'd']], columns=['x', 'y'])
        t.QAXConcat(['x', 'y'], 'j')
        assert t.GetCol('j') == ['ab', 'cd']

    def test_no_extra_columns_left(self):
        # 死代码临时列已删除：只应多出目标列
        t = Qax([['a', 'b']], columns=['x', 'y'])
        t.QAXConcat(['x', 'y'], 'j', sep='-')
        assert t.QAXColNames() == ['x', 'y', 'j']