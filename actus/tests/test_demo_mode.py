# -*- coding: utf-8 -*-
"""阶段3：demo 演示模式的回归。

ACTUS_REFACTOR_PLAN §3.3/§3.4：demo 动作走「演示模式（执行并展开源码）」，
全部代码块默认视为 only-code 展开。
"""
from vools.actus.executor import _attach_demo_expansion
from vools.actus.model import Action


def _demo_action(blocks):
    return Action(meta={"id": "myapp.demo", "name": "demo", "version": "1.0.0",
                        "trust": "sandbox", "kind": "demo", "platform": "desktop"},
                  path="", sha256="", blocks=blocks)


def test_demo_expansion_attaches_every_block():
    action = _demo_action([
        {"language": "python", "tags": ["main"], "source": 'print("entry")'},
        {"language": "python", "tags": [], "source": 'print("helper")'},
    ])
    result = {"status": "ok", "data": {"result": "ran"}}
    out = _attach_demo_expansion(result, action)
    assert out["status"] == "ok"
    demo = out["data"]["demo"]
    assert demo["block_count"] == 2
    assert demo["expanded"][0]["only_code"] is True
    assert demo["expanded"][0]["source"] == 'print("entry")'
    assert demo["expanded"][0]["language"] == "python"
    assert demo["expanded"][1]["tags"] == []


def test_demo_expansion_skips_blocks_without_source():
    action = _demo_action([
        {"language": "python", "tags": ["main"], "source": "print(1)"},
        {"language": "markdown", "tags": [], "source": ""},
    ])
    out = _attach_demo_expansion({"status": "ok", "data": {}}, action)
    assert out["data"]["demo"]["block_count"] == 1


def test_demo_expansion_tolerates_non_dict_data():
    """data 不是 dict 时不应炸（出参形态可能变化）。"""
    action = _demo_action([{"language": "python", "tags": [], "source": "x"}])
    out = _attach_demo_expansion({"status": "failed", "data": None}, action)
    assert out["status"] == "failed"


def test_demo_kind_runs_exec_path_and_attaches(monkeypatch):
    """dispatch 层：demo 必须走 execute（执行入口块）并附加展开内容。"""
    from vools.actus import executor as ex
    from vools.actus import indexer

    demo = _demo_action([{"language": "python", "tags": ["main"], "source": 'print("hi")'}])

    class _FakeRef:
        path = "fake.actus.schema.md"

    monkeypatch.setattr(indexer, "get_action", lambda aid, d=None: _FakeRef())
    monkeypatch.setattr(ex, "load_and_validate", lambda p: demo)

    calls = []

    def fake_execute(action_id, params=None, **kw):
        calls.append(action_id)
        return {"status": "ok", "data": {"result": "ran"}}

    # 关键：先把真 execute 存下来，再打桩——否则下面调的就是 fake 自己，
    # 真 execute（含 kind 分派）根本不会跑。
    real_execute = ex.execute
    monkeypatch.setattr(ex, "execute", fake_execute)
    result = real_execute("myapp.demo", {})
    assert result["status"] == "ok"
    assert calls == ["myapp.demo"], "demo 应先执行入口块"
    assert result["data"]["demo"]["block_count"] == 1
