"""
vools.bridge.md kinds — 分类路由 / 配置块 / http / sqlite 块测试

覆盖：
- resolve_block_kind / resolve_block_role 三层映射
- static 块（toml deps / yaml runtime / ini legacy）
- #!configs action-config 块
- sqlite 块（stdlib sqlite3）
- http 块（stdlib urllib + 本地测试服务器）
- 指令校验新增规则
"""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

# 确保测试能导入 vools.bridge
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.md.directives import parse_block_directives, validate_directives  # noqa: E402
from vools.bridge.md.parser import CodeBlock  # noqa: E402
from vools.bridge.md.runner import (  # noqa: E402
    DEFAULT_ROLE_MAP,
    KIND_BRIDGE,
    KIND_DATABASE,
    KIND_EXEC,
    KIND_META,
    KIND_PROTOCOL,
    KIND_RENDER,
    KIND_STATIC,
    LANGUAGE_KIND_MAP,
    ROLE_ACTION_CONFIG,
    ROLE_DEPS,
    ROLE_GEN_CONFIG,
    ROLE_LEGACY,
    ROLE_RUNTIME,
    resolve_block_kind,
    resolve_block_role,
    _execute_block,
)


def _block(lang: str, content: str = "", directives: dict = None, index: int = 0) -> CodeBlock:
    return CodeBlock(
        index=index,
        language=lang,
        directives=directives or {},
        content=content,
    )


def _ctx(tmp_path):
    return {"workdir": str(tmp_path), "build_dir": str(tmp_path)}


def _config():
    return {}


# ═══════════════════════════════════════════════════════
# A1: kind / role 三层映射
# ═══════════════════════════════════════════════════════


class TestKindRouting:
    """resolve_block_kind 三层映射。"""

    def test_exec_kinds(self):
        for lang in ("python", "shell", "bash", "sh", "bat", "cmd", "node", "js"):
            assert resolve_block_kind(_block(lang)) == KIND_EXEC, lang

    def test_static_kinds(self):
        for lang in ("css", "json", "toml", "yaml", "ini", "mermaid", "latex"):
            assert resolve_block_kind(_block(lang)) == KIND_STATIC, lang

    def test_protocol_kinds(self):
        for lang in ("mcp", "http"):
            assert resolve_block_kind(_block(lang)) == KIND_PROTOCOL, lang

    def test_database_kinds(self):
        for lang in ("sql", "sqlite", "mysql", "postgresql"):
            assert resolve_block_kind(_block(lang)) == KIND_DATABASE, lang

    def test_render_kind(self):
        assert resolve_block_kind(_block("html")) == KIND_RENDER

    def test_bridge_kinds(self):
        for lang in ("c", "cpp", "go", "rust", "java", "kotlin", "swift"):
            assert resolve_block_kind(_block(lang)) == KIND_BRIDGE, lang

    def test_lua_is_gen_config_kind(self):
        # lua 默认 role=gen-config（动态生成配置）→ kind=exec
        assert resolve_block_kind(_block("lua")) == KIND_EXEC

    def test_meta_kind_via_configs(self):
        assert resolve_block_kind(_block("json", directives={"configs": ""})) == KIND_META

    def test_role_override_kind(self):
        # toml 默认 static；role=data 覆盖仍为 static
        assert resolve_block_kind(_block("toml", directives={"role": "data"})) == KIND_STATIC


class TestRoleRouting:
    """resolve_block_role 语义角色推导。"""

    def test_default_roles(self):
        assert resolve_block_role(_block("toml")) == ROLE_DEPS
        assert resolve_block_role(_block("yaml")) == ROLE_RUNTIME
        assert resolve_block_role(_block("yml")) == ROLE_RUNTIME
        assert resolve_block_role(_block("ini")) == ROLE_LEGACY
        assert resolve_block_role(_block("lua")) == ROLE_GEN_CONFIG

    def test_configs_bare(self):
        assert resolve_block_role(_block("json", directives={"configs": ""})) == ROLE_ACTION_CONFIG

    def test_role_override(self):
        assert resolve_block_role(_block("toml", directives={"role": "legacy"})) == ROLE_LEGACY

    def test_unknown_lang_generic(self):
        assert resolve_block_role(_block("unknown-x")) == "generic"


