# -*- coding: utf-8 -*-
"""阶段3：非 exec kind（link/alias）执行语义的回归。

ACTUS_REFACTOR_PLAN §3.3 的出口条件是「link 合并参数执行、alias 转发」。
此前执行器完全不感知 kind，link/alias 会被当成普通 exec 动作执行。

本组用例测**纯逻辑与错误路径**（_merge_link_params / 缺 target / 防环），
不依赖打桩模块全局 execute——那样在与其他测试文件组合跑时会被环境污染
（实测：单独跑全绿、与 test_basic_actions.py 一起跑就红）。
"""
from vools.actus.executor import _execute_forwarding_kind, _merge_link_params
from vools.actus.model import Action


def _action(aid, kind, target=None, args=None):
    meta = {"id": aid, "name": aid, "version": "1.0.0", "trust": "sandbox",
            "kind": kind, "platform": "desktop"}
    if target:
        meta["target"] = target
    if args is not None:
        meta["args"] = args
    return Action(meta=meta, path="", sha256="", blocks=[])


# --------------------------------------------------------------------------
# 纯合并逻辑
# --------------------------------------------------------------------------
def test_merge_link_params_base_and_caller_overrides():
    """link：args 作基底、调用方入参覆盖同名键（浅合并）。"""
    link = _action("myapp.mylink", "link", target="myapp.target",
                   args={"from_link": "yes", "shared": "link-value"})
    merged = _merge_link_params(link, {"shared": "caller-value", "extra": 1})
    assert merged["from_link"] == "yes", "link 的 args 基底没生效"
    assert merged["shared"] == "caller-value", "调用方入参应覆盖同名键"
    assert merged["extra"] == 1


def test_merge_link_params_without_args():
    """link 没有 args 时，入参原样透传。"""
    link = _action("myapp.mylink", "link", target="myapp.target")
    assert _merge_link_params(link, {"a": 1}) == {"a": 1}


def test_merge_link_params_non_dict_args_is_tolerated():
    """args 不是 dict 时不应炸（只合并 dict 形态）。"""
    link = _action("myapp.mylink", "link", target="myapp.target", args="oops")
    assert _merge_link_params(link, {"a": 1}) == {"a": 1}


# --------------------------------------------------------------------------
# 错误路径（不需要 execute）
# --------------------------------------------------------------------------
def test_link_without_target_reports_readably():
    link = _action("myapp.badlink", "link")
    result = _execute_forwarding_kind(link, "myapp.badlink", {}, "link")
    assert result["status"] == "failed"
    err = result.get("error") or {}
    assert err.get("code") == "param_invalid"
    assert "target" in (err.get("message") or "")


def test_forwarding_depth_guard_rejects_sixth_level(monkeypatch):
    """防环守卫必须是**行为**：直线转发到第 6 层必须被拒且报「深度超限」。

    退步了会怎样（旧测试用源码子串 `"depth >= 5" in src`）：
      守卫条件被改成 `if depth >= 5 and False:`（永久失效，真环之外的深链会无限递归/
      栈溢出）时，源码里那几条子串**仍然都在**，旧测试照绿。这里改为真正跑一遍转发链：
      用 monkeypatch 让 `execute` 递归回 `_execute_forwarding_kind`，逐层 +1 直到上限。
    断言：返回 failed + code=param_invalid + 消息含「转发层级 ≥5」/「深度超限」；
    线程局部 depth 必须被 finally 复位为 0（防污染后续调用）。
    """
    from vools.actus import executor as ex

    calls = []

    def fake_execute(target, params=None, **kw):
        calls.append(target)
        # 下一层继续转发（目标名故意与前缀不同，保证不是「真环」而是直线深链）
        return ex._execute_forwarding_kind(
            _action(target, "alias", target=target + "-next"), target, params or {},
            "alias", **kw)

    monkeypatch.setattr(ex, "execute", fake_execute)
    result = ex._execute_forwarding_kind(
        _action("myapp.l1", "alias", target="l2"), "myapp.l1", {}, "alias")

    err = result.get("error") or {}
    assert result["status"] == "failed", result
    assert err.get("code") == "param_invalid", err
    message = err.get("message") or ""
    assert ("转发层级 ≥5" in message) or ("深度超限" in message), \
        "第 6 层转发必须被拒并说明深度超限，实得 %r" % (message,)
    # 允许走到第 5 层，第 6 层被拒 → 实际转发 5 次
    assert len(calls) == 5, "应在第 5 层之后拒绝第 6 层，实际转发次数=%d" % len(calls)
    assert getattr(ex._forward_ctx, "depth", 0) == 0, \
        "守卫返回后线程局部 depth 未复位（会污染同线程后续转发）"
    assert getattr(ex._forward_ctx, "chain", []) == [], "转发链未复位"


def test_true_cycle_reports_action_ref_cycle(monkeypatch):
    """真环（目标已在转发链上）必须报 `action_ref_cycle`，而不是只报深度超限。

    退步了会怎样：把「环」与「深链」混为一谈（旧实现只数深度、消息写死「疑似环」）
    → 用户拿到的是「层级超限」这种误导性建议（拆分动作），而真正的环永远修不好。
    """
    from vools.actus import executor as ex

    def fake_execute(target, params=None, **kw):
        # a1 → a2；a2 又指回 a1 → 真环
        nxt = "a1" if target == "a2" else "a2"
        return ex._execute_forwarding_kind(
            _action(target, "alias", target=nxt), target, params or {}, "alias", **kw)

    monkeypatch.setattr(ex, "execute", fake_execute)
    result = ex._execute_forwarding_kind(
        _action("a1", "alias", target="a2"), "a1", {}, "alias")

    err = result.get("error") or {}
    assert result["status"] == "failed"
    assert err.get("code") == "action_ref_cycle", err
    assert "转发成环" in (err.get("message") or ""), err
    assert (err.get("details") or {}).get("chain"), "环检测必须回传完整链路"


def test_alias_forwards_params_unchanged_but_link_merges(monkeypatch):
    """行为契约：alias 转发**不合并**自身 args；link 才做「args 基底 + 调用方覆盖」。

    退步了会怎样（旧测试只断言源码里 `... if kind == 'link'` 子串）：
    实现把 alias 也走合并（或 link 忘了合并）时，子串可能仍在，但转发出去的入参
    已经错了 —— 目标动作会收到不该有的默认参数。这里直接截获真正转发给
    `execute` 的 params 来断言。
    """
    from vools.actus import executor as ex

    captured = []

    def fake_execute(target, params=None, **kw):
        captured.append((target, dict(params or {})))
        return {"status": "ok", "data": None, "error": None}

    monkeypatch.setattr(ex, "execute", fake_execute)

    alias = _action("myapp.alias", "alias", target="myapp.target",
                    args={"from_alias": "yes", "base": "alias-base"})
    ex._execute_forwarding_kind(alias, "myapp.alias", {"caller": 1}, "alias")
    link = _action("myapp.link", "link", target="myapp.target",
                   args={"from_link": "yes", "shared": "link-base"})
    ex._execute_forwarding_kind(link, "myapp.link",
                                {"shared": "caller", "caller": 1}, "link")

    alias_target, alias_params = captured[0]
    link_target, link_params = captured[1]
    assert alias_target == "myapp.target" and link_target == "myapp.target"
    assert alias_params == {"caller": 1}, \
        "alias 不得合并自身 args，实际转发入参=%r" % (alias_params,)
    assert link_params == {"from_link": "yes", "shared": "caller", "caller": 1}, \
        "link 应合并 args 基底并让调用方覆盖同名键，实际=%r" % (link_params,)
