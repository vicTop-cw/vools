# -*- coding: utf-8 -*-
"""回归测试：SQL builder 占位符替换不侵入字符串字面量（BUG-232）。

原 `_PLACEHOLDER_PATTERN = r'\?|%s|%\w+|:\w+'` 被直接 `sub()` 整个条件串，
引号内的字面量文本（`'what?'`、时间字面量 `'12:30:00'`、LIKE 模式）被误改
写成当前 paramstyle 的占位符——SQL 文本静默损坏；带参数时字面量 `?` 先占
位还会令参数索引整体错位，查询错值。

修复：按引号切分（SQL 标准 `''` 转义；双引号标识符同样按字面量处理），
仅在引号外片段做占位符替换（`_normalize_condition` 与
`_collect_condition_params` 两处共用 `_sub_placeholders`）。
"""

from vools.sql.core.builder import BaseSqlBuilder


class TestLiteralsPreserved:
    """BUG-232 核心：引号内文本原样保留。"""

    def test_question_mark_in_literal(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where("name = 'what?'").build())
        assert sql == "SELECT * FROM t WHERE name = 'what?'"
        assert params == ()

    def test_time_literal_not_mangled(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where("ts > '12:30:00'").build())
        assert sql == "SELECT * FROM t WHERE ts > '12:30:00'"
        assert params == ()

    def test_literal_plus_real_param_indexing(self):
        # 字面量 ? 不得占位，真实参数编号从 0 起
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where("name = 'x?' AND id = ?", 1).build())
        assert sql == "SELECT * FROM t WHERE name = 'x?' AND id = %s"
        assert params == (1,)

    def test_escaped_quote(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where("name = 'it''s ?' AND x = ?", 9).build())
        assert sql == "SELECT * FROM t WHERE name = 'it''s ?' AND x = %s"
        assert params == (9,)

    def test_double_quoted_identifier(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('"col?" = ?', 3).build())
        assert sql == 'SELECT * FROM t WHERE "col?" = %s'
        assert params == (3,)


class TestMultiConditionCrossReindex:
    """多条件跨 where/and_ 的占位符编号正确（不因字面量错位）。"""

    def test_mixed_conditions(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where("a = ?", 1)
                       .and_("b = 'y?'")
                       .and_("c = ?", 2)
                       .build())
        assert sql == "SELECT * FROM t WHERE a = %s AND b = 'y?' AND c = %s"
        assert params == (1, 2)


class TestNormalPlaceholdersUnchanged:
    """正常占位符路径保持（防修复过度）。"""

    def test_single_param(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('id = %s', 5).build())
        assert sql == 'SELECT * FROM t WHERE id = %s'
        assert params == (5,)

    def test_question_style_input(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('id = ?', 7).build())
        assert sql == 'SELECT * FROM t WHERE id = %s'
        assert params == (7,)

    def test_no_where(self):
        sql, params = BaseSqlBuilder().select('id').from_('t').build()
        assert sql == 'SELECT id FROM t'
        assert params == ()