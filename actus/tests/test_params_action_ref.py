# -*- coding: utf-8 -*-
"""阶段1：入参形态补充验收 —— stdin 与 @action 递归引用。

ACTUS_REFACTOR_PLAN §3.2 的七种入参形态里，`-`（stdin）与
`@action:<id>`（递归引用，取其出参作为入参）此前从未被实测。
本组覆盖正常路径、出参非 dict 的包装、执行失败、深度上限与成环检测。
"""
import io

import pytest

from vools.actus import executor as ex
from vools.actus.resolver import _resolve_action_ref, resolve_params_extended


# --------------------------------------------------------------------------
# stdin 形态
# --------------------------------------------------------------------------
def test_params_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"from_stdin": true}'))
    assert resolve_params_extended("-") == {"from_stdin": True}


def test_params_stdin_must_be_object(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('[1, 2]'))
    with pytest.raises(ValueError):
        resolve_params_extended("-")


# --------------------------------------------------------------------------
# @action 递归引用
# --------------------------------------------------------------------------
def test_params_action_ref_uses_action_output(monkeypatch):
    """@action:<id> 必须执行该动作并把其出参 data 作为入参。"""
    seen = {}

    def fake_execute(action_id, params=None, **kw):
        seen["id"] = action_id
        seen["params"] = params
        return {"status": "ok", "data": {"produced": 42}}

    monkeypatch.setattr(ex, "execute", fake_execute)
    assert resolve_params_extended("@action:myapp.producer") == {"produced": 42}
    assert seen["id"] == "myapp.producer"


def test_params_action_ref_wraps_non_dict_output(monkeypatch):
    monkeypatch.setattr(ex, "execute",
                        lambda aid, params=None, **kw: {"status": "ok", "data": [1, 2]})
    assert resolve_params_extended("@action:myapp.producer") == {"output": [1, 2]}


def test_params_action_ref_failure_reports(monkeypatch):
    monkeypatch.setattr(ex, "execute",
                        lambda aid, params=None, **kw: {"status": "failed",
                                                        "error": {"code": "boom"}})
    with pytest.raises(Exception) as exc:
        resolve_params_extended("@action:myapp.bad")
    assert getattr(exc.value, "code", "") == "action_ref_failed", exc.value


def test_params_action_ref_depth_limit():
    with pytest.raises(Exception) as exc:
        _resolve_action_ref("myapp.loop", max_depth=2, _depth=2, _visited=set())
    assert getattr(exc.value, "code", "") == "action_ref_depth_exceeded", exc.value


def test_params_action_ref_cycle_detected():
    with pytest.raises(Exception) as exc:
        _resolve_action_ref("myapp.loop", _visited={"myapp.loop"})
    assert getattr(exc.value, "code", "") == "action_ref_cycle", exc.value
