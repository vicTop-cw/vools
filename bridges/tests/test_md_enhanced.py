"""vools.bridge.md 增强测试：代码折叠 + MCP 块 + CSS/JS 别名 + entry 双语义

本文件覆盖 2026-10 打磨轮新增的 4 个能力：
1. 代码折叠（fold/collapse/fold-label 指令 + CodeBlock.foldable/collapsed/fold_label + 渲染）
2. MCP 块语言（mcp_client.py stdio JSON-RPC，零第三方依赖）
3. CSS 静态块 + Node.js 别名（node/nodejs/js/javascript）
4. entry 双语义（语言选择器 / tag 过滤器向后兼容）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.md.parser import parse_md, CodeBlock
from vools.bridge.md.directives import (
    BLOCK_DIRECTIVE_KEYS, parse_block_directives, validate_directives,
)
from vools.bridge.md.runner import (
    run_md, _execute_block, BUILTIN_BLOCK_LANGUAGES,
)

# ─────────────────────────────────────────────────────────
# 1. 代码折叠
# ─────────────────────────────────────────────────────────

def test_fold_directive_in_block_keys():
    """fold/collapse/fold-label 必须登记在 BLOCK_DIRECTIVE_KEYS 里。"""
    for k in ("fold", "collapse", "fold-label"):
        assert k in BLOCK_DIRECTIVE_KEYS, f"missing directive key: {k}"


def test_parse_fold_directive_bare():
    """#!fold（无值）→ foldable=True，collapse 默认 False。"""
    d = parse_block_directives("#!fold")
    assert "fold" in d
    assert d.get("fold") == ""


def test_parse_fold_directive_with_collapse():
    """#!fold=manual #!collapse=true → foldable=True, collapsed=True。"""
    d = parse_block_directives("#!fold=manual #!collapse=true")
    assert d.get("fold") == "manual"
    assert d.get("collapse") == "true"


def test_parse_fold_directive_with_fold_label():
    """#!fold=auto #!fold-label=展开更多 → fold_label 生效。"""
    d = parse_block_directives("#!fold=auto #!fold-label=展开更多")
    assert d.get("fold-label") == "展开更多"


