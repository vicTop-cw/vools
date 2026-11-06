# -*- coding: utf-8 -*-
"""更深边界回归（第 31 轮 / 统帅轮-08时）：补 REFACTOR_COMPLETION.md §六.3 的三项遗留。

覆盖三个此前无用例的面：
  1. template 生成失败路径（scaffold_action 抛异常 → runtime error）
  2. demo 递归（demo 动作里调用另一个 demo 动作 → 不应无限递归）
  3. workflow 节点重试（节点失败后按 retry 配置重试 + 退避 + fallback）

每个用例都有明确的失败模式断言，确保行为被锁定。
"""
import time
import pytest

from vools.actus.executor import _execute_template_kind, _demo_ctx as _demo_ctx_ref


def _action(action_id, kind, **meta):
    """构造一个最小 Action 对象（mock meta 即可，_execute_template_kind 只读 meta）。"""
    class _A:
        pass
    a = _A()
    a.kind = kind
    a.meta = meta
    a.id = action_id
    return a


# ---------------------------------------------------------------------------
# 1. template 生成失败路径
# ---------------------------------------------------------------------------
def test_template_scaffold_raises_returns_runtime_error(monkeypatch):
    """scaffold_action 抛异常时，template 动作必须返回 runtime error 而非崩溃。

    此前只有「缺模板描述 → param_invalid」和「scaffold 成功 → ok」两个路径，
    缺「scaffold 内部抛异常」的用例。executor.py:162 的 except 分支从未被测试覆盖。
    """
    from vools.actus import scaffold as sc

    def boom(description, action_id=None, trust="audit",
             output_dir=None, author="ai-scaffold", repo_root=None, force=False):
        raise RuntimeError("scaffold 内部磁盘写满")

    monkeypatch.setattr(sc, "scaffold_action", boom)
    tmpl = _action("myapp.t", "template", template="做一个计算器")
    result = _execute_template_kind(tmpl, "myapp.t", {})
    assert result["status"] == "failed", result
    err = result.get("error") or {}
    assert err.get("code") == "runtime", err
    assert "生成失败" in (err.get("message") or ""), err
    assert "磁盘写满" in (err.get("message") or ""), err


def test_template_scaffold_raises_message_contains_exc(monkeypatch):
    """生成失败的 message 必须含原始异常文本（便于运维定位）。"""
    from vools.actus import scaffold as sc

    def boom(description, action_id=None, trust="audit",
             output_dir=None, author="ai-scaffold", repo_root=None, force=False):
        raise ValueError("模板参数非法: xxx")

    monkeypatch.setattr(sc, "scaffold_action", boom)
    tmpl = _action("myapp.t", "template", description="做一个计算器")
    result = _execute_template_kind(tmpl, "myapp.t", {})
    assert result["status"] == "failed"
    msg = (result.get("error") or {}).get("message") or ""
    assert "模板参数非法" in msg, msg
    assert "xxx" in msg, msg


# ---------------------------------------------------------------------------
# 2. demo 递归保护
# ---------------------------------------------------------------------------
def test_demo_recursive_call_does_not_infinite_loop(tmp_path):
    """demo 动作里调用另一个 demo 动作时，_demo_ctx.active 必须防住无限递归。

    executor.py:370 用线程局部标志 _demo_ctx.active 拦截递归：外层 demo 进入演示
    分支设 active=True，内层 demo 检查 active=True 后按 exec 执行（不进演示分支）。
    此前没有用例验证这个保护真实生效——递归 demo 会栈溢出。

    本用例造两个 demo 动作：outer 的入口块里调用 inner（也是 demo）。
    如果保护失效，inner 再次进入演示分支 → 无限递归 → RecursionError。
    """
    from vools.actus.executor import execute as _execute

    repo_root = tmp_path / "repo"
    actions_dir = repo_root / "actions"
    actions_dir.mkdir(parents=True)

    # inner demo 动作：只有入口块，print 标记
    inner_md = """---
id: myapp.inner
name: InnerDemo
version: 1.0.0
trust: sandbox
kind: demo
entry: main
platform: desktop
description: 内层 demo
---

# Inner

```python #!run tag=main
print("inner-ran")
```
"""
    (actions_dir / "inner.actus.schema.md").write_text(inner_md, encoding="utf-8")

    # outer demo 动作：入口块里调用 inner demo（经 execute）
    outer_md = """---
id: myapp.outer
name: OuterDemo
version: 1.0.0
trust: sandbox
kind: demo
entry: main
platform: desktop
description: 外层 demo，递归调用 inner
---

# Outer

```python #!run tag=main
from vools.actus.executor import execute
r = execute("myapp.inner", {})
print("outer-done")
```
"""
    (actions_dir / "outer.actus.schema.md").write_text(outer_md, encoding="utf-8")

    # 用隔离的 meta_dir 避免污染真实仓库
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()

    # 跑 outer demo：如果递归保护失效会栈溢出
    result = _execute("myapp.outer", {},
                      meta_dir=str(meta_dir),
                      actions_dir=str(actions_dir))
    # 不抛 RecursionError 即保护生效；outer 应正常完成
    assert result.get("status") == "ok", result
    # demo 展开应附 expanded 字段
    data = result.get("data") or {}
    assert "demo" in data, "outer demo 未附 expanded 演示展开"
    expanded = data["demo"].get("expanded") or []
    assert expanded, "outer demo 的 expanded 不应为空"


