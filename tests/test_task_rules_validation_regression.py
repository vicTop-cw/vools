# -*- coding: utf-8 -*-
"""回归测试：rules 族构造参数校验（BUG-434）。

修复前：

    DagScheduler(queue=None)          # 到 start() 才抛 AttributeError 'storage'
    DagScheduler(mode='bogus')        # 静默接受
    DagScheduler(max_workers=0)       # 静默接受（不启动任何 worker）
    RuleEngine(mode='bogus') / (max_workers=0)   # 同上
    Rule(name='', ...)                # 静默接受
    Rule(name='x', condition=cond, action=123)  # 直到 evaluate 才抛 TypeError
    RuleSet(rules='x')                # **得到 1 条规则**（字符串被逐字符展开）
    RuleSet([123])                    # 得到 1 条非 Rule 对象

修复后入口即抛带字段名的 TypeError/ValueError；合法构造不变。
"""

import pytest

from vools.task.core.queue import TaskQueue
from vools.task.rules.dag import DagScheduler
from vools.task.rules.engine import RuleEngine
from vools.task.rules.rule import Rule, RuleSet


def _cond(ctx):
    return True


def _act(ctx):
    return ctx


@pytest.fixture()
def queue(tmp_path):
    q = TaskQueue(db_path=str(tmp_path / "q.db"))
    yield q
    try:
        q.storage.close()
    except Exception:
        pass


class TestDagSchedulerValidation:
    @pytest.mark.parametrize("bad", [None, 123, "x", object()])
    def test_bad_queue(self, bad):
        with pytest.raises(TypeError) as ei:
            DagScheduler(queue=bad)
        assert "queue" in str(ei.value)

    def test_bad_mode(self, queue):
        with pytest.raises(ValueError) as ei:
            DagScheduler(queue, mode="bogus")
        assert "mode" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1, "x", True])
    def test_bad_max_workers(self, queue, bad):
        with pytest.raises((TypeError, ValueError)) as ei:
            DagScheduler(queue, max_workers=bad)
        assert "max_workers" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -0.1, "x", True])
    def test_bad_poll_interval(self, queue, bad):
        with pytest.raises((TypeError, ValueError)) as ei:
            DagScheduler(queue, poll_interval=bad)
        assert "poll_interval" in str(ei.value)

    def test_bad_propagate_failure(self, queue):
        with pytest.raises(TypeError) as ei:
            DagScheduler(queue, propagate_failure="x")
        assert "propagate_failure" in str(ei.value)

    def test_valid(self, queue):
        s = DagScheduler(queue, mode="process", max_workers=2, poll_interval=0.2)
        assert s._mode == "process"
        assert s._max_workers == 2


class TestRuleEngineValidation:
    def test_bad_mode(self):
        with pytest.raises(ValueError):
            RuleEngine(mode="bogus")

    @pytest.mark.parametrize("bad", [0, -1, "x"])
    def test_bad_max_workers(self, bad):
        with pytest.raises((TypeError, ValueError)) as ei:
            RuleEngine(max_workers=bad)
        assert "max_workers" in str(ei.value)

    def test_valid(self):
        assert RuleEngine(mode="thread", max_workers=2)._max_workers == 2


class TestRuleValidation:
    @pytest.mark.parametrize("bad", ["", "   ", 123, None])
    def test_bad_name(self, bad):
        with pytest.raises(ValueError) as ei:
            Rule(name=bad, condition=_cond, action=_act)
        assert "name" in str(ei.value)

    @pytest.mark.parametrize("kw", ["condition", "action"])
    def test_bad_callables(self, kw):
        kwargs = {kw: 123}
        with pytest.raises(TypeError) as ei:
            Rule(name="x", condition=_cond, action=_act, **kwargs)
        assert kw in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_bad_priority(self, bad):
        with pytest.raises(TypeError) as ei:
            Rule(name="x", condition=_cond, action=_act, priority=bad)
        assert "priority" in str(ei.value)

    def test_negative_priority(self):
        with pytest.raises(ValueError):
            Rule(name="x", condition=_cond, action=_act, priority=-1)

    def test_bad_metadata(self):
        with pytest.raises(TypeError) as ei:
            Rule(name="x", condition=_cond, action=_act, metadata="x")
        assert "metadata" in str(ei.value)

    def test_valid(self):
        r = Rule(name="r", condition=_cond, action=_act, priority=2,
                 metadata={"k": 1})
        assert (r.name, r.priority, r.metadata) == ("r", 2, {"k": 1})


class TestRuleSetValidation:
    @pytest.mark.parametrize("bad", ["x", 123, object()])
    def test_bad_rules_container(self, bad):
        with pytest.raises(TypeError) as ei:
            RuleSet(rules=bad)
        assert "rules" in str(ei.value)

    def test_bad_element(self):
        with pytest.raises(TypeError) as ei:
            RuleSet(rules=[123])
        assert "Rule" in str(ei.value)

    def test_none_and_valid(self):
        assert RuleSet().rules == []
        rs = RuleSet(rules=[Rule("a", _cond, _act)])
        assert len(rs.rules) == 1
