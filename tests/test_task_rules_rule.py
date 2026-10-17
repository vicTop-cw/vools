# -*- coding: utf-8 -*-
"""测试 vools.task.rules.rule — Rule 与 RuleSet。"""

from vools.functional import Result

__all__ = ["TestRule", "TestRuleSet"]


def _true_cond(ctx):
    return Result.success(True)


def _false_cond(ctx):
    return Result.success(False)


def _fail_cond(ctx):
    return Result.failure(ValueError("cond failed"))


def _act(ctx):
    return Result.success(f"acted:{ctx.get('x', 0)}")


class TestRule:
    """Rule 核心行为测试。"""

    def test_init_frozen(self):
        from vools.task.rules.rule import Rule
        r = Rule(name="r1", condition=_true_cond, action=_act, priority=5, metadata={"k": "v"})
        assert r.name == "r1"
        assert r.priority == 5
        assert r.metadata == {"k": "v"}
        assert r.condition is _true_cond
        assert r.action is _act

    def test_evaluate_cond_true(self):
        from vools.task.rules.rule import Rule
        r = Rule(name="r", condition=_true_cond, action=_act)
        result = r.evaluate({"x": 10})
        assert result.is_success
        assert result.unwrap() == "acted:10"

    def test_evaluate_cond_false(self):
        from vools.task.rules.rule import Rule
        r = Rule(name="r", condition=_false_cond, action=_act)
        result = r.evaluate({})
        assert result.is_success
        assert result.unwrap() is None

    def test_evaluate_cond_failure(self):
        from vools.task.rules.rule import Rule
        r = Rule(name="r", condition=_fail_cond, action=_act)
        result = r.evaluate({})
        assert result.is_failure
        # Result.failure 的 unwrap() 抛出的异常保留原始 message
        import pytest
        with pytest.raises(ValueError, match="cond failed"):
            result.unwrap()

    def test_do_chain(self):
        from vools.task.rules.rule import Rule
        r = Rule(name="r", condition=_true_cond, action=_act)
        seen = []
        r2 = r.do(pre_f=lambda x: (seen.append("pre"), x)[1],
                  f=lambda x: (seen.append("f"), x)[1],
                  sub_f=lambda x: seen.append("sub"))
        assert r2 is r
        assert seen == ["pre", "f", "sub"]

    def test_metadata_default_factory(self):
        from vools.task.rules.rule import Rule
        r = Rule(name="r", condition=_true_cond, action=_act)
        assert r.metadata == {}


class TestRuleSet:
    """RuleSet 核心行为测试。"""

    def _rs(self):
        from vools.task.rules.rule import RuleSet, Rule
        return RuleSet([
            Rule(name="low", condition=_true_cond, action=lambda ctx: Result.success("low"), priority=1),
            Rule(name="high", condition=_true_cond, action=lambda ctx: Result.success("high"), priority=5),
        ])

    def test_init_empty(self):
        from vools.task.rules.rule import RuleSet
        rs = RuleSet()
        assert len(rs) == 0
        assert rs.rules == []

    def test_len(self):
        assert len(self._rs()) == 2

    def test_rules_property(self):
        rs = self._rs()
        rules = rs.rules
        assert len(rules) == 2
        # 返回副本
        rules.append("x")
        assert len(rs.rules) == 2

    def test_add(self):
        from vools.task.rules.rule import Rule, RuleSet
        rs = RuleSet([Rule(name="a", condition=_true_cond, action=_act)])
        rs2 = rs.add(Rule(name="b", condition=_true_cond, action=_act))
        assert len(rs) == 1
        assert len(rs2) == 2

    def test_or_combo(self):
        from vools.task.rules.rule import Rule, RuleSet
        # 第一个 true → 返回其 action
        rs1 = RuleSet([Rule(name="a", condition=_true_cond, action=lambda ctx: Result.success("a"))])
        rs2 = RuleSet([Rule(name="b", condition=_true_cond, action=lambda ctx: Result.success("b"))])
        combo = rs1 | rs2
        assert len(combo) == 1
        result = combo.evaluate({})
        assert result.is_success
        # evaluate 会按 priority 排序，单条组合 rule 直接评估
        assert len(result.unwrap()) == 1

    def test_or_empty_left(self):
        from vools.task.rules.rule import Rule, RuleSet
        rs1 = RuleSet()
        rs2 = RuleSet([Rule(name="b", condition=_true_cond, action=lambda ctx: Result.success("b"))])
        combo = rs1 | rs2
        assert len(combo) == 1

    def test_add_order(self):
        rs1 = self._rs()
        from vools.task.rules.rule import Rule, RuleSet
        rs2 = RuleSet([Rule(name="mid", condition=_true_cond, action=_act, priority=3)])
        merged = rs1 + rs2
        # 按 priority 降序：high(5) > mid(3) > low(1)
        names = [r.name for r in merged.rules]
        assert names == ["high", "mid", "low"]

    def test_and_combo(self):
        from vools.task.rules.rule import Rule, RuleSet
        rs1 = RuleSet([Rule(name="a", condition=_true_cond, action=lambda ctx: Result.success("a"))])
        rs2 = RuleSet([Rule(name="b", condition=_true_cond, action=lambda ctx: Result.success("b"))])
        combo = rs1 & rs2
        assert len(combo) == 1
        # 内部 action 返回 Result.success(results)
        result = combo.rules[0].action({})
        assert result.is_success
        assert len(result.unwrap()) == 2

    def test_and_cond_false(self):
        from vools.task.rules.rule import Rule, RuleSet
        rs1 = RuleSet([Rule(name="a", condition=_false_cond, action=_act)])
        rs2 = RuleSet([Rule(name="b", condition=_true_cond, action=_act)])
        combo = rs1 & rs2
        result = combo.rules[0].condition({})
        assert result.is_success
        assert result.unwrap() is False

    def test_evaluate_priority_order(self):
        rs = self._rs()
        result = rs.evaluate({})
        assert result.is_success
        pairs = result.unwrap()
        # 按 priority 降序
        assert pairs[0][0] == "high"
        assert pairs[1][0] == "low"

    def test_evaluate_failure_stops(self):
        from vools.task.rules.rule import Rule, RuleSet
        rs = RuleSet([
            Rule(name="ok", condition=_true_cond, action=lambda ctx: Result.success(1), priority=5),
            Rule(name="bad", condition=_true_cond, action=lambda ctx: Result.failure(ValueError("boom")), priority=3),
            Rule(name="after", condition=_true_cond, action=lambda ctx: Result.success(3), priority=1),
        ])
        result = rs.evaluate({})
        assert result.is_failure
        import pytest
        with pytest.raises(Exception, match="boom"):
            result.unwrap()

    def test_repr(self):
        rs = self._rs()
        assert "RuleSet(2 rules)" in repr(rs)

    def test_do_chain(self):
        rs = self._rs()
        seen = []
        r2 = rs.do(pre_f=lambda x: (seen.append("pre"), x)[1],
                   f=lambda x: (seen.append("f"), x)[1],
                   sub_f=lambda x: seen.append("sub"))
        assert r2 is rs
        assert seen == ["pre", "f", "sub"]

    def test_import_all(self):
        from vools.task.rules.rule import __all__
        assert "Rule" in __all__
        assert "RuleSet" in __all__