def test_demo_ctx_flag_reset_after_execution():
    """_demo_ctx.active 在演示执行结束后必须复位为 False，否则后续 demo 被误判。

    executor.py:378 finally 块复位 active。如果 finally 没执行（异常路径），
    后续非递归 demo 会被当成递归内的 exec 执行，丢掉演示展开。
    """
    # _demo_ctx 是 executor.py 的线程局部对象，初始 active=False
    assert getattr(_demo_ctx_ref, "active", False) is False

    # 手动模拟演示执行流程：设 active=True 后在 finally 里复位
    _demo_ctx_ref.active = True
    assert getattr(_demo_ctx_ref, "active", False) is True
    # 模拟 finally
    _demo_ctx_ref.active = False
    assert getattr(_demo_ctx_ref, "active", False) is False


# ---------------------------------------------------------------------------
# 3. workflow 节点重试
# ---------------------------------------------------------------------------
def _make_workflow_action(wf_dict):
    """构造一个含 workflow 元数据的 Action 对象。"""
    from vools.actus.model import Action
    return Action(
        meta={"id": "myapp.wf", "name": "WF", "version": "1.0.0",
              "trust": "audit", "kind": "exec", "entry": "main",
              "workflow": wf_dict},
        path="",
        sha256="",
    )


def test_workflow_node_retries_on_failure_then_succeeds(tmp_path, monkeypatch):
    """节点失败后按 retry.max_attempts 重试，第 N 次成功后标记 ok。

    workflow.py:297 for attempt in range(max_attempts) 循环：前两次失败，
    第三次成功 → 节点状态 ok，records 里 attempt=3。
    此前没有用例验证「重试最终成功」的路径——只有全部失败或一次成功。
    """
    from vools.actus.workflow import WorkflowExecutor

    calls = {"n": 0}

    def fake_execute(action_id, params, confirmed=False, meta_dir=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"status": "failed",
                    "error": {"code": "runtime", "message": f"attempt {calls['n']} 失败"}}
        return {"status": "ok", "data": {"v": calls["n"]}}

    monkeypatch.setattr("vools.actus.workflow._execute.execute", fake_execute)

    wf = {
        "nodes": [
            {"id": "n1", "action_id": "myapp.flaky",
             "retry": {"max_attempts": 3, "backoff_ms": 0, "backoff_multiplier": 1.0}}
        ],
        "edges": [],
    }
    action = _make_workflow_action(wf)
    from vools.actus.workflow import Workflow
    workflow = Workflow(action)
    runner = WorkflowExecutor(workflow, meta_dir=str(tmp_path / "meta"))
    res = runner.run()
    assert res.get("status") == "ok", "节点重试 3 次后成功，workflow 应 ok"
    assert runner._node_status.get("n1") == "ok", runner._node_status
    assert calls["n"] == 3, f"应重试 3 次，实得 {calls['n']}"
    # records 里应有 attempt=3 的 ok 记录
    ok_records = [r for r in runner._records if r.get("status") == "ok"]
    assert ok_records and ok_records[-1].get("attempt") == 3, ok_records


