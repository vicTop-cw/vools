# -*- coding: utf-8 -*-
"""计划 §四.5：MCP 工具的 target 形态描述必须与 resolver 能力一致。

背景：MCP 侧与 CLI 此前有同一个缺口——直接把参数当 action_id 用，
resolver 的六形态一个都不生效。本轮先把 resolver 接进 MCP 的只读工具
（actus_info / actus_preview），再把形态写进工具描述——**顺序不能反**，
先写文档就是文档说谎。
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP = os.path.join(ROOT, "vools", "actus", "mcp_server.py")


def _tool_defs():
    src = open(MCP, encoding="utf-8").read()
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        d = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                try:
                    d[k.value] = ast.literal_eval(v)
                except Exception:
                    d[k.value] = "<expr>"
        if "name" in d and "description" in d and isinstance(d.get("name"), str):
            out[d["name"]] = d
    return out


def test_resolver_wired_into_readonly_mcp_tools():
    """actus_info / actus_preview 必须真的走 resolver（源码级契约）。"""
    from vools.actus import mcp_server
    src = open(MCP, encoding="utf-8").read()
    assert "def resolve_action_arg" in src
    assert "aid = resolve_action_arg(args.get('id', ''))" in src, \
        "actus_info / actus_preview 的 id 必须经 resolve_action_arg 解析"


def test_descriptions_document_target_forms():
    """工具描述必须写清六形态（计划 §四.5），且与 resolver 实际能力对齐。

    描述是字符串拼接（`'…' + TARGET_FORMS_HINT`），AST literal_eval 求不出来，
    所以直接对源码文本断言。
    """
    src = open(MCP, encoding="utf-8").read()
    for name in ("actus_info", "actus_preview"):
        idx = src.find("'name': '%s'" % name)
        assert idx > 0, name
        block = src[idx:idx + 900]
        assert "TARGET_FORMS_HINT" in block, "%s 描述未引用形态说明" % name
    hint_idx = src.find("TARGET_FORMS_HINT = (")
    assert hint_idx > 0
    hint = src[hint_idx:hint_idx + 600]
    assert "六种形态" in hint
    for kw in ("动作 id", "可读名", "md5", "路径", "URL"):
        assert kw in hint, "形态说明缺少关键词 %r" % kw


def test_target_forms_hint_matches_resolver_sources():
    """描述里列的形态必须与 resolver 实际返回的 source 集合一致。"""
    import inspect
    from vools.actus import resolver
    src = inspect.getsource(resolver.resolve_target)
    for source in ("'path'", "'url'", "'name'", "'md5'", "'id'"):
        assert source in src, "resolver 未产出 source=%s" % source
    hint = open(MCP, encoding="utf-8").read()
    for kw in ("动作 id", "可读名", "md5", "路径", "URL"):
        assert kw in hint


def test_resolve_action_arg_passthrough_on_failure(monkeypatch):
    """解析不出来必须回退原值（零回归），不能抛异常打断调用方。"""
    from vools.actus import resolver
    from vools.actus.mcp_server import resolve_action_arg

    def boom(*a, **kw):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(resolver, "resolve_target", boom)
    assert resolve_action_arg("something.weird") == "something.weird"


def test_resolve_action_arg_returns_canonical_id(monkeypatch):
    """解析成功时必须返回标准 action_id（name 形态 → id）。"""
    from vools.actus import resolver
    from vools.actus.mcp_server import resolve_action_arg

    class _R:
        action_id = "actus.basics.calculator"

    monkeypatch.setattr(resolver, "resolve_target", lambda raw, **kw: _R())
    assert resolve_action_arg("Calculator") == "actus.basics.calculator"
