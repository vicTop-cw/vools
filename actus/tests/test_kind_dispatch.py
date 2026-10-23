# -*- coding: utf-8 -*-
"""阶段3：非 exec kind（link/alias）执行语义的回归。

ACTUS_REFACTOR_PLAN §3.3 的出口条件是「link 合并参数执行、alias 转发」。
此前执行器完全不感知 kind，link/alias 会被当成普通 exec 动作执行。

本组用例直接测转发逻辑（_execute_forwarding_kind），用 monkeypatch 替掉
execute 递归，从而精确断言参数合并结果，而不依赖文件扫描/索引缓存。
"""
from vools.actus.executor import _execute_forwarding_kind
from vools.actus.model import Action


def _action(aid, kind, target=None, args=None):
    meta = {"id": aid, "name": aid, "version": "1.0.0", "trust": "sandbox",
            "kind": kind, "platform": "desktop"}
    if target:
        meta["target"] = target
    if args is not None:
        meta["args"] = args
    return Action(meta=meta, path="", sha256="", blocks=[])


def test_link_merges_args_as_base_and_caller_overrides(monkeypatch):
    """link：args 作基底、调用方入参覆盖同名键（浅合并）。"""
    from vools.actus import executor as ex
    link = _action("myapp.mylink", "link", target="myapp.target",
                   args={"from_link": "yes", "shared": "link-value"})
    seen = {}

    def fake_execute(action_id, params=None, **kw):
        seen["id"] = action_id
        seen["params"] = params
        return {"status": "ok", "data": {"echo": params}}

    monkeypatch.setattr(ex, "execute", fake_execute)
    result = _execute_forwarding_kind(link, "myapp.mylink",
                                      {"shared": "caller-value", "extra": 1}, "link")
    assert result["status"] == "ok", result
    assert seen["id"] == "myapp.target"
    assert seen["params"]["from_link"] == "yes", "link 的 args 基底没生效"
    assert seen["params"]["shared"] == "caller-value", "调用方入参应覆盖同名键"
    assert seen["params"]["extra"] == 1


def test_alias_forwards_without_merging(monkeypatch):
    """alias：直接转发，不合并 args。"""
    from vools.actus import executor as ex
    alias = _action("myapp.myalias", "alias", target="myapp.target")
    seen = {}

    def fake_execute(action_id, params=None, **kw):
        seen["id"] = action_id
        seen["params"] = params
        return {"status": "ok", "data": {}}

    monkeypatch.setattr(ex, "execute", fake_execute)
    result = _execute_forwarding_kind(alias, "myapp.myalias", {"a": 1}, "alias")
    assert result["status"] == "ok", result
    assert seen["id"] == "myapp.target"
    assert seen["params"] == {"a": 1}, "alias 不应合并 args"


def test_link_without_target_reports_readably():
    link = _action("myapp.badlink", "link")
    result = _execute_forwarding_kind(link, "myapp.badlink", {}, "link")
    assert result["status"] == "failed"
    err = result.get("error") or {}
    assert err.get("code") == "param_invalid"
    assert "target" in (err.get("message") or "")


def test_forwarding_depth_guard_breaks_cycles(monkeypatch):
    """转发层级 ≥5 必须报错（防 link/alias 环）。"""
    from vools.actus import executor as ex
    link = _action("myapp.loop", "link", target="myapp.loop")

    def fake_execute(action_id, params=None, **kw):
        return _execute_forwarding_kind(link, "myapp.loop", {}, "link")

    monkeypatch.setattr(ex, "execute", fake_execute)
    result = _execute_forwarding_kind(link, "myapp.loop", {}, "link")
    assert result["status"] == "failed"
    assert "环" in ((result.get("error") or {}).get("message") or "")