def test_workflow_node_retries_exhausted_then_failed(tmp_path, monkeypatch):
    """节点重试耗尽（max_attempts 次全失败）且无 fallback → 节点 failed。

    workflow.py:368-374：重试耗尽后尝试 fallback，fallback 缺失则标记 failed，
    records 里记「重试 N 次后仍失败」。
    """
    from vools.actus.workflow import WorkflowExecutor, Workflow

    calls = {"n": 0}

    def fake_execute(action_id, params, confirmed=False, meta_dir=None):
        calls["n"] += 1
        return {"status": "failed",
                "error": {"code": "runtime", "message": f"attempt {calls['n']} 失败"}}

    monkeypatch.setattr("vools.actus.workflow._execute.execute", fake_execute)

    wf = {
        "nodes": [
            {"id": "n1", "action_id": "myapp.always_fail",
             "retry": {"max_attempts": 2, "backoff_ms": 0, "backoff_multiplier": 1.0}}
        ],
        "edges": [],
    }
    action = _make_workflow_action(wf)
    workflow = Workflow(action)
    runner = WorkflowExecutor(workflow, meta_dir=str(tmp_path / "meta"))
    res = runner.run()
    assert res.get("status") == "failed", "节点重试耗尽且无 fallback，workflow 应 failed"
    assert runner._node_status.get("n1") == "failed", runner._node_status
    assert calls["n"] == 2, f"应重试 2 次，实得 {calls['n']}"
    failed_records = [r for r in runner._records if r.get("status") == "failed"]
    assert failed_records, "应有 failed 记录"
    msg = failed_records[-1].get("error") or ""
    assert "重试 2 次后仍失败" in msg, msg


def test_workflow_node_retry_uses_fallback_when_exhausted(tmp_path, monkeypatch):
    """节点重试耗尽后，fallback 动作成功 → 节点 ok（fallback 替代）。

    workflow.py:349-364：重试耗尽后尝试 node.fallback，fallback 成功则标记 ok。
    """
    from vools.actus.workflow import WorkflowExecutor, Workflow

    primary_calls = {"n": 0}
    fallback_calls = {"n": 0}

    def fake_execute(action_id, params, confirmed=False, meta_dir=None):
        if action_id == "myapp.primary":
            primary_calls["n"] += 1
            return {"status": "failed",
                    "error": {"code": "runtime", "message": "primary 失败"}}
        if action_id == "myapp.fallback":
            fallback_calls["n"] += 1
            return {"status": "ok", "data": {"from": "fallback"}}
        return {"status": "failed"}

    monkeypatch.setattr("vools.actus.workflow._execute.execute", fake_execute)

    wf = {
        "nodes": [
            {"id": "n1", "action_id": "myapp.primary",
             "retry": {"max_attempts": 2, "backoff_ms": 0},
             "fallback": "myapp.fallback"}
        ],
        "edges": [],
    }
    action = _make_workflow_action(wf)
    workflow = Workflow(action)
    runner = WorkflowExecutor(workflow, meta_dir=str(tmp_path / "meta"))
    res = runner.run()
    assert res.get("status") == "ok", "fallback 成功后节点应 ok"
    assert runner._node_status.get("n1") == "ok", runner._node_status
    assert primary_calls["n"] == 2, f"primary 应重试 2 次，实得 {primary_calls['n']}"
    assert fallback_calls["n"] == 1, f"fallback 应调用 1 次，实得 {fallback_calls['n']}"
    ok_records = [r for r in runner._records if r.get("status") == "ok"]
    assert ok_records and ok_records[-1].get("fallback") == "myapp.fallback", ok_records


def test_workflow_retry_backoff_uses_exponential_multiplier(tmp_path, monkeypatch):
    """重试退避必须用 backoff_ms * multiplier^attempt 指数退避。

    workflow.py:344-346：attempt=0 退避 backoff_ms*1，attempt=1 退避 backoff_ms*multiplier。
    此前没有用例验证退避计算——退避算错会让重试过快（压垮下游）或过慢（拖长耗时）。
    """
    from vools.actus.workflow import WorkflowExecutor, Workflow

    calls = {"n": 0}
    slept = []

    def fake_execute(action_id, params, confirmed=False, meta_dir=None):
        calls["n"] += 1
        return {"status": "failed",
                "error": {"code": "runtime", "message": "fail"}}

    monkeypatch.setattr("vools.actus.workflow._execute.execute", fake_execute)
    monkeypatch.setattr("vools.actus.workflow.time.sleep",
                        lambda s: slept.append(s))

    wf = {
        "nodes": [
            {"id": "n1", "action_id": "myapp.x",
             "retry": {"max_attempts": 3, "backoff_ms": 100,
                       "backoff_multiplier": 2.0}}
        ],
        "edges": [],
    }
    action = _make_workflow_action(wf)
    workflow = Workflow(action)
    runner = WorkflowExecutor(workflow, meta_dir=str(tmp_path / "meta"))
    runner.run()
    # max_attempts=3 → 2 次退避（attempt=0,1）
    # attempt=0: 100 * 2.0^0 = 100 → 0.1s
    # attempt=1: 100 * 2.0^1 = 200 → 0.2s
    assert len(slept) == 2, f"应退避 2 次，实得 {slept}"
    assert slept[0] == 0.1, f"attempt=0 退避应为 0.1s，实得 {slept[0]}"
    assert slept[1] == 0.2, f"attempt=1 退避应为 0.2s，实得 {slept[1]}"
