# -*- coding: utf-8 -*-
"""阶段3：template / bundle / doc 三个无源码动作族的执行语义回归。

ACTUS_REFACTOR_PLAN §3.3 的出口条件包含「template 走 scaffold」。
此前这三个 kind 一律报 kind_unsupported（不再被当 exec 静默执行）。
"""
from vools.actus.executor import (
    _execute_bundle_kind,
    _execute_doc_kind,
    _execute_template_kind,
)
from vools.actus.model import Action


def _action(aid, kind, **extra):
    meta = {"id": aid, "name": aid, "version": "1.0.0", "trust": "sandbox",
            "kind": kind, "platform": "desktop"}
    meta.update(extra)
    return Action(meta=meta, path="", sha256="", blocks=[])


# --------------------------------------------------------------------------
# bundle：列出成员动作 id
# --------------------------------------------------------------------------
def test_bundle_lists_members_from_list():
    bundle = _action("myapp.bundle", "bundle", members=["a", "b", "c"])
    result = _execute_bundle_kind(bundle, "myapp.bundle", {})
    assert result["status"] == "ok"
    assert result["data"]["members"] == ["a", "b", "c"]
    assert result["data"]["count"] == 3


def test_bundle_accepts_comma_string_and_target_fallback():
    bundle = _action("myapp.bundle", "bundle", members="a, b ,c")
    assert _execute_bundle_kind(bundle, "myapp.bundle", {})["data"]["members"] == ["a", "b", "c"]
    fallback = _action("myapp.bundle2", "bundle", target="myapp.only")
    result = _execute_bundle_kind(fallback, "myapp.bundle2", {})
    assert result["data"]["members"] == ["myapp.only"]


def test_bundle_without_members_is_empty_not_error():
    bundle = _action("myapp.empty", "bundle")
    result = _execute_bundle_kind(bundle, "myapp.empty", {})
    assert result["status"] == "ok"
    assert result["data"]["count"] == 0


# --------------------------------------------------------------------------
# doc：仅渲染，不执行
# --------------------------------------------------------------------------
def test_doc_renders_without_executing():
    doc = Action(meta={"id": "myapp.doc", "name": "doc", "version": "1.0.0",
                       "trust": "sandbox", "kind": "doc", "platform": "desktop",
                       "description": "说明文档"}, path="", sha256="", blocks=[],
                 body="# Hello\n\n正文")
    result = _execute_doc_kind(doc, "myapp.doc", {})
    assert result["status"] == "ok"
    assert result["data"]["rendered"] is True
    assert result["data"]["description"] == "说明文档"
    assert result["data"]["body"].startswith("# Hello")


# --------------------------------------------------------------------------
# template：走 scaffold
# --------------------------------------------------------------------------
def test_template_without_description_reports_readably():
    tmpl = _action("myapp.t", "template")
    result = _execute_template_kind(tmpl, "myapp.t", {})
    assert result["status"] == "failed"
    err = result.get("error") or {}
    assert err.get("code") == "param_invalid"
    assert "template" in (err.get("message") or "")


def test_template_calls_scaffold_with_declared_params(monkeypatch):
    from vools.actus import scaffold as sc

    captured = {}

    def fake_scaffold(description, action_id=None, trust="audit",
                      output_dir=None, author="ai-scaffold", repo_root=None):
        captured["description"] = description
        captured["action_id"] = action_id
        captured["trust"] = trust
        return {"path": "/tmp/gen.actus.schema.md", "id": action_id or "gen",
                "trust": trust, "template": "basic",
                "validation": {"valid": True, "errors": []}, "next_steps": []}

    monkeypatch.setattr(sc, "scaffold_action", fake_scaffold)
    tmpl = _action("myapp.t", "template", target="myapp.generated",
                   template="做一个计算器")
    result = _execute_template_kind(tmpl, "myapp.t", {"k": 1})
    assert result["status"] == "ok", result
    assert captured["description"] == "做一个计算器"
    assert captured["action_id"] == "myapp.generated"
    assert result["data"]["scaffold"]["path"] == "/tmp/gen.actus.schema.md"
    assert result["data"]["template_params"] == {"k": 1}


def test_template_dict_template_uses_description_key(monkeypatch):
    from vools.actus import scaffold as sc

    captured = {}

    def fake_scaffold(description, action_id=None, trust="audit",
                      output_dir=None, author="ai-scaffold", repo_root=None):
        captured["description"] = description
        return {"path": "/tmp/x", "id": "x", "trust": trust, "template": "basic",
                "validation": {"valid": True, "errors": []}, "next_steps": []}

    monkeypatch.setattr(sc, "scaffold_action", fake_scaffold)
    tmpl = _action("myapp.t", "template", template={"description": "从 dict 取描述"})
    result = _execute_template_kind(tmpl, "myapp.t", {})
    assert result["status"] == "ok"
    assert captured["description"] == "从 dict 取描述"