def test_parse_fold_in_md():
    """解析 .md 时 fold/collapse/fold-label 指令正确填充 CodeBlock 字段。"""
    md = """#!config test.md

```python #!run #!fold=auto #!collapse=true #!fold-label=更多
print("hi")
```
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False,
                                      encoding='utf-8') as f:
        f.write(md)
        path = f.name
    try:
        parsed = parse_md(path)
        b0 = parsed.blocks[0]
        assert b0.foldable is True, f"foldable should be True, got {b0.foldable}"
        assert b0.collapsed is True, f"collapsed should be True, got {b0.collapsed}"
        assert b0.fold_label == "更多", f"fold_label should be '更多', got {b0.fold_label!r}"
    finally:
        os.unlink(path)


def test_validate_fold_directives():
    """fold/collapse/fold-label 值合法性校验。"""
    # fold=bad → 错误
    errors = validate_directives({"fold": "bad"}, "python")
    assert any("fold" in e for e in errors), f"should error on fold=bad: {errors}"

    # collapse=bad → 错误
    errors = validate_directives({"collapse": "bad"}, "python")
    assert any("collapse" in e for e in errors), f"should error on collapse=bad: {errors}"


def test_code_block_defaults_backward_compat():
    """无 fold 指令时 foldable/collapsed 默认 False，行为完全向后兼容。"""
    b = CodeBlock(index=0, language="python", directives={}, content="")
    assert b.foldable is False
    assert b.collapsed is False
    assert b.fold_label == ""


# ─────────────────────────────────────────────────────────
# 2. MCP 块语言
# ─────────────────────────────────────────────────────────

_MCP_SERVER_SRC = r'''
import json, sys

def handle(method, params):
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-echo", "version": "0.1"},
        }
    if method == "tools/list":
        return {
            "tools": [
                {"name": "ping", "description": "返回 pong"},
                {"name": "echo", "description": "返回参数原样", "inputSchema": {"type": "object"}},
            ],
        }
    if method == "tools/call":
        name = (params or {}).get("name")
        args = (params or {}).get("arguments") or {}
        if name == "ping":
            return {"content": [{"type": "text", "text": "pong"}], "isError": False}
        if name == "echo":
            text = args.get("message", "")
            return {"content": [{"type": "text", "text": "echo: " + text}], "isError": False}
        return {"content": [{"type": "text", "text": "unknown tool: " + str(name)}], "isError": True}
    return None

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            rid = req.get("id")
            method = req.get("method", "")
            params = req.get("params", {})
            result = handle(method, params)
            if rid is not None:
                print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False), flush=True)
        except Exception as e:
            if rid is not None:
                print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(e)}}), flush=True)

main()
'''

def _write_mcp_server(tmpdir):
    path = os.path.join(tmpdir, "_mcp_echo_server.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_MCP_SERVER_SRC)
    return path


def test_mcp_client_ping():
    """MCP 客户端 connect + list_tools + call_tool(ping)。"""
    from vools.bridge.md.mcp_client import MCPClient, MCPClientError
    with tempfile.TemporaryDirectory() as td:
        srv = _write_mcp_server(td)
        client = MCPClient({"command": sys.executable, "args": [srv]}, timeout=10)
        try:
            client.connect()
            tools = client.list_tools()
            names = [t["name"] for t in tools]
            assert "ping" in names and "echo" in names, f"tools: {names}"
            res = client.call_tool("ping", {})
            texts = [c.get("text", "") for c in res.get("content", [])]
            assert "pong" in texts, f"ping result: {texts}"
        finally:
            client.close()


def test_mcp_client_echo():
    """MCP 客户端 call_tool(echo) 传参往返。"""
    from vools.bridge.md.mcp_client import MCPClient
    with tempfile.TemporaryDirectory() as td:
        srv = _write_mcp_server(td)
        client = MCPClient({"command": sys.executable, "args": [srv]}, timeout=10)
        try:
            client.connect()
            res = client.call_tool("echo", {"message": "hello md"})
            texts = [c.get("text", "") for c in res.get("content", [])]
            assert "echo: hello md" in texts, f"echo result: {texts}"
        finally:
            client.close()


def test_mcp_directive_quoted_server():
    """引号值 server="cmd args" 能完整解析（含空格）。"""
    d = parse_block_directives('#!server="python a.py" #!tool=ping')
    assert d.get("server") == "python a.py", d
    assert d.get("tool") == "ping", d


def test_mcp_directive_simple_server():
    """未加引号的 server=name 解析为简单名。"""
    d = parse_block_directives("#!server=filesystem #!tool=read_file")
    assert d.get("server") == "filesystem"
    assert d.get("tool") == "read_file"


def test_mcp_block_via_runner():
    """通过 _execute_block 跑一个 mcp 块（内联 server 命令）。"""
    with tempfile.TemporaryDirectory() as td:
        srv = _write_mcp_server(td)
        # 直接构造 CodeBlock 时，directive 值不含引号（引号是 md 解析阶段剥掉的）
        block = CodeBlock(
            index=0, language="mcp",
            directives={"server": f"{sys.executable} {srv}", "tool": "ping"},
            content="{}",
        )
        out, err, code = _execute_block(block, {}, {}, None, 10)
        assert code == 0, f"MCP block failed: {err}"
        assert "pong" in out, f"MCP ping output: {out!r}"


def test_mcp_block_via_parse_md():
    """通过 parse_md + _execute_block 跑 mcp 块（端到端）。"""
    with tempfile.TemporaryDirectory() as td:
        srv = _write_mcp_server(td)
        quoted = f'"{sys.executable} {srv}"'
        md = f"""#!config test.md

