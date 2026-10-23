# -*- coding: utf-8 -*-
"""计划 §六.4：link 的深合并（开放问题落地）。

原实现只做浅合并（`dict.update`）：嵌套 dict 会被**整块替换**，组合场景下
调用方无法只覆盖子键。现在按动作 `meta['merge']` 支持 deep（递归合并），
默认仍是 shallow 保证零回归。
"""
from vools.actus.executor import _deep_merge_params, _merge_link_params
from vools.actus.model import Action


def _link(args, merge=None):
    meta = {"id": "myapp.link", "name": "L", "version": "1.0.0", "trust": "sandbox",
            "kind": "link", "target": "myapp.target", "platform": "desktop",
            "args": args}
    if merge is not None:
        meta["merge"] = merge
    return Action(meta=meta, path="", sha256="", blocks=[])


BASE = {"env": {"A": "1", "B": "2"}, "tags": ["x", "y"], "keep": "yes"}
CALLER = {"env": {"A": "9"}, "tags": ["z"]}


# --------------------------------------------------------------------------
# 默认 shallow：嵌套 dict 整体替换（零回归）
# --------------------------------------------------------------------------
def test_default_shallow_replaces_nested_dict():
    merged = _merge_link_params(_link(BASE), CALLER)
    assert merged["env"] == {"A": "9"}, "浅合并不该保留 base 的 B"
    assert merged["tags"] == ["z"]
    assert merged["keep"] == "yes", "顶层未覆盖的键应保留"


def test_shallow_mode_explicit_is_same_as_default():
    assert _merge_link_params(_link(BASE, merge="shallow"), CALLER) == \
        _merge_link_params(_link(BASE), CALLER)


# --------------------------------------------------------------------------
# deep：递归合并嵌套 dict，调用方叶子优先
# --------------------------------------------------------------------------
def test_deep_merges_nested_dict():
    merged = _merge_link_params(_link(BASE, merge="deep"), CALLER)
    assert merged["env"] == {"A": "9", "B": "2"}, "深合并应保留 B 并覆盖 A"
    assert merged["tags"] == ["z"], "list 整体替换，不做拼接"
    assert merged["keep"] == "yes"


def test_deep_merges_three_levels():
    base = {"a": {"b": {"c": 1, "d": 2}}}
    caller = {"a": {"b": {"c": 9}}}
    assert _deep_merge_params(base, caller) == {"a": {"b": {"c": 9, "d": 2}}}


def test_deep_replaces_when_types_differ():
    """base 是 dict、caller 是标量（或反之）时整体替换，不做递归。"""
    assert _deep_merge_params({"a": {"x": 1}}, {"a": 5}) == {"a": 5}
    assert _deep_merge_params({"a": 5}, {"a": {"x": 1}}) == {"a": {"x": 1}}


def test_deep_lists_are_replaced_not_concatenated():
    assert _deep_merge_params({"a": [1, 2]}, {"a": [3]}) == {"a": [3]}


def test_deep_does_not_mutate_inputs():
    base = {"a": {"b": 1}}
    caller = {"a": {"c": 2}}
    _deep_merge_params(base, caller)
    assert base == {"a": {"b": 1}}
    assert caller == {"a": {"c": 2}}


# --------------------------------------------------------------------------
# 边界
# --------------------------------------------------------------------------
def test_non_dict_args_ignored():
    """args 不是 dict 时原样透传入参（两侧老行为一致）。"""
    action = _link("oops")
    assert _merge_link_params(action, {"a": 1}) == {"a": 1}


def test_empty_caller_returns_base():
    assert _merge_link_params(_link(BASE, merge="deep"), {}) == BASE
