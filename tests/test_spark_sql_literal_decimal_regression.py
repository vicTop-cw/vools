# -*- coding: utf-8 -*-
"""回归测试：Spark SQL 字面量转换支持 Decimal（BUG-315）。

Spark 后端没有服务端参数绑定（BUG-234 改为安全代值），`_quote_sql_literal`
负责把参数转成 SQL 字面量。原实现数值分支只覆盖 `int`/`float`，
`decimal.Decimal` 落到末尾 fallback 被**加引号成字符串**：

    _quote_sql_literal(Decimal('1.25'))  ->  "'1.25'"     # 应 1.25

语义后果：金额比较靠隐式 cast 才成立、算术表达式报错、INSERT 把字符串写进
数值列。修复：在数值分支后补 `Decimal`（用 `str` 而非 `repr`，避免产出
`Decimal('1.25')` 这种函数调用语法）。
"""

import datetime
import decimal

import pytest

from vools.sql.spark.connection import _format_sql_params, _quote_sql_literal


class TestDecimalLiterals:
    @pytest.mark.parametrize('value,expected', [
        (decimal.Decimal('1.25'), '1.25'),
        (decimal.Decimal('-10.50'), '-10.50'),
        (decimal.Decimal('42'), '42'),
        (decimal.Decimal('0.001'), '0.001'),
    ])
    def test_decimal_not_quoted(self, value, expected):
        assert _quote_sql_literal(value) == expected

    def test_decimal_in_sql(self):
        sql = _format_sql_params(
            'SELECT * FROM t WHERE amt > %s', [decimal.Decimal('9.99')])
        assert sql == 'SELECT * FROM t WHERE amt > 9.99'


class TestOtherTypesUnchanged:
    @pytest.mark.parametrize('value,expected', [
        (1, '1'), (1.5, '1.5'), (-2, '-2'),
        ('abc', "'abc'"), ("it's", "'it''s'"),
        (None, 'NULL'), (True, 'TRUE'), (False, 'FALSE'),
        (datetime.date(2026, 1, 2), "'2026-01-02'"),
    ])
    def test_literal(self, value, expected):
        assert _quote_sql_literal(value) == expected

    def test_like_pattern_preserved(self):
        # BUG-234 面：SQL 内的字面 % 不被占位符替换误伤
        assert _format_sql_params(
            "SELECT * FROM t WHERE a LIKE '%x%' AND b = %s", ['v']
        ) == "SELECT * FROM t WHERE a LIKE '%x%' AND b = 'v'"

    def test_param_count_mismatch_still_raises(self):
        with pytest.raises(ValueError):
            _format_sql_params('a=%s b=%s', [1])