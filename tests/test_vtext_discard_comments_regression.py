# -*- coding: utf-8 -*-
"""回归测试：discard_comments 不破坏字符串字面量（BUG-358）。

原实现用正则全局删除注释：

    re.sub(r'--.*?$|/\\*.*?\\*/', '', text, flags=MULTILINE | DOTALL)

于是**字符串/标识符字面量内**的 `--`、`/* */` 也被当成注释删掉，整条 SQL 被截断：

    SELECT '--not comment' AS c;   ->   SELECT '                （后半句丢失）
    SELECT '/*x*/' AS c;           ->   SELECT '' AS c;
    SELECT "--x" FROM t;           ->   SELECT "

修复：改为字符扫描器 `_strip_sql_comments`，跳过单引号/双引号/反引号内的
内容（含 SQL 的 `''`、`""` 转义），只移除引号外的 `-- 行注释` 与
`/* 块注释 */`；未闭合的引号/块注释按原样保留（不崩、不丢内容）。
真实注释剔除与空行丢弃行为不变。
"""

import pytest

from vools.data.vtext import VText


class TestLiteralsPreserved:
    def test_double_dash_in_string(self):
        # 修复前：'SELECT ' （整句被截断）
        sql = "SELECT '--not comment' AS c;"
        assert str(VText(sql).discard_comments()) == sql

    def test_block_comment_marker_in_string(self):
        sql = "SELECT '/*x*/' AS c;"
        assert str(VText(sql).discard_comments()) == sql

    def test_double_dash_in_double_quotes(self):
        sql = 'SELECT "--x" FROM t;'
        assert str(VText(sql).discard_comments()) == sql

    def test_escaped_quotes(self):
        sql = "SELECT 'it''s -- ok' AS c;"
        assert str(VText(sql).discard_comments()) == sql

    def test_backticks(self):
        sql = 'SELECT `a--b` FROM t;'
        assert str(VText(sql).discard_comments()) == sql

    def test_json_like_literal(self):
        sql = """SELECT '{"k": "/*not*/"}' AS j;"""
        assert str(VText(sql).discard_comments()) == sql


class TestRealCommentsStillRemoved:
    def test_trailing_line_comment(self):
        assert str(VText('SELECT 1; -- note').discard_comments()) == 'SELECT 1; '

    def test_whole_line_comment(self):
        assert str(VText('-- note\nSELECT 1;').discard_comments()) == 'SELECT 1;'

    def test_inline_block_comment(self):
        assert str(VText('SELECT /* x */ 1;').discard_comments()) == 'SELECT  1;'

    def test_multiline_block_comment(self):
        assert str(VText('SELECT /* a\nb */ 1;').discard_comments()) == 'SELECT  1;'

    def test_empty_lines_dropped(self):
        assert str(VText('-- a\n\nSELECT 1;\n\n').discard_comments()) == 'SELECT 1;'

    def test_comment_after_literal(self):
        sql = "SELECT '--x' FROM t; -- real comment"
        assert str(VText(sql).discard_comments()) == "SELECT '--x' FROM t; "


class TestUnterminatedInput:
    def test_unterminated_quote_kept(self):
        # 不崩，且内容不丢
        assert str(VText("SELECT 'abc").discard_comments()) == "SELECT 'abc"

    def test_unterminated_block_comment(self):
        assert str(VText('SELECT 1 /* abc').discard_comments()) == 'SELECT 1 '


class TestMoveTrailingCommasUnaffected:
    def test_still_moves_without_discard(self):
        out = str(VText('a,  -- c\nb').move_trailing_commas(discard_comment=False))
        assert ',' in out and '\n' in out