# ═══════════════════════════════════════════════════════
# A5: 指令校验新增规则
# ═══════════════════════════════════════════════════════


class TestDirectiveValidationNew:
    """validate_directives 新增规则。"""

    def test_valid_role(self):
        assert validate_directives({"role": "deps"}, "toml") == []

    def test_invalid_role(self):
        errors = validate_directives({"role": "bogus"}, "toml")
        assert any("role" in e for e in errors)

    def test_configs_must_be_bare(self):
        errors = validate_directives({"configs": "x"}, "json")
        assert any("configs" in e for e in errors)

    def test_validate_values(self):
        assert validate_directives({"validate": "syntax"}, "json") == []
        assert validate_directives({"validate": "none"}, "json") == []
        errors = validate_directives({"validate": "bad"}, "json")
        assert any("validate" in e for e in errors)

    def test_schema_only_json_yaml(self):
        assert validate_directives({"schema": "s.json"}, "json") == []
        errors = validate_directives({"schema": "s.json"}, "toml")
        assert any("schema" in e for e in errors)

    def test_method_http_only(self):
        assert validate_directives({"method": "GET"}, "http") == []
        errors = validate_directives({"method": "GET"}, "mcp")
        assert any("method" in e for e in errors)

    def test_target_database_or_protocol(self):
        assert validate_directives({"target": "sqlite://./a.db"}, "sql") == []
        assert validate_directives({"target": "http://x"}, "http") == []
        errors = validate_directives({"target": "x"}, "toml")
        assert any("target" in e for e in errors)

    def test_on_error_values(self):
        assert validate_directives({"on_error": "skip"}, "python") == []
        errors = validate_directives({"on_error": "bad"}, "python")
        assert any("on_error" in e for e in errors)


# ═══════════════════════════════════════════════════════
# B1: static 配置块（toml deps / yaml runtime / ini legacy）
# ═══════════════════════════════════════════════════════


class TestStaticConfigBlocks:
    """static kind 配置块写文件 + 语法校验。"""

    def test_toml_deps_writes_file(self, tmp_path):
        content = '[deps]\nnim = "0.9.0"\nrust = "1.70"\n'
        block = _block("toml", content, index=1)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "config", "deps", "block_1.toml")
        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            text = f.read()
        assert "nim" in text and "rust" in text
        assert stdout == f"[static] block 1 (toml) -> artifacts/config/deps/block_1.toml"

    def test_toml_invalid_syntax(self, tmp_path):
        block = _block("toml", "[deps\nnim = ", index=1)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 1
        assert "TOML" in stderr or "toml" in stderr

    def test_yaml_runtime_writes_file(self, tmp_path):
        content = "language: nim\ncompiler: nim\nbuild_options: -d:release\n"
        block = _block("yaml", content, index=2)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "config", "runtime", "block_2.yaml")
        assert os.path.exists(out_path)

    def test_yaml_invalid_syntax(self, tmp_path):
        # 依赖 PyYAML；若未装则跳过语法校验（rc=0）
        block = _block("yaml", "a: [b, c", index=2)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        if rc == 1:
            assert "YAML" in stderr
        else:
            # PyYAML 未装，降级仅写文件
            assert rc == 0

    def test_ini_legacy_writes_file(self, tmp_path):
        content = "[server]\nhost = localhost\nport = 8080\n"
        block = _block("ini", content, index=3)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "config", "legacy", "block_3.ini")
        assert os.path.exists(out_path)

    def test_json_static_writes_file(self, tmp_path):
        content = json.dumps({"name": "vools", "version": "0.8.0"})
        block = _block("json", content, index=4)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "static", "block_4.json")
        assert os.path.exists(out_path)

    def test_validate_none_skips_syntax(self, tmp_path):
        # 即使语法错误，validate=none 也应放行
        block = _block("json", "{bad json", {"validate": "none"}, index=5)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr


