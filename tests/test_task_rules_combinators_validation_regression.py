# -*- coding: utf-8 -*-
"""回归测试：RuleEngine.add_rule(s) 与 RuleSet 组合运算符（BUG-435）+ 组合语义。

修复前：

    engine.add_rule(123)              # 非 Rule 被塞进列表，evaluate 时才炸
    engine.add_rules(rule, 123)        # 同上（批量静默混入）
    rs | 123   / rs + 'x'   / rs & None
        # AttributeError: 'int' object has no attribute '_rules'（完全看不出
        # 是"组合运算需要 RuleSet"）

修复后入口即抛带字段名的 TypeError。

语义锁定（与 ``Rule.evaluate`` 契约一致：**condition 为假 = 跳过（success(None)），
不是错误**）：

* ``|`` OR：执行首个条件为真的规则动作；全部为假时不执行任何动作；
* ``&`` AND：所有条件为真才执行全部动作，否则不执行；
* ``+`` 顺序组合：按 priority 降序合并；
* ``evaluate`` 在"条件不满足"时返回 success（无异常），不报失败。
"""

import pytest

from vools.functional.result import Result
from vools.task.rules.engine import RuleEngine
from vools.task.rules.rule import Rule, RuleSet


def _cond(value):
    def _c(ctx):
        return Result.success(value)
    return _c


def _act(label, calls):
    def _a(ctx):
        calls.append(label)
        return Result.success(ctx)
    return _a


def _rule(name, cond_value, calls, label=None):
    return Rule(name, _cond(cond_value), _act(label or name, calls))


class TestAddRuleValidation:
    @pytest.mark.parametrize("bad", [123, "x", None, object()])
    def test_add_rule(self, bad):
        with pytest.raises(TypeError) as ei:
            RuleEngine().add_rule(bad)
        assert "Rule" in str(ei.value)

    def test_add_rules_mixed(self):
        with pytest.raises(TypeError) as ei:
            RuleEngine().add_rules(Rule("a", _cond(True), lambda c: Result.success(c)), 123)
        assert "Rule" in str(ei.value)

    def test_add_rules_valid(self):
        engine = RuleEngine()
        engine.add_rules(Rule("a", _cond(True), lambda c: Result.success(c)),
                         Rule("b", _cond(True), lambda c: Result.success(c)))
        assert len(engine.rules) == 2


class TestRuleSetCombinatorsValidation:
    @pytest.fixture()
    def rs(self):
        return RuleSet(rules=[Rule("a", _cond(True), lambda c: Result.success(c))])

    @pytest.mark.parametrize("bad", [123, "x", None, object()])
    def test_bad_other(self, rs, bad):
        for expr in (lambda: rs | bad, lambda: rs + bad, lambda: rs & bad):
            with pytest.raises(TypeError) as ei:
                expr()
            assert "RuleSet" in str(ei.value)


class TestCombinatorSemantics:
    def test_or_runs_first_matching_action(self):
        calls = []
        rs1 = RuleSet(rules=[_rule("a", False, calls)])
        rs2 = RuleSet(rules=[_rule("b", True, calls)])
        result = (rs1 | rs2).evaluate({})
        assert result.is_success is True
        assert calls == ["b"]

    def test_or_no_action_when_all_false(self):
        calls = []
        rs1 = RuleSet(rules=[_rule("a", False, calls)])
        rs2 = RuleSet(rules=[_rule("b", False, calls)])
        result = (rs1 | rs2).evaluate({})
        assert result.is_success is True     # 条件不满足不是错误
        assert calls == []

    def test_and_runs_all_when_all_true(self):
        calls = []
        rs1 = RuleSet(rules=[_rule("a", True, calls)])
        rs2 = RuleSet(rules=[_rule("b", True, calls)])
        (rs1 & rs2).evaluate({})
        assert calls == ["a", "b"]

    def test_and_skips_all_when_any_false(self):
        calls = []
        rs1 = RuleSet(rules=[_rule("a", True, calls)])
        rs2 = RuleSet(rules=[_rule("b", False, calls)])
        result = (rs1 & rs2).evaluate({})
        assert result.is_success is True     # 条件不满足 => 跳过，不报错
        assert calls == []

    def test_add_sorted_by_priority_desc(self):
        low = RuleSet(rules=[Rule("low", _cond(True),
                                  lambda c: Result.success(1), priority=1)])
        high = RuleSet(rules=[Rule("high", _cond(True),
                                   lambda c: Result.success(2), priority=10)])
        assert [r.name for r in (low + high).rules] == ["high", "low"]
