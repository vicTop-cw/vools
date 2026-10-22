# -*- coding: utf-8 -*-
"""回归测试：sum/avg 的「仅数字」语义文档对齐（BUG-285）。

实现一直过滤 `isinstance(v, (int, float))`（Row/Column 版 docstring 已写
「仅数字」），但 Table 级（最常用入口）与 QAXSum/QAXAvg 的 docstring 只写
「求和」/「平均值」。而 `Table.from_file` 读 CSV 得到的单元格**全是字符串**，
`from_file(...).sum('amount')` 恒为 0 且无任何告警——文档未声明该语义。

本测试锁定：
① 行为不变（数字字符串仍被忽略 → 0；to_num 转换后正确求和）；
② 四个 docstring 均显式声明「仅数字」语义，防止文档再次漂移。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


def _str_table():
    return Table([[1, '10'], [2, '20']], columns=['id', 'v'])


class TestBehaviorUnchanged:
    def test_numeric_strings_ignored_sum(self):
        # 既有语义：数字字符串被忽略 → 0（文档现已显式声明）
        assert _str_table().sum('v') == 0

    def test_numeric_strings_ignored_avg(self):
        assert _str_table().avg('v') == 0

    def test_to_num_pipeline(self):
        t = _str_table()
        t.to_num('v')
        assert t.sum('v') == 30
        assert t.avg('v') == 15.0

    def test_int_column_unaffected(self):
        t = Table([[1, 10], [2, 20]], columns=['id', 'v'])
        assert t.sum('v') == 30
        assert t.avg('v') == 15.0

    def test_qax_aggregates_same_semantics(self):
        q = Qax([[1, '10'], [2, '20']], columns=['id', 'v'])
        assert q.QAXSum('v') == 0
        assert q.QAXAvg('v') == 0
        q2 = Qax([[1, 10], [2, 20]], columns=['id', 'v'])
        assert q2.QAXSum('v') == 30
        assert q2.QAXAvg('v') == 15.0


class TestDocstringDeclaresSemantics:
    def test_table_sum_docstring(self):
        doc = Table.sum.__doc__ or ''
        assert '仅统计' in doc and '字符串' in doc

    def test_table_avg_docstring(self):
        doc = Table.avg.__doc__ or ''
        assert '仅统计' in doc and '字符串' in doc

    def test_qax_sum_docstring(self):
        doc = Qax.QAXSum.__doc__ or ''
        assert '仅统计' in doc and '字符串' in doc

    def test_qax_avg_docstring(self):
        doc = Qax.QAXAvg.__doc__ or ''
        assert '仅统计' in doc and '字符串' in doc