```mcp #!server={quoted} #!tool=ping
```
"""
        mdp = os.path.join(td, "test.md")
        with open(mdp, "w", encoding="utf-8") as f:
            f.write(md)
        parsed = parse_md(mdp)
        b0 = parsed.blocks[0]
        assert b0.language == "mcp", f"language: {b0.language}"
        out, err, code = _execute_block(b0, {}, {}, None, 10)
        assert code == 0, f"MCP via parse_md failed: {err}"
        assert "pong" in out, f"output: {out!r}"


# ─────────────────────────────────────────────────────────
# 3. CSS 块 + Node.js 别名
# ─────────────────────────────────────────────────────────

def test_builtin_has_css():
    assert "css" in BUILTIN_BLOCK_LANGUAGES


def test_builtin_has_javascript():
    for alias in ("node", "nodejs", "js", "javascript"):
        assert alias in BUILTIN_BLOCK_LANGUAGES, f"missing {alias}"


def test_css_block_writes_file():
    """CSS 块把内容写入 build_dir/artifacts/css/block_N.css。"""
    with tempfile.TemporaryDirectory() as td:
        block = CodeBlock(index=0, language="css", directives={}, content="body { color: red; }")
        ctx = {"build_dir": td}
        out, err, code = _execute_block(block, ctx, {}, None, 10)
        assert code == 0, f"CSS block failed: {err}"
        path = os.path.join(td, "artifacts", "css", "block_0.css")
        assert os.path.exists(path), f"expected {path}"
        with open(path, encoding="utf-8") as f:
            assert "color: red" in f.read()


@pytest.mark.skipif(shutil.which("node") is None, reason="node 未安装")
def test_js_block_executes():
    """javascript 别名块通过 node CLI 执行。"""
    block = CodeBlock(index=0, language="javascript", directives={}, content='console.log("hello");')
    out, err, code = _execute_block(block, {}, {}, None, 10)
    assert code == 0, f"JS failed: {err}"
    assert "hello" in out


@pytest.mark.skipif(shutil.which("node") is None, reason="node 未安装")
def test_node_alias_executes():
    """node 别名与 js 等价。"""
    block = CodeBlock(index=0, language="node", directives={}, content="console.log(1 + 2);")
    out, err, code = _execute_block(block, {}, {}, None, 10)
    assert code == 0, f"node failed: {err}"
    assert "3" in out


# ─────────────────────────────────────────────────────────
# 4. entry 双语义
# ─────────────────────────────────────────────────────────

def _write_md(tmpdir, content, name="test.md"):
    p = os.path.join(tmpdir, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def test_entry_language_selector_python():
    """entry=python 时只执行 python 块（语言选择器）。"""
    md = """#!config test.md
#!entry python

```python #!run
print("from python")
```

```shell #!run
echo "from shell"
```

```javascript #!run
console.log("from js");
```
"""
    with tempfile.TemporaryDirectory() as td:
        mdp = _write_md(td, md)
        build = os.path.join(td, "build")
        report = run_md(mdp, build_dir=build, only=[], parallel=False)
        brs = report.get("blocks", [])
        langs = {b["language"] for b in brs if b["status"] == "ok"}
        assert "python" in langs, f"python should run: {langs}"
        assert "shell" not in langs, f"shell should NOT run: {langs}"
        assert "javascript" not in langs, f"js should NOT run: {langs}"


def test_entry_tag_filter_backward_compat():
    """entry=main 时只执行 tag=main 的块（旧行为向后兼容）。"""
    md = """#!config test.md
#!entry main

```python #!run #!tag=main
print("main block")
```

```python #!run #!tag=other
print("other block")
```

```shell #!run #!tag=main
echo "shell main"
```
"""
    with tempfile.TemporaryDirectory() as td:
        mdp = _write_md(td, md)
        build = os.path.join(td, "build")
        report = run_md(mdp, build_dir=build, only=[], parallel=False)
        brs = report.get("blocks", [])
        tags = {tuple(b["tag"]) for b in brs if b["status"] == "ok"}
        assert ("main",) in tags, f"'main' tag should run: {tags}"
        assert ("other",) not in tags, f"'other' tag should NOT run: {tags}"


# ─────────────────────────────────────────────────────────
# 5. 双版本漂移回归
# ─────────────────────────────────────────────────────────

def test_mcp_client_module_exists():
    """mcp_client 模块必须在已安装的 vools.bridge.md 里可导入。"""
    from vools.bridge.md import mcp_client
    assert hasattr(mcp_client, "MCPClient")
    assert hasattr(mcp_client, "execute_mcp_block")