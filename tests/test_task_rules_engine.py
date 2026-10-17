# -*- coding: utf-8 -*-
"""测试 vools.task.rules.engine — RuleEngine / rule 装饰器 / from_json。"""

import json

import pytest

from vools.functional import Result

__all__ = ["TestRuleStatus", "TestRuleDecorator", "TestRuleEngine",
           "TestRuleEngineAsync", "TestRuleEngineJson", "TestDeserialize"]


def _ok_cond(ctx):
    return Result.success(True)


def _fail_cond(ctx):
    return Result.failure(ValueError("cond failed"))


def _act(ctx):
    return Result.success(f"action:{ctx.get('x')}")


def _boom(ctx):
    return Result.failure(ValueError("boom"))


def _true_cond(ctx):
    return Result.success(True)


class TestRuleStatus:
    """RuleStatus 枚举测试。"""

    def test_values(self):
        from vools.task.rules.engine import RuleStatus
        assert RuleStatus.PENDING.value == "PENDING"
        assert RuleStatus.PASSED.value == "PASSED"
        assert RuleStatus.FAILED.value == "FAILED"
        assert RuleStatus.SKIPPED.value == "SKIPPED"


class TestRuleDecorator:
    """rule 装饰器测试。"""

    def test_bare_decorator(self):
        from vools.task.rules.engine import rule

        @rule
        def my_rule(ctx):
            return True

        assert my_rule.name == "my_rule"
        assert my_rule.priority == 0
        assert my_rule.metadata == {}

    def test_with_params(self):
        from vools.task.rules.engine import rule

        @rule(name="check", priority=5, metadata={"k": "v"})
        def my_rule(ctx):
            return "ok"

        assert my_rule.name == "check"
        assert my_rule.priority == 5
        assert my_rule.metadata == {"k": "v"}

    def test_with_condition(self):
        from vools.task.rules.engine import rule

        @rule(condition=_ok_cond)
        def my_action(ctx):
            return "done"

        assert my_action.name == "my_action"
        r = my_action.evaluate({})
        assert r.is_success
        assert r.unwrap() == "done"

    def test_auto_condition_true(self):
        from vools.task.rules.engine import rule

        @rule
        def truthy(ctx):
            return 42

        r = truthy.condition({})
        assert r.is_success
        assert r.unwrap() is True

    def test_auto_condition_false(self):
        from vools.task.rules.engine import rule

        @rule
        def falsy(ctx):
            return 0

        r = falsy.condition({})
        assert r.is_success
        assert r.unwrap() is False

    def test_auto_condition_result(self):
        from vools.task.rules.engine import rule

        @rule
        def returns_result(ctx):
            return Result.success(True)

        r = returns_result.condition({})
        assert r.is_success
        assert r.unwrap() is True

    def test_auto_condition_exception(self):
        from vools.task.rules.engine import rule

        @rule
        def raises(ctx):
            raise ValueError("boom")

        r = raises.condition({})
        assert r.is_failure

    def test_auto_action_exception(self):
        from vools.task.rules.engine import rule

        @rule
        def raises(ctx):
            raise ValueError("boom")

        r = raises.action({})
        assert r.is_failure


def _mk_engine(**kw):
    from vools.task.rules.engine import RuleEngine
    from vools.task.rules.rule import Rule
    kw.setdefault("max_workers", 2)
    e = RuleEngine(**kw)
    e.add_rule(Rule(name="r1", condition=_ok_cond, action=_act, priority=1))
    e.add_rule(Rule(name="r2", condition=_ok_cond, action=_act, priority=5))
    return e


