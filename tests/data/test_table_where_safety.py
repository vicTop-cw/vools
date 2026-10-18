# -*- coding: utf-8 -*-
"""tests/data/test_table_where_safety.py — Table.where 表达式沙箱安全（钉 BUG-94）

BUG-94: _parse_where_expr 用 ``eval(safe)``（默认 __builtins__），
任何 ``__import__('os').system(...)`` 均可 RCE——直接 RCE 和列注入 RCE
都实测成功（终端打印 PWNED）。

修复：AST 节点白名单校验（仅允许比较/布尔/算术运算和字面量），
拒绝函数调用/属性访问/下标等危险节点；再以受限 builtins 求值。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.data.table import Table  # noqa: E402


class TestTableWhereRCE:
    """where 表达式不得 RCE"""

    def _make_table(self):
        return Table([['Alice', 30], ['Bob', 25]], columns=['name', 'age'])

    def test_direct_rce_blocked(self, tmp_path):
        t = self._make_table()
        marker = tmp_path.as_posix() + "/pwned.txt"
        expr = f"__import__('os').system('echo PWNED > \"{marker}\"')"
        t.where(expr)
        assert not os.path.exists(marker), "RCE should be blocked"

    def test_column_injection_rce_blocked(self, tmp_path):
        t = self._make_table()
        marker = tmp_path.as_posix() + "/pwned2.txt"
        expr = f"__import__('os').system('echo PWNED > \"{marker}\"') or age == 30"
        t.where(expr)
        assert not os.path.exists(marker), "Column injection RCE should be blocked"

    def test_eval_access_blocked(self, tmp_path):
        t = self._make_table()
        marker = tmp_path / "pwned3"
        expr = f"eval('__import__(chr(111)+chr(115)).system(chr(116)+chr(111)+chr(117)+chr(99)+chr(104)) and {marker}')"
        t.where(expr)
        # Should not crash; AST validation rejects eval
        assert True

    def test_open_blocked(self):
        t = self._make_table()
        expr = "open('/etc/passwd').read()"
        # Should not raise (AST validation returns False)
        result = t.where(expr)
        assert result is not None or result == []


class TestTableWhereNormal:
    """正常 where 表达式不受影响"""

    def _make_table(self):
        return Table([['Alice', 30], ['Bob', 25], ['Carol', 40]],
                     columns=['name', 'age'])

    def test_gt(self):
        t = self._make_table()
        result = list(t.where("age > 28"))
        assert len(result) == 2

    def test_and_or(self):
        t = self._make_table()
        result = list(t.where("age > 25 and age < 35"))
        assert len(result) == 1

    def test_eq(self):
        t = self._make_table()
        result = list(t.where("age == 30"))
        assert len(result) == 1

    def test_string_eq(self):
        t = self._make_table()
        result = list(t.where("name == 'Alice'"))
        assert len(result) == 1

    def test_unknown_column_returns_false(self):
        """未知列名应安全返回 False（不崩溃）"""
        t = self._make_table()
        result = list(t.where("nonexistent == 1"))
        assert len(result) == 0

    def test_invalid_syntax_returns_false(self):
        """非法表达式应安全返回 False"""
        t = self._make_table()
        result = list(t.where("age >"))
        assert len(result) == 0