# ═══════════════════════════════════════════════════════
# B3: #!configs action-config 块
# ═══════════════════════════════════════════════════════


class TestActionConfigBlock:
    """#!configs 裸指令 → meta kind。"""

    def test_configs_parse_ok(self, tmp_path):
        content = json.dumps({"id": "actus.test.foo", "name": "Foo", "deps": []})
        block = _block("json", content, {"configs": ""}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        assert "parsed ok" in stdout
        assert "actus.test.foo" not in stdout  # 内容不进入输出

    def test_configs_invalid_json(self, tmp_path):
        block = _block("json", "{bad json", {"configs": ""}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 1
        assert "无效 JSON" in stderr


# ═══════════════════════════════════════════════════════
# B5: sqlite 块
# ═══════════════════════════════════════════════════════


class TestSqliteBlock:
    """sqlite 块（stdlib sqlite3）。"""

    def test_sqlite_select(self, tmp_path):
        db = os.path.join(str(tmp_path), "test.db")
        target = f"sqlite://{db}"
        content = "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, name TEXT);\nINSERT INTO t (name) VALUES ('a'), ('b');\nSELECT * FROM t;"
        block = _block("sql", content, {"target": target}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        assert "id" in stdout
        assert "a" in stdout

    def test_sqlite_out_csv(self, tmp_path):
        db = os.path.join(str(tmp_path), "test.db")
        target = f"sqlite://{db}"
        content = "CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT);\nINSERT INTO t (name) VALUES ('x');\nSELECT * FROM t;"
        out_csv = os.path.join(str(tmp_path), "result.csv")
        block = _block("sql", content, {"target": target, "out": out_csv}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        assert os.path.exists(out_csv)
        with open(out_csv, "r", encoding="utf-8") as f:
            assert "id" in f.read()

    def test_sqlite_missing_target(self, tmp_path):
        block = _block("sql", "SELECT 1;", {}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 1
        assert "target" in stderr

    def test_sqlite_syntax_error(self, tmp_path):
        db = os.path.join(str(tmp_path), "test.db")
        target = f"sqlite://{db}"
        block = _block("sql", "SELECT * FROM nope;", {"target": target}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 1
        assert "sqlite" in stderr


# ═══════════════════════════════════════════════════════
# B4: http 块
# ═══════════════════════════════════════════════════════


class _EchoHandler(BaseHTTPRequestHandler):
    """本地测试 HTTP server：回显 method/path/body。"""

    def do_GET(self):
        body = json.dumps({"method": "GET", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(length).decode("utf-8", errors="replace")
        body = json.dumps({"method": "POST", "path": self.path, "body": req_body}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):
        pass  # 静默


@pytest.fixture()
def http_server():
    """启动本地测试服务器，yield (host, port, url_prefix)。"""
    server = HTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=3)


class TestHttpBlock:
    """http 块（stdlib urllib）。"""

    def test_http_get(self, tmp_path, http_server):
        url = f"{http_server}/api/users"
        block = _block("http", "", {"target": url, "method": "GET"}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        data = json.loads(stdout)
        assert data["method"] == "GET"
        assert data["path"] == "/api/users"

    def test_http_post_body(self, tmp_path, http_server):
        url = f"{http_server}/api/users"
        body = json.dumps({"name": "张三"}, ensure_ascii=False)
        block = _block("http", body, {"target": url, "method": "POST"}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        data = json.loads(stdout)
        assert data["method"] == "POST"
        assert "张三" in data["body"]

    def test_http_missing_target(self, tmp_path):
        block = _block("http", "", {}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 1
        assert "target" in stderr

    def test_http_network_error(self, tmp_path):
        # 未监听端口 → 网络错误
        block = _block("http", "", {"target": "http://127.0.0.1:1/x"}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc != 0
        assert "网络错误" in stderr or "请求异常" in stderr


# ═══════════════════════════════════════════════════════
# B2: lua gen-config 块（无 lua 时降级不崩溃）
# ═══════════════════════════════════════════════════════


class TestLuaGenConfig:
    """lua gen-config 块：尝试执行，失败降级报错。"""

    def test_lua_block_when_lua_missing(self, tmp_path):
        # 无 lua 编译器时 rc != 0，stderr 提示
        block = _block("lua", "return { name = 'x' }", {}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        # 若 lua 可用则 rc=0（本机很可能无 lua，允许 rc=1）
        if rc == 1:
            assert "lua" in stderr.lower() or "不可用" in stderr


# ═══════════════════════════════════════════════════════
# C1/C2/C3/C4: P1 阶段块（图表 / 数学 / 构建 / 模板）
# ═══════════════════════════════════════════════════════


class TestP1StaticBlocks:
    """P1 阶段静态块：图表 / 数学 / 构建 / 模板语言。

    这些语言 bridge helper 已注册但编译器未装（is_available=False），
    所以走 static kind（只写产物文件）。
    """

    # ── C1: 图表 ──

    def test_mermaid_block(self, tmp_path):
        content = "graph TD;\n  A-->B;"
        block = _block("mermaid", content, {}, index=1)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "diagram", "block_1.mmd")
        assert os.path.exists(out_path)
        # static 块 stdout 只含产物路径，不含内容
        assert "artifacts/diagram/block_1.mmd" in stdout

    def test_plantuml_block(self, tmp_path):
        content = "@startuml\nAlice -> Bob\n@enduml"
        block = _block("plantuml", content, {}, index=2)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "diagram", "block_2.puml")
        assert os.path.exists(out_path)

    def test_dot_block(self, tmp_path):
        content = 'digraph G { a -> b }'
        block = _block("dot", content, {}, index=3)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "diagram", "block_3.dot")
        assert os.path.exists(out_path)

    # ── C2: 数学 ──

    def test_latex_block(self, tmp_path):
        content = r"\begin{equation}E = mc^2\end{equation}"
        block = _block("latex", content, {}, index=4)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "math", "block_4.tex")
        assert os.path.exists(out_path)

    def test_math_block(self, tmp_path):
        content = r"\frac{1}{2}"
        block = _block("math", content, {}, index=5)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr

    # ── C3: 构建 / 基础设施 ──

    def test_dockerfile_block(self, tmp_path):
        content = "FROM python:3.11\nRUN pip install vools"
        block = _block("dockerfile", content, {}, index=6)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "build", "block_6.Dockerfile")
        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            assert "FROM" in f.read()

    def test_docker_compose_block(self, tmp_path):
        content = "services:\n  app:\n    image: python:3.11"
        block = _block("docker-compose", content, {}, index=7)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "build", "block_7.yml")
        assert os.path.exists(out_path)

    def test_nginx_block(self, tmp_path):
        content = "server {\n  listen 80;\n}"
        block = _block("nginx", content, {}, index=8)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "build", "block_8.conf")
        assert os.path.exists(out_path)

    def test_makefile_block(self, tmp_path):
        # 不执行 make（无 target 指令时纯写文件 rc=0）
        content = "all:\n\techo hi"
        block = _block("makefile", content, {}, index=9)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "build", "block_9Makefile")
        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            assert "all:" in f.read()

    # ── C4: 模板语言 ──

    def test_jinja_block(self, tmp_path):
        content = "Hello {{ name }}!"
        block = _block("jinja", content, {}, index=10)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "templates", "block_10.j2")
        assert os.path.exists(out_path)

    def test_handlebars_block(self, tmp_path):
        content = "{{#if user}}{{user.name}}{{/if}}"
        block = _block("handlebars", content, {}, index=11)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "templates", "block_11.hbs")
        assert os.path.exists(out_path)

    def test_pug_block(self, tmp_path):
        content = "h1 Hello"
        block = _block("pug", content, {}, index=12)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        out_path = os.path.join(str(tmp_path), "artifacts", "templates", "block_12.pug")
        assert os.path.exists(out_path)

    def test_mako_block(self, tmp_path):
        content = "${name}"
        block = _block("mako", content, {}, index=13)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr

    def test_ejs_block(self, tmp_path):
        content = "<%= name %>"
        block = _block("ejs", content, {}, index=14)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


