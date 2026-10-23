# -*- coding: utf-8 -*-
"""七种 kind 在**异常输入**下的行为契约（计划 §3.3 + 错误码一致性）。

现有用例主要覆盖正常路径；本组锁定「声明不完整的非 exec 动作」必须给出
**结构化 param_invalid**，而不是静默 no-op 报成功。

实测发现的不一致：`link` / `alias` 缺 target 会抛 param_invalid（正确），
但 `kind=bundle` 缺 members 时返回 `status=ok, members=[], count=0` ——
空操作却报成功。已统一为 param_invalid。
"""
import pytest

from vools.actus import executor as ex
from vools.actus.model import Action


def _action(kind, **meta):
    base = {"id": "myapp.probe", "name": "P", "version": "1.0.0",
            "trust": "sandbox", "kind": kind, "platform": "desktop"}
    base.update(meta)
    return Action(meta=base, path="", sha256="", blocks=[], body="# probe\n")


def _run(action):
    return ex.execute(action.meta["id"], {}, confirmed=True, preparsed_action=action)


# --------------------------------------------------------------------------
# 缺配置必须报 param_invalid（不能静默成功）
# --------------------------------------------------------------------------
def test_link_without_target_is_invalid():
    r = _run(_action("link"))
    assert r["status"] == "failed"
    assert (r.get("error") or {}).get("code") == "param_invalid"


def test_alias_without_target_is_invalid():
    r = _run(_action("alias"))
    assert r["status"] == "failed"
    assert (r.get("error") or {}).get("code") == "param_invalid"


def test_bundle_without_members_is_invalid():
    """缺陷回归：此前返回 status=ok（空操作报成功）。"""
    r = _run(_action("bundle"))
    assert r["status"] == "failed", "bundle 无成员不该报成功: %r" % (r,)
    assert (r.get("error") or {}).get("code") == "param_invalid"


def test_template_without_description_is_invalid():
    r = _run(_action("template"))
    assert r["status"] == "failed"
    assert (r.get("error") or {}).get("code") == "param_invalid"


# --------------------------------------------------------------------------
# 有配置时正常工作
# --------------------------------------------------------------------------
def test_bundle_with_members_ok():
    r = _run(_action("bundle", members=["a.one", "b.two"]))
    assert r["status"] == "ok"
    assert r["data"]["count"] == 2


def test_bundle_with_comma_string_members_ok():
    r = _run(_action("bundle", members="a.one, b.two ,"))
    assert r["status"] == "ok"
    assert r["data"]["members"] == ["a.one", "b.two"]


def test_bundle_falls_back_to_target():
    r = _run(_action("bundle", target="a.only"))
    assert r["status"] == "ok"
    assert r["data"]["members"] == ["a.only"]


def test_doc_without_body_is_ok():
    """doc 是纯渲染，空正文渲染为空是合理行为（不报错）。"""
    r = _run(_action("doc"))
    assert r["status"] == "ok"
    assert r["data"]["rendered"] is True
