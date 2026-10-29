# -*- coding: utf-8 -*-
"""计划 §四.5：MCP 工具的 target 形态描述必须与 resolver 能力一致。

背景：MCP 侧与 CLI 此前有同一个缺口——直接把参数当 action_id 用，
resolver 的六形态一个都不生效。本轮先把 resolver 接进 MCP 的只读工具
（actus_info / actus_preview），再把形态写进工具描述——**顺序不能反**，
先写文档就是文档说谎。
"""
import ast
import os

import pytest

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
    """actus_info / actus_preview 必须真的走 resolver（**行为**契约）。

    第 20 轮：删掉源码字符串断言，改为**调用 MCP 工具**，用 name/md5 形态的
    实际解析结果证明 resolver 在链路上；再用不存在的 id 证明没有"全部吞掉"
    的退化（守卫被删 → name 形态会退化成 action_not_found，立刻红）。
    """
    import io as _io
    import json as _json
    from vools.actus import mcp_server
    from vools.actus.indexer import get_action

    action = get_action("actus.basics.calculator")
    canonical = action.meta["id"]
    server = mcp_server.MCPServer(stdout=_io.BytesIO())

    def call(tool, arguments):
        raw = server._call_tool({"name": tool, "arguments": arguments})
        return raw.get("isError"), _json.loads(raw["content"][0]["text"])

    err, payload = call("actus_info", {"id": action.meta["name"]})
    assert err is False, payload
    assert payload["data"]["id"] == canonical, payload

    err, payload = call("actus_info", {"id": action.md5})
    assert err is False, payload
    assert payload["data"]["id"] == canonical, payload

    err, payload = call("actus_preview",
                        {"id": action.meta["name"], "args": {"param": "1"}})
    assert err is False, payload
    assert payload["data"]["action"]["id"] == canonical, payload

    err, payload = call("actus_info", {"id": "no.such.action"})
    assert err is True and payload["error"]["code"] == "action_not_found", payload


def test_descriptions_document_target_forms():
    """工具描述必须写清六形态（计划 §四.5）——**从 tools/list 输出断言**。

    第 20 轮：不再读源码文本，改为取 MCP `_list_tools()` 的**渲染后描述**
    （这才是 AI/客户端实际看到的东西）。守卫被删/描述被截断 → 立刻红。
    """
    import io as _io
    from vools.actus import mcp_server

    tools = {t["name"]: t for t in
             mcp_server.MCPServer(stdout=_io.BytesIO())._list_tools()}
    for name in ("actus_info", "actus_preview"):
        desc = tools[name]["description"]
        assert "六种形态" in desc, "%s 描述未写清形态: %r" % (name, desc[:120])
        for kw in ("动作 id", "可读名", "md5", "路径", "URL"):
            assert kw in desc, "%s 描述缺少形态关键词 %r" % (name, kw)


def test_target_forms_hint_matches_resolver_sources(tmp_path):
    """描述里列的形态必须与 resolver **实际产出**的 source 集合一致。

    第 20 轮：删掉 `inspect.getsource(resolve_target)` 子串断言，改为对每种
    形态**真的调用** resolve_target 并收集 source；URL 分支用 monkeypatch
    替换下载实现（不联网、不落真实缓存）。
    """
    import io as _io
    from vools.actus import resolver as r
    from vools.actus import mcp_server

    action = __import__("vools.actus", fromlist=["get_action"]).get_action(
        "actus.basics.calculator")
    scattered = tmp_path / "r20.scattered.actus.md"
    scattered.write_text(
        "```json #!cfg\n{\"id\": \"r20.scattered.act\", \"name\": \"R20\","
        " \"version\": \"1.0.0\", \"trust\": \"sandbox\", \"kind\": \"demo\","
        " \"platform\": [\"desktop\"]}\n```\n", encoding="utf-8")

    seen = set()
    seen.add(r.resolve_target(action.meta["id"]).source)
    seen.add(r.resolve_target(action.meta["name"]).source)
    seen.add(r.resolve_target(action.md5).source)
    seen.add(r.resolve_target(str(scattered)).source)

    original = r._download_url
    r._download_url = lambda url, allow_hosts=None: str(scattered)
    try:
        seen.add(r.resolve_target("https://example.invalid/a.actus.md",
                                  allow_hosts=["example.invalid"]).source)
    finally:
        r._download_url = original
    assert seen == {"id", "name", "md5", "path", "url"}, seen

    tools = {t["name"]: t for t in
             mcp_server.MCPServer(stdout=_io.BytesIO())._list_tools()}
    for kw in ("动作 id", "可读名", "md5", "路径", "URL"):
        assert kw in tools["actus_info"]["description"]


def test_resolve_action_arg_passthrough_on_failure(monkeypatch):
    """解析不出来必须回退原值（零回归），不能抛异常打断调用方。"""
    from vools.actus import resolver
    from vools.actus.mcp_server import resolve_action_arg

    def boom(*a, **kw):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(resolver, "resolve_target", boom)
    assert resolve_action_arg("something.weird") == "something.weird"


def test_resolve_action_arg_reports_ambiguity(monkeypatch):
    """歧义必须显式报（计划 §六.2）：结构化 ambiguous + 候选列表，与 CLI 对齐。"""
    from vools.actus import resolver
    from vools.actus.mcp_server import resolve_action_arg
    from vools.actus.errors import ActionError

    class _R:
        action_id = ""
        ambiguous = ["actus.a.one", "actus.b.two"]

    monkeypatch.setattr(resolver, "resolve_target", lambda raw, **kw: _R())
    with pytest.raises(ActionError) as exc:
        resolve_action_arg("Dup")
    assert exc.value.code == "ambiguous", exc.value
    details = getattr(exc.value, "details", None) or {}
    assert details.get("candidates") == ["actus.a.one", "actus.b.two"], details


def test_resolve_action_arg_falls_back_on_resolver_error(monkeypatch):
    """解析器自身异常仍回退原值（零回归）。"""
    from vools.actus import resolver
    from vools.actus.mcp_server import resolve_action_arg

    def boom(*a, **kw):
        raise RuntimeError("exploded")

    monkeypatch.setattr(resolver, "resolve_target", boom)
    assert resolve_action_arg("weird") == "weird"


def test_resolve_action_arg_returns_canonical_id(monkeypatch):
    """解析成功时必须返回标准 action_id（name 形态 → id）。"""
    from vools.actus import resolver
    from vools.actus.mcp_server import resolve_action_arg

    class _R:
        action_id = "actus.basics.calculator"
        ambiguous = []

    monkeypatch.setattr(resolver, "resolve_target", lambda raw, **kw: _R())
    assert resolve_action_arg("Calculator") == "actus.basics.calculator"
