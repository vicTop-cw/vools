# -*- coding: utf-8 -*-
"""回归测试：BaseSqlBuilder 标识符校验（BUG-459）。

BUG-395 已覆盖 join_type / 条件表达式 / limit-offset；本轮补上**标识符**面：
表名、列名、JOIN 的 ON 条件原为零校验，空串会**静默产出语法非法的 SQL**：

    BaseSqlBuilder().select('*').from_('').build()        # ('SELECT * FROM ', ())
    BaseSqlBuilder().select('*').from_('t').join('u', '').build()
                                                          # ('... ON ', ())
    BaseSqlBuilder().select('').from_('t').build()        # ('SELECT  FROM t', ())
    BaseSqlBuilder().build()                              # ('SELECT *', ())

修复后在**调用点**抛 ValueError；合法 SQL 生成保持不变。
"""

import pytest

from vools.sql.core.builder import BaseSqlBuilder


class TestIdentifierValidation:
    @pytest.mark.parametrize("bad", ["", "   "])
    def test_from_table(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").from_(bad)

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_join_table(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").from_("t").join(bad, "t.id = u.id")

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_join_condition(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").from_("t").join("u", bad)

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_insert_table(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().insert_into(bad)

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_update_table(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().update(bad)

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_delete_table(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().delete_from(bad)

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_select_column(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select(bad)


class TestSelectWithoutFrom:
    def test_empty_builder_rejected(self):
        with pytest.raises(ValueError) as ei:
            BaseSqlBuilder().build()
        assert "FROM" in str(ei.value)

    def test_star_without_from_rejected(self):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").build()


class TestValidSqlGeneration:
    def test_plain_select(self):
        assert BaseSqlBuilder().select("a", "b").from_("t").build() == (
            "SELECT a, b FROM t", ())

    def test_parameterised_where(self):
        assert BaseSqlBuilder().select("*").from_("t").where("a = ?", 1).build() == (
            "SELECT * FROM t WHERE a = %s", (1,))

    def test_join(self):
        assert BaseSqlBuilder().select("*").from_("t").join("u", "t.id = u.id").build() == (
            "SELECT * FROM t INNER JOIN u ON t.id = u.id", ())

    def test_group_having_order_limit_offset(self):
        sql, params = (BaseSqlBuilder().select("a").from_("t").group_by("a")
                       .having("count(*) > 1").order_by("a").limit(10).offset(5).build())
        assert sql == ("SELECT a FROM t GROUP BY a HAVING count(*) > 1 "
                       "ORDER BY a LIMIT %s OFFSET %s")
        assert params == (10, 5)

    def test_insert(self):
        assert BaseSqlBuilder().insert_into("t").values(a=1, b=2).build() == (
            "INSERT INTO t (a, b) VALUES (%s, %s)", (1, 2))

    def test_insert_default_values(self):
        assert BaseSqlBuilder().insert_into("t").values().build() == (
            "INSERT INTO t DEFAULT VALUES", ())

    def test_update(self):
        assert BaseSqlBuilder().update("t").set_(a=1).where("id = 1").build() == (
            "UPDATE t SET a = %s WHERE id = 1", (1,))

    def test_delete(self):
        assert BaseSqlBuilder().delete_from("t").where("id = 1").build() == (
            "DELETE FROM t WHERE id = 1", ())

    def test_multi_table(self):
        assert BaseSqlBuilder().select("*").from_("t", "u").build() == (
            "SELECT * FROM t, u", ())


class TestRegressionWithBug395Guards:
    """BUG-395 的守卫保持：空条件/非法 join_type/负 limit 仍被拒。"""

    @pytest.mark.parametrize("method", ["where", "and_", "or_", "having"])
    def test_empty_condition(self, method):
        b = BaseSqlBuilder().select("*").from_("t")
        with pytest.raises(ValueError):
            getattr(b, method)("")

    def test_bad_join_type(self):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").from_("t").join("u", "t.id=u.id", "BOGUS")

    def test_negative_limit(self):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").from_("t").limit(-1)

    def test_update_without_set(self):
        with pytest.raises(ValueError):
            BaseSqlBuilder().update("t").set_().where("id=1").build()


class TestOrderByGroupByValidation:
    """BUG-460：order_by/group_by 空值与非字符串同样会产出非法 SQL。"""

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_order_by_empty(self, bad):
        with pytest.raises(ValueError) as ei:
            BaseSqlBuilder().select("*").from_("t").order_by(bad)
        assert "order_by" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "  "])
    def test_group_by_empty(self, bad):
        with pytest.raises(ValueError) as ei:
            BaseSqlBuilder().select("a").from_("t").group_by(bad)
        assert "group_by" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None, ["a"]])
    def test_non_str_rejected(self, bad):
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").from_("t").order_by(bad)
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("a").from_("t").group_by(bad)

    def test_empty_in_list_rejected(self):
        """多列时第二列为空同样拒绝（原来生成 'ORDER BY a, '）。"""
        with pytest.raises(ValueError):
            BaseSqlBuilder().select("*").from_("t").order_by("a", "")

    def test_valid_order_group(self):
        assert BaseSqlBuilder().select("*").from_("t").order_by("a", "b").build() == (
            "SELECT * FROM t ORDER BY a, b", ())
        assert BaseSqlBuilder().select("*").from_("t").order_by("a DESC").build() == (
            "SELECT * FROM t ORDER BY a DESC", ())
        assert BaseSqlBuilder().select("a").from_("t").group_by("a").build() == (
            "SELECT a FROM t GROUP BY a", ())