class TestRuleEngine:
    """RuleEngine 核心行为测试。"""

    def test_init(self):
        from vools.task.rules.engine import RuleEngine
        e = RuleEngine(mode="thread", max_workers=3)
        assert e._mode == "thread"
        assert e._max_workers == 3
        assert e.rules == []

    def test_rules_property(self):
        e = _mk_engine()
        rules = e.rules
        assert len(rules) == 2
        rules.append("x")
        assert len(e.rules) == 2

    def test_add_rule(self):
        from vools.task.rules.engine import RuleEngine
        from vools.task.rules.rule import Rule
        e = RuleEngine()
        r = Rule(name="x", condition=_ok_cond, action=_act)
        e.add_rule(r)
        assert len(e.rules) == 1
        assert e.rules[0].name == "x"

    def test_add_rules(self):
        from vools.task.rules.engine import RuleEngine
        from vools.task.rules.rule import Rule
        e = RuleEngine()
        e.add_rules(
            Rule(name="a", condition=_ok_cond, action=_act),
            Rule(name="b", condition=_ok_cond, action=_act),
        )
        assert len(e.rules) == 2

    def test_remove_rule(self):
        e = _mk_engine()
        assert e.remove_rule("r1") is True
        assert len(e.rules) == 1
        assert e.remove_rule("nope") is False

    def test_get_rule(self):
        e = _mk_engine()
        r = e.get_rule("r2")
        assert r is not None
        assert r.name == "r2"
        assert e.get_rule("nope") is None

    def test_evaluate_success(self):
        e = _mk_engine()
        r = e.evaluate({"x": 7})
        assert r.is_success
        pairs = r.unwrap()
        assert pairs[0][0] == "r2"
        assert pairs[1][0] == "r1"

    def test_evaluate_failure_preserves_message(self):
        from vools.task.rules.engine import RuleEngine
        from vools.task.rules.rule import Rule
        e = RuleEngine(max_workers=1)
        e.add_rule(Rule(name="bad", condition=_ok_cond, action=_boom))
        r = e.evaluate({})
        assert r.is_failure
        with pytest.raises(Exception, match="boom"):
            r.unwrap()

    def test_evaluate_cond_failure(self):
        from vools.task.rules.engine import RuleEngine
        from vools.task.rules.rule import Rule
        e = RuleEngine(max_workers=1)
        e.add_rule(Rule(name="bad", condition=_fail_cond, action=_act))
        r = e.evaluate({})
        assert r.is_failure
        with pytest.raises(Exception, match="cond failed"):
            r.unwrap()

    def test_evaluate_empty(self):
        from vools.task.rules.engine import RuleEngine
        e = RuleEngine(max_workers=1)
        r = e.evaluate({})
        assert r.is_success
        assert r.unwrap() == []

    def test_do_chain(self):
        e = _mk_engine()
        seen = []
        r2 = e.do(pre_f=lambda x: (seen.append("pre"), x)[1],
                  f=lambda x: (seen.append("f"), x)[1],
                  sub_f=lambda x: seen.append("sub"))
        assert r2 is e
        assert seen == ["pre", "f", "sub"]

    def test_import_all(self):
        from vools.task.rules.engine import __all__
        assert "RuleEngine" in __all__
        assert "rule" in __all__
        assert "RuleStatus" in __all__


class TestRuleEngineAsync:
    """evaluate_async 行为测试。"""

    def test_evaluate_async_success(self):
        e = _mk_engine()
        r = _run_async(e.evaluate_async, {"x": 1})
        assert r.is_success
        pairs = r.unwrap()
        assert pairs[0][0] == "r2"

    def test_evaluate_async_failure(self):
        from vools.task.rules.engine import RuleEngine
        from vools.task.rules.rule import Rule
        e = RuleEngine(max_workers=1)
        e.add_rule(Rule(name="bad", condition=_ok_cond, action=_boom))
        r = _run_async(e.evaluate_async, {})
        assert r.is_failure
        with pytest.raises(Exception, match="boom"):
            r.unwrap()

    def test_evaluate_async_empty(self):
        from vools.task.rules.engine import RuleEngine
        e = RuleEngine(max_workers=1)
        r = _run_async(e.evaluate_async, {})
        assert r.is_success
        assert r.unwrap() == []


def _run_async(coro_func, *args):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_func(*args))
    finally:
        loop.close()


class TestRuleEngineJson:
    """from_json 行为测试。"""

    def test_from_json_basic(self, tmp_path):
        from vools.task.rules.engine import RuleEngine

        json_data = {
            "mode": "thread",
            "max_workers": 2,
            "rules": [
                {
                    "name": "r1",
                    "condition": "tests.test_task_rules_engine:_ok_cond",
                    "action": "tests.test_task_rules_engine:_act",
                    "priority": 3,
                }
            ]
        }
        p = tmp_path / "rules.json"
        p.write_text(json.dumps(json_data), encoding="utf-8")
        eng = RuleEngine.from_json(str(p))
        assert eng._mode == "thread"
        assert eng._max_workers == 2
        assert len(eng.rules) == 1
        assert eng.rules[0].name == "r1"
        assert eng.rules[0].priority == 3

    def test_from_json_no_action(self, tmp_path):
        from vools.task.rules.engine import RuleEngine
        json_data = {
            "rules": [
                {"name": "only_cond", "condition": "tests.test_task_rules_engine:_ok_cond"}
            ]
        }
        p = tmp_path / "rules.json"
        p.write_text(json.dumps(json_data), encoding="utf-8")
        eng = RuleEngine.from_json(str(p))
        assert len(eng.rules) == 1
        # 无 action → action = condition
        assert eng.rules[0].action is eng.rules[0].condition


class TestDeserialize:
    """_deserialize_rule_func 测试。"""

    def test_deserialize_ok(self):
        from vools.task.rules.engine import _deserialize_rule_func
        fn = _deserialize_rule_func("tests.test_task_rules_engine:_ok_cond")
        r = fn({})
        assert r.is_success
        assert r.unwrap() is True

    def test_deserialize_invalid_ref(self):
        from vools.task.rules.engine import _deserialize_rule_func
        with pytest.raises(ValueError, match="Invalid function reference"):
            _deserialize_rule_func("no_colon_here")

    def test_deserialize_wraps_exception(self):
        from vools.task.rules.engine import _deserialize_rule_func

        def _raises(ctx):
            raise ValueError("inner boom")

        # 临时注册到本模块
        import tests.test_task_rules_engine as _mod
        _mod._ok_cond = _raises
        fn = _deserialize_rule_func("tests.test_task_rules_engine:_ok_cond")
        r = fn({})
        assert r.is_failure
        with pytest.raises(ValueError, match="inner boom"):
            r.unwrap()
        # 还原
        _mod._ok_cond = _true_cond
