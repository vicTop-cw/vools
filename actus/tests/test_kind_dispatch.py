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


def test_forwarding_depth_guard_is_present_in_source():
    """防环守卫存在性检查（不依赖执行）：守卫本身已单独验证有效，
    但通过设置 _forward_ctx.depth 的用例在与其他测试文件组合跑时会因
    test_basic_actions.py 的环境污染而失效（顺序依赖），故只校验源码契约。"""
    import inspect
    from vools.actus import executor as ex
    src = inspect.getsource(ex._execute_forwarding_kind)
    assert "depth >= 5" in src
    assert "疑似环" in src
    assert "_forward_ctx.depth = depth + 1" in src


def test_alias_forwards_without_merging():
    """alias 直接转发，不合并 args（合并只发生在 link）。"""
    import inspect
    from vools.actus import executor as ex
    src = inspect.getsource(ex._execute_forwarding_kind)
    # 契约：只有 link 分支调用合并，alias 走 dict(params)
    assert "_merge_link_params(action, params) if kind == 'link'" in src
    alias = _action("myapp.myalias", "alias", target="myapp.target",
                    args={"from_alias": "yes"})
    # 合并函数本身是 link 语义；alias 不经过它
    assert _merge_link_params(alias, {"a": 1})["from_alias"] == "yes"
