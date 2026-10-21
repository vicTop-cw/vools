# -*- coding: utf-8 -*-
"""回归测试：Spark 后端参数安全代值（BUG-234）。

原 `execute`/`executemany` 用 `sql % tuple(params)` 裸插值：字符串参数不加
引号不转义（同代码在 sqlite/pg 由驱动绑定安全、spark 上语法坏或注入），
SQL 字面量 `%`（LIKE '%abc%'）被 %-格式化误伤，占位符/参数数量不校验。

修复：只匹配 `%s` 并逐个安全代值（字符串加引号 + `''` 转义、None→NULL、
bool→TRUE/FALSE、数值 repr、日期 ISO 引号、bytes hex），数量不匹配抛
带语义 ValueError；其它 `%` 原样保留。
"""

import datetime

import pytest

from vools.sql.spark.connection import _format_sql_params, _quote_sql_literal


class TestStringQuoting:
    """BUG-234 核心：字符串参数必须引号化并转义。"""

    def test_plain_string(self):
        assert _format_sql_params(
            "SELECT * FROM t WHERE name = %s", ["abc"]
        ) == "SELECT * FROM t WHERE name = 'abc'"

    def test_quote_escaped(self):
        assert _format_sql_params(
            "WHERE name = %s", ["a'b"]
        ) == "WHERE name = 'a''b'"

    def test_injection_neutralized(self):
        assert _format_sql_params(
            "WHERE name = %s", ["x' OR '1'='1"]
        ) == "WHERE name = 'x'' OR ''1''=''1'"


class TestLiteralPercentPreserved:
    """LIKE 等字面量 % 不被 %-格式化误伤。"""

    def test_like_pattern_survives(self):
        assert _format_sql_params(
            "SELECT * FROM t WHERE d LIKE '%abc%' AND id = %s", [1]
        ) == "SELECT * FROM t WHERE d LIKE '%abc%' AND id = 1"


class TestLiteralTypes:
    """各类型字面量映射。"""

    @pytest.mark.parametrize("value,expected", [
        (None, "NULL"),
        (True, "TRUE"),
        (False, "FALSE"),
        (42, "42"),
        (1.5, "1.5"),
        (b"\x01\xff", "'01ff'"),
    ])
    def test_scalars(self, value, expected):
        assert _quote_sql_literal(value) == expected

    def test_date_iso(self):
        assert _quote_sql_literal(datetime.date(2024, 1, 2)) == "'2024-01-02'"


class TestCountValidation:
    """占位符/参数数量不匹配时报语义错误（不再是底层格式化异常）。"""

    def test_fewer_params_than_placeholders(self):
        with pytest.raises(ValueError, match="占位符数量多于参数数量"):
            _format_sql_params("a = %s AND b = %s", [1])

    def test_more_params_than_placeholders(self):
        with pytest.raises(ValueError, match="参数数量多于 SQL 占位符数量"):
            _format_sql_params("a = %s", [1, 2])


class TestExistingSemanticsKept:
    """既有测试锁定的整数路径结果不变。"""

    def test_int_placeholder(self):
        assert _format_sql_params("SELECT %s", (1,)) == "SELECT 1"

    def test_no_placeholder_no_params(self):
        assert _format_sql_params("SELECT 1", []) == "SELECT 1"

    def test_multiple_ints(self):
        assert _format_sql_params("SELECT %s, %s", (1, 2)) == "SELECT 1, 2"