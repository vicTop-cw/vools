# -*- coding: utf-8 -*-
"""回归测试：Table.where 静默拒绝无法与"无匹配"区分（BUG-502）。

``_parse_where_expr`` 对**语法错误 / 未知列名 / 非白名单节点**一律返回 False，
这是 BUG-94 有意的**安全拒绝语义**（见 tests/data/test_table_where_safety.py）。
代价是调用方完全拿不到信号：

    t.where("age >")      # → 空表（语法错误？还是没有匹配行？无法区分）
    t.where("nope > 1")   # → 空表（未知列名）

本轮新增强制关键字 ``strict=True``（默认 False，安全拒绝语义完全不变）：
一旦表达式语法错误、引用未知列或含不允许的节点，立即抛 ValueError 并说明原因。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def table():
    return Table([["Alice", 30], ["Bob", 25]], columns=["name", "age"])


class TestStrictModeRaises:
    @pytest.mark.parametrize("expr", ["age >", "age >>>", "and", ""])
    def test_syntax_errors(self, table, expr):
        with pytest.raises(ValueError) as ei:
            table.where(expr, strict=True)
        assert "where 表达式" in str(ei.value)

    @pytest.mark.parametrize("expr", ["nope > 1", "unknown_col == 1"])
    def test_unknown_column(self, table, expr):
        with pytest.raises(ValueError):
            table.where(expr, strict=True)

    @pytest.mark.parametrize("expr", [
        "__import__('os').system('echo x')",
        "open('/etc/passwd')",
        "age.__class__",
    ])
    def test_dangerous_nodes(self, table, expr):
        with pytest.raises(ValueError):
            table.where(expr, strict=True)

    def test_valid_expression_passes(self, table):
        assert table.where("age > 28", strict=True)._data == [["Alice", 30]]


class TestDefaultSafetySemanticsUnchanged:
    """BUG-94 的安全拒绝语义（返回 False → 空表）必须保持不变。"""

    @pytest.mark.parametrize("expr", [
        "age >", "nope > 1", "__import__('os')", "open('/etc/passwd')",
        "age.__class__", "globals()", "lambda: 1",
    ])
    def test_returns_empty_not_raises(self, table, expr):
        assert table.where(expr)._data == []

    def test_injection_has_no_side_effect(self, table):
        # 关键安全断言：表达式不得被执行（返回空表而非报错/产生副作用）
        assert table.where("__import__('os').system('echo pwned')")._data == []


class TestValidExpressionsUnchanged:
    def test_comparison(self, table):
        assert table.where("age > 28")._data == [["Alice", 30]]
        assert table.where("28 > age")._data == [["Bob", 25]]

    def test_boolean_ops(self, table):
        assert table.where("age >= 30 and name == 'Alice'")._data == [["Alice", 30]]
        assert table.where("not (age > 30)")._data == [["Alice", 30], ["Bob", 25]]

    def test_in_operator(self, table):
        assert table.where("age in [25, 30]")._data == [["Alice", 30], ["Bob", 25]]

    def test_callable_predicate(self, table):
        assert table.where(lambda r: r["age"] > 26)._data == [["Alice", 30]]

    def test_type_error_for_non_str_non_callable(self, table):
        with pytest.raises(TypeError):
            table.where(123)

    def test_strict_is_keyword_only(self):
        import inspect

        params = inspect.signature(Table.where).parameters
        assert params["strict"].kind is inspect.Parameter.KEYWORD_ONLY
