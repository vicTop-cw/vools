# -*- coding: utf-8 -*-
"""cli.py 契约测试（第 71 轮）。

覆盖：_out/_out_result 状态映射、_ensure_utf8_stdout 回退、main() 入口
（无子命令/异常映射/mcp 分发）、_build_parser 全子命令 smoke、_parse_params、
_ambiguous_error/_resolve_cli_target、_vis_config_dir、bug 分发（_bug_project_dir/
_bug_rows/_dispatch_bug）、密钥合并、triggers/execute 分发、dialog/evolve。

隔离：ACTUS_META_DIR / ACTUS_REPO_ROOT / HOME 指 tmp。
产品代码零改动。
"""
import _ai_local_bootstrap  # noqa: F401  必须先于 vools.actus 导入（套件约定）

import argparse
import importlib
import json
import os
import sys
import types

import pytest

import vools.actus.cli as cli_mod


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    meta = tmp_path / "_meta"
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    for p in (meta, repo, home):
        p.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("ACTUS_CONFIG_DIR", raising=False)
    yield


NS = argparse.Namespace


# ── _out / _out_result ────────────────────────────────────────────────

class TestOut:
    def test_out_prints_json(self, capsys):
        cli_mod._out({"a": "中文"})
        data = json.loads(capsys.readouterr().out)
        assert data == {"a": "中文"}

    def test_out_result_ok(self, capsys):
        rc = cli_mod._out_result({"status": "ok", "x": 1})
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "ok"
        assert data["data"]["x"] == 1

    def test_out_result_failed_with_hint(self, capsys):
        rc = cli_mod._out_result(
            {"status": "failed", "message": "坏了"})
        assert rc == 1
        captured = capsys.readouterr()
        assert "坏了" in captured.err
        data = json.loads(captured.out)
        assert data["status"] == "failed"

    def test_out_result_unknown_status_is_failure(self, capsys):
        rc = cli_mod._out_result({"status": "awaiting_confirmation"})
        assert rc == 1

    def test_out_result_status_field_none_always_ok(self, capsys):
        rc = cli_mod._out_result({"status": "whatever"}, status_field=None)
        assert rc == 0

    def test_out_result_non_dict_is_failure(self):
        assert cli_mod._out_result([1, 2]) == 1

    def test_out_result_validation_valid(self, capsys):
        assert cli_mod._out_result({"validation": {"valid": True}}) == 0
        assert cli_mod._out_result({"validation": {"valid": False}}) == 1

    def test_out_result_no_status_no_validation_is_ok(self):
        assert cli_mod._out_result({"data": 1}) == 0

    def test_out_result_warnings_passthrough(self, capsys):
        rc = cli_mod._out_result({"status": "ok"}, warnings=["runtime:x"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["warnings"] == ["runtime:x"]

    def test_out_result_failed_no_message_no_stderr(self, capsys):
        rc = cli_mod._out_result({"status": "failed"})
        captured = capsys.readouterr()
        assert rc == 1
        assert captured.err == ""


# ── _ensure_utf8_stdout ───────────────────────────────────────────────

class TestEnsureUtf8:
    def test_reconfigure_ok(self, capsys):
        cli_mod._ensure_utf8_stdout()  # 正常路径不抛

    def test_fallback_wrapper(self, monkeypatch):
        import io as _io

        class NoReconf:
            def __init__(self):
                self.buffer = _io.BytesIO()

        fake_out, fake_err = NoReconf(), NoReconf()
        monkeypatch.setattr(sys, "stdout", fake_out, raising=False)
        monkeypatch.setattr(sys, "stderr", fake_err, raising=False)
        cli_mod._ensure_utf8_stdout()
        # 退化为 TextIOWrapper 包 buffer
        assert isinstance(sys.stdout, _io.TextIOWrapper)

    def test_double_failure_silent(self, monkeypatch):
        class Bad:
            buffer = property(lambda self: (_ for _ in ()).throw(
                RuntimeError("no buffer")))

        monkeypatch.setattr(sys, "stdout", Bad(), raising=False)
        monkeypatch.setattr(sys, "stderr", Bad(), raising=False)
        cli_mod._ensure_utf8_stdout()  # 不抛


# ── main() ────────────────────────────────────────────────────────────

class TestMain:
    def test_no_command_prints_help_returns_2(self, capsys):
        rc = cli_mod.main([])
        assert rc == 2
        assert "usage" in capsys.readouterr().out.lower()

    def test_version_exits_zero(self):
        with pytest.raises(SystemExit) as ei:
            cli_mod.main(["--version"])
        assert ei.value.code == 0

    def test_valueerror_maps_param_invalid(self, monkeypatch, capsys):
        def boom(args):
            raise ValueError("非法参数")

        monkeypatch.setattr(cli_mod, "_dispatch", boom)
        rc = cli_mod.main(["list"])
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["error"]["code"] == "param_invalid"
        assert "非法参数" in data["error"]["message"]

    def test_exception_uses_code_attr(self, monkeypatch, capsys):
        class Err(Exception):
            code = "custom_code"

        def boom(args):
            raise Err("内部炸了")

        monkeypatch.setattr(cli_mod, "_dispatch", boom)
        rc = cli_mod.main(["list"])
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["error"]["code"] == "custom_code"

    def test_exception_without_code_is_internal(self, monkeypatch, capsys):
        def boom(args):
            raise RuntimeError("无名错")

        monkeypatch.setattr(cli_mod, "_dispatch", boom)
        rc = cli_mod.main(["list"])
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["error"]["code"] == "internal"

    def test_mcp_sse_dispatch(self, monkeypatch):
        calls = {}

        fake_sse = types.ModuleType("vools.actus.mcp_sse")

        def serve_sse(port=None):
            calls["sse_port"] = port

        fake_sse.serve_sse = serve_sse
        monkeypatch.setitem(sys.modules, "vools.actus.mcp_sse", fake_sse)
        rc = cli_mod.main(["mcp", "--transport", "sse", "--port", "9999"])
        assert rc == 0
        assert calls["sse_port"] == 9999

    def test_mcp_stdio_dispatch(self, monkeypatch):
        calls = {}
        fake_srv = types.ModuleType("vools.actus.mcp_server")

        def _serve():
            calls["stdio"] = True

        fake_srv.serve = _serve
        monkeypatch.setitem(sys.modules, "vools.actus.mcp_server", fake_srv)
        rc = cli_mod.main(["mcp"])
        assert rc == 0
        assert calls["stdio"] is True

    def test_dispatch_rc_passthrough(self, monkeypatch):
        monkeypatch.setattr(cli_mod, "_dispatch", lambda args: 5)
        assert cli_mod.main(["list"]) == 5


# ── parser smoke ──────────────────────────────────────────────────────

class TestParserSmoke:
    @pytest.fixture(scope="class")
    def parser(self):
        return cli_mod._build_parser()

    @pytest.mark.parametrize("argv,command", [
        (["scan"], "scan"),
        (["list"], "list"),
        (["list", "--all"], "list"),
        (["list", "--kind", "exec", "--tag", "a,b"], "list"),
        (["validate", "a.b"], "validate"),
        (["info", "a.b"], "info"),
        (["preview", "a.b", "--html"], "preview"),
        (["run", "a.b", "--yes"], "run"),
        (["run", "a.b", "--allow-host", "x.dev"], "run"),
        (["status", "e1"], "status"),
        (["bug", "list"], "bug"),
        (["bug", "report", "sum"], "bug"),
        (["bug", "stats", "--json"], "bug"),
        (["reg", "list"], "reg"),
        (["team", "list"], "team"),
        (["private", "list"], "private"),
        (["visibility", "get", "a.b"], "visibility"),
        (["registry", "build"], "registry"),
        (["install", "https://x.dev/a/b.git"], "install"),
        (["uninstall", "--name", "b"], "uninstall"),
        (["publish"], "publish"),
        (["search", "kw"], "search"),
        (["sync"], "sync"),
        (["rollback", "--name", "b", "--version", "1"], "rollback"),
        (["check-update", "--name", "b"], "check-update"),
        (["keygen"], "keygen"),
        (["sign", "."], "sign"),
        (["verify", "."], "verify"),
        (["approve", "req1"], "approve"),
        (["pending"], "pending"),
        (["dialog", "alert"], "dialog"),
        (["evolve", "desc"], "evolve"),
        (["webhook", "--status"], "webhook"),
        (["project", "export"], "project"),
        (["omega", "template", "a.b", "--example", "{}"], "omega"),
        (["concurrency", "status"], "concurrency"),
        (["deps", "a.b"], "deps"),
        (["desktop"], "desktop"),
        (["events"], "events"),
        (["viz"], "viz"),
        (["replay", "--run-id", "r1"], "replay"),
        (["notify", "stats"], "notify"),
        (["export"], "export"),
        (["probe"], "probe"),
        (["cost"], "cost"),
        (["selfdrive", "status"], "selfdrive"),
        (["health"], "health"),
        (["selfheal", "patterns"], "selfheal"),
        (["template", "list"], "template"),
        (["execute", "--language", "python", "--code", "1"], "execute"),
        (["triggers", "list"], "triggers"),
        (["vault", "list"], "vault"),
        (["dep-tree", "a.b"], "dep-tree"),
        (["list-installed"], "list-installed"),
        (["config", "claude"], "config"),
        (["runtimes"], "runtimes"),
        (["project-mgmt", "--status"], "project-mgmt"),
        (["loop", "list"], "loop"),
        (["registry", "info"], "registry"),
        (["private", "add", "a.b"], "private"),
        (["team", "list"], "team"),
        (["reg", "add", "n", "https://x"], "reg"),
        (["mcp"], "mcp"),
    ])
    def test_parse(self, parser, argv, command):
        args = parser.parse_args(argv)
        assert getattr(args, "command", None) == command


# ── _parse_params / _ambiguous_error ─────────────────────────────────

class TestParseParams:
    def test_empty(self):
        assert cli_mod._parse_params("") == {}
        assert cli_mod._parse_params("{}") == {}

    def test_bad_json(self):
        with pytest.raises(ValueError):
            cli_mod._parse_params("{bad")

    def test_non_dict(self):
        with pytest.raises(ValueError):
            cli_mod._parse_params("[1,2]")

    def test_ok(self):
        assert cli_mod._parse_params('{"a": 1}') == {"a": 1}


class TestAmbiguousError:
    def test_shape(self):
        err = cli_mod._ambiguous_error("dup", ["a.b", "c.d"])
        assert err["code"] == "ambiguous"
        assert err["details"]["candidates"] == ["a.b", "c.d"]

    def test_none_candidates(self):
        err = cli_mod._ambiguous_error("x", None)
        assert err["details"]["candidates"] == []


# ── _resolve_cli_target ───────────────────────────────────────────────

class TestResolveCliTarget:
    def _fake_resolver(self, monkeypatch, fn):
        fake = types.ModuleType("vools.actus.resolver")
        fake.resolve_target = fn
        monkeypatch.setitem(sys.modules, "vools.actus.resolver", fake)

    def test_exception_ambiguous_details_ambiguous(self, monkeypatch):
        class Exc(Exception):
            code = "action_ambiguous"
            details = {"ambiguous": ["x.a", "x.b"]}

        self._fake_resolver(monkeypatch,
                            lambda *a, **k: (_ for _ in ()).throw(Exc("amb")))
        kind, err = cli_mod._resolve_cli_target("x")
        assert kind == "error"
        assert err["details"]["candidates"] == ["x.a", "x.b"]

    def test_exception_ambiguous_details_candidates(self, monkeypatch):
        class Exc(Exception):
            code = "ambiguous"
            details = {"candidates": ["x.a"]}

        self._fake_resolver(monkeypatch,
                            lambda *a, **k: (_ for _ in ()).throw(Exc("amb")))
        kind, err = cli_mod._resolve_cli_target("x")
        assert err["details"]["candidates"] == ["x.a"]

    def test_exception_other_code_passthrough(self, monkeypatch):
        class Exc(Exception):
            code = "not_found"
            details = {"hint": 1}

        self._fake_resolver(monkeypatch,
                            lambda *a, **k: (_ for _ in ()).throw(Exc("nf")))
        kind, err = cli_mod._resolve_cli_target("x")
        assert err == {"code": "not_found", "message": "nf",
                       "details": {"hint": 1}}

    def test_exception_no_details(self, monkeypatch):
        self._fake_resolver(
            monkeypatch,
            lambda *a, **k: (_ for _ in ()).throw(ValueError("v")))
        kind, err = cli_mod._resolve_cli_target("x")
        assert err["code"] == "param_invalid"

    def test_url_rejected(self, monkeypatch):
        r = types.SimpleNamespace(ambiguous=None, source="url",
                                  url="https://x", sha256="ab",
                                  digest_verified=False, path=None,
                                  action_id=None)
        self._fake_resolver(monkeypatch, lambda *a, **k: r)
        kind, err = cli_mod._resolve_cli_target("https://x")
        assert err["code"] == "param_invalid"

    def test_ambiguous_result(self, monkeypatch):
        r = types.SimpleNamespace(ambiguous=["a", "b"], source="id",
                                  path=None, action_id=None)
        self._fake_resolver(monkeypatch, lambda *a, **k: r)
        kind, err = cli_mod._resolve_cli_target("x")
        assert err["details"]["candidates"] == ["a", "b"]

    def test_id_passthrough(self, monkeypatch):
        r = types.SimpleNamespace(ambiguous=None, source="id",
                                  path=None, action_id="a.b")
        self._fake_resolver(monkeypatch, lambda *a, **k: r)
        assert cli_mod._resolve_cli_target("x") == ("id", "a.b")

    def test_id_fallback_raw(self, monkeypatch):
        r = types.SimpleNamespace(ambiguous=None, source="id",
                                  path=None, action_id=None)
        self._fake_resolver(monkeypatch, lambda *a, **k: r)
        assert cli_mod._resolve_cli_target("raw") == ("id", "raw")

    def test_path_resolves_scattered(self, monkeypatch, tmp_path):
        p = tmp_path / "demo.actus.md"
        p.write_text("---\nid: demo.x\nname: Demo\nversion: 1.0.0\ntrust: audit\nentry: demo\n---\n# 执行\n", "utf-8")
        r = types.SimpleNamespace(ambiguous=None, source="path", path=str(p),
                                  action_id=None)
        self._fake_resolver(monkeypatch, lambda *a, **k: r)
        kind, action = cli_mod._resolve_cli_target(str(p))
        assert kind == "path"
        assert action.meta.get("id") == "demo.x"


# ── _vis_config_dir ───────────────────────────────────────────────────

class TestVisConfigDir:
    def test_default_none(self):
        assert cli_mod._vis_config_dir() is None

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ACTUS_CONFIG_DIR", "D:/cfg")
        assert cli_mod._vis_config_dir() == "D:/cfg"


# ── bug 分发 ──────────────────────────────────────────────────────────

class TestBugHelpers:
    def test_bug_project_dir_none(self):
        assert cli_mod._bug_project_dir("") is None
        assert cli_mod._bug_project_dir(None) is None

    def test_bug_project_dir_absolute(self, tmp_path):
        raw = str(tmp_path / "proj")
        out = cli_mod._bug_project_dir(raw)
        assert os.path.isabs(out)
        assert out.lower() == os.path.abspath(raw).lower()

    def test_bug_rows_filter(self, monkeypatch):
        rows = [{"status": "OPEN", "severity": "high"},
                {"status": "FIXED", "severity": "low"},
                {"status": "open", "severity": "HIGH"}]

        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        fake_br.report_bug = lambda *a, **k: {}
        fake_br.bug_list = lambda project_dir=None: rows
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        assert len(cli_mod._bug_rows(None, status="open")) == 2
        assert len(cli_mod._bug_rows(None, severity="HIGH")) == 2
        assert len(cli_mod._bug_rows(None)) == 3


class TestDispatchBug:
    def _args(self, **kw):
        base = dict(bug_command=None, project_dir=None, status=None,
                    severity=None, as_json=False, summary=None, detail=None,
                    severity2=None, ref_call_id=None, reported_by=None,
                    source=None)
        base.update(kw)
        return NS(**base)

    def test_no_command_usage(self, capsys):
        assert cli_mod._dispatch_bug(self._args()) == 2
        assert "用法" in capsys.readouterr().err

    def test_list_empty_human(self, monkeypatch, capsys):
        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        fake_br.report_bug = lambda *a, **k: {}
        fake_br.bug_list = lambda project_dir=None: []
        fake_br.bugs_path = lambda pd: str(os.path.join("x", "bugs.md"))
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        rc = cli_mod._dispatch_bug(self._args(bug_command="list"))
        assert rc == 0
        assert "暂无" in capsys.readouterr().out

    def test_list_json(self, monkeypatch, capsys):
        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        fake_br.report_bug = lambda *a, **k: {}
        fake_br.bug_list = lambda project_dir=None: [
            {"id": "BUG-1", "status": "OPEN", "severity": "high",
             "summary": "s" * 100, "hits": 2, "seq": 1}]
        fake_br.bugs_path = lambda pd: "x" + os.sep + "bugs.md"
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        rc = cli_mod._dispatch_bug(
            self._args(bug_command="list", as_json=True))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 1
        assert "/" in data["path"]

    def test_list_human_table(self, monkeypatch, capsys):
        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        fake_br.report_bug = lambda *a, **k: {}
        fake_br.bug_list = lambda project_dir=None: [
            {"id": "BUG-1", "status": "OPEN", "severity": "high",
             "summary": "s", "hits": 1, "seq": 1}]
        fake_br.bugs_path = lambda pd: "bugs.md"
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        rc = cli_mod._dispatch_bug(self._args(bug_command="list"))
        assert rc == 0
        assert "共 1 条" in capsys.readouterr().out

    def test_stats_json(self, monkeypatch, capsys):
        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        fake_br.report_bug = lambda *a, **k: {}
        fake_br.bug_list = lambda project_dir=None: [
            {"status": "OPEN", "severity": "high"},
            {"status": "FIXED", "severity": "low"}]
        fake_br.bugs_path = lambda pd: "bugs.md"
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        rc = cli_mod._dispatch_bug(
            self._args(bug_command="stats", as_json=True))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["total"] == 2
        assert data["open"] == 1

    def test_report_error(self, monkeypatch, capsys):
        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        
        class BugreportError(Exception):
            pass

        def report_bug(*a, **k):
            raise BugreportError("bad summary")

        fake_br.BugreportError = BugreportError
        fake_br.report_bug = report_bug
        fake_br.bug_list = lambda project_dir=None: []
        fake_br.bugs_path = lambda pd: "bugs.md"
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        rc = cli_mod._dispatch_bug(
            self._args(bug_command="report", summary="s"))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["error"]["code"] == "param_invalid"

    def test_report_ok_json(self, monkeypatch, capsys):
        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        
        class BugreportError(Exception):
            pass

        fake_br.BugreportError = BugreportError

        def report_bug(*a, **k):
            return {"status": "OPEN", "id": "BUG-9",
                    "path": os.path.join("x", "bugs.md"),
                    "summary": "s", "severity": "high",
                    "duplicate": False}

        fake_br.report_bug = report_bug
        fake_br.bug_list = lambda project_dir=None: []
        fake_br.bugs_path = lambda pd: "bugs.md"
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        rc = cli_mod._dispatch_bug(
            self._args(bug_command="report", summary="s", as_json=True))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "ok"
        assert data["bug_status"] == "OPEN"
        assert "/" in data["path"]

    def test_report_ok_duplicate_human(self, monkeypatch, capsys):
        fake_br = types.ModuleType("vools.actus.bugreport")
        class BugreportError(Exception):
            pass
        fake_br.BugreportError = BugreportError
        
        class BugreportError(Exception):
            pass

        fake_br.BugreportError = BugreportError

        def report_bug(*a, **k):
            return {"status": "OPEN", "id": "BUG-9", "path": "bugs.md",
                    "summary": "s", "severity": "high", "duplicate": True,
                    "hits": 3}

        fake_br.report_bug = report_bug
        fake_br.bug_list = lambda project_dir=None: []
        fake_br.bugs_path = lambda pd: "bugs.md"
        monkeypatch.setitem(sys.modules, "vools.actus.bugreport", fake_br)
        rc = cli_mod._dispatch_bug(
            self._args(bug_command="report", summary="s"))
        assert rc == 0
        assert "已存在同键" in capsys.readouterr().out


# ── 密钥合并 ──────────────────────────────────────────────────────────

class TestSecretsMerged:
    def test_list_delegates(self, monkeypatch):
        seen = {}
        import vools.actus.vault as vault

        def fake_list(scope, meta_dir):
            seen.update(scope=scope, meta_dir=meta_dir)
            return {"names": []}

        monkeypatch.setattr(vault, "list_secret_names", fake_list)
        out = cli_mod._list_secrets_merged("md", None)
        assert out == {"names": []}
        assert seen["scope"] == "global"
        assert seen["meta_dir"] == "md"

    def test_delete_hint_injected(self, monkeypatch):
        import vools.actus.vault as vault

        def fake_delete(key, scope, meta_dir, include_v1=False, caller=None):
            return {"status": "ok", "hint": "原始提示"}

        monkeypatch.setattr(vault, "delete_secret", fake_delete)
        out = cli_mod._delete_secret_merged("md", "k", "s")
        assert "v2" in out["hint"]
        assert "include_v1" not in out

    def test_delete_no_hint(self, monkeypatch):
        import vools.actus.vault as vault
        monkeypatch.setattr(
            vault, "delete_secret",
            lambda *a, **k: {"status": "ok"})
        assert cli_mod._delete_secret_merged("md", "k", "s") == {"status": "ok"}


# ── triggers 分发 ─────────────────────────────────────────────────────

class TestDispatchTriggers:
    def _args(self, **kw):
        base = dict(triggers_command=None, type="file", expr=None,
                    path=None, events=None, recursive=False, key=None,
                    args=None, action_id="a.b")
        base.update(kw)
        return NS(**base)

    def test_add_ok(self, capsys):
        rc = cli_mod._dispatch_triggers(
            self._args(triggers_command="add", type="hotkey",
                       action_id="a.b", key="ctrl+1"))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "ok"

    def test_add_invalid(self):
        rc = cli_mod._dispatch_triggers(
            self._args(triggers_command="add", type="no_such_type",
                       action_id="a.b"))
        assert rc == 1

    def test_add_bad_args_json_silently_dropped(self, capsys):
        rc = cli_mod._dispatch_triggers(
            self._args(triggers_command="add", type="hotkey",
                       action_id="a.b", key="ctrl+1", args="{bad"))
        assert rc == 0  # JSON 坏 → args 字段静默缺省（现状）

    def test_list(self, capsys):
        rc = cli_mod._dispatch_triggers(
            self._args(triggers_command="list"))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "triggers" in data

    def test_status(self, capsys):
        rc = cli_mod._dispatch_triggers(
            self._args(triggers_command="status"))
        assert rc == 0

    def test_remove(self, capsys):
        rc = cli_mod._dispatch_triggers(
            self._args(triggers_command="remove", action_id="x"))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["removed"] == "x"

    def test_unknown_command(self):
        rc = cli_mod._dispatch_triggers(
            self._args(triggers_command="wat"))
        assert rc == 2


# ── execute 分发 ──────────────────────────────────────────────────────

class TestDispatchExecute:
    def _args(self, **kw):
        base = dict(code=None, file=None, language="python", args=None,
                    stdin=None, env=None)
        base.update(kw)
        return NS(**base)

    def test_missing_code(self, capsys):
        rc = cli_mod._dispatch_execute(self._args())
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["error"]["code"] == "missing_code"

    def test_unsupported_language(self, capsys):
        rc = cli_mod._dispatch_execute(
            self._args(code="x", language="nope"))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["error"]["code"] == "unsupported_language"

    def test_ok_python(self, capsys):
        rc = cli_mod._dispatch_execute(
            self._args(code="print('hi')"))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "hi" in data["stdout"]

    def test_file_source(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("print('from-file')", "utf-8")
        rc = cli_mod._dispatch_execute(
            self._args(file=str(f)))
        assert rc == 0
        assert "from-file" in json.loads(capsys.readouterr().out)["stdout"]

    def test_env_and_args_context(self, capsys):
        rc = cli_mod._dispatch_execute(
            self._args(code="import json,sys;print(json.dumps(sys.argv))",
                       args=["p1"], env='{"K": "V"}'))
        assert rc == 0

    def test_bad_env_json_dropped(self, capsys):
        rc = cli_mod._dispatch_execute(
            self._args(code="print('ok')", env="{bad"))
        assert rc == 0

    def test_execution_error(self, monkeypatch, capsys):
        import vools.actus.runtimes as rt
        monkeypatch.setattr(
            rt, "execute_block",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        monkeypatch.setattr(rt, "get_available_runtimes", lambda: ["python"])
        rc = cli_mod._dispatch_execute(self._args(code="x"))
        assert rc == 1
        data = json.loads(capsys.readouterr().out)
        assert data["error"]["code"] == "execution_error"

    def test_nonzero_exit_code_passthrough(self, capsys):
        rc = cli_mod._dispatch_execute(
            self._args(code="import sys; sys.exit(3)"))
        assert rc == 3


# ── dialog ────────────────────────────────────────────────────────────

class TestCmdDialog:
    def _args(self, **kw):
        base = dict(mode="info", title="t", message=None, options=None,
                    password=False, multiline=False, timeout=None,
                    fields=None)
        base.update(kw)
        return NS(**base)

    def test_exe_missing(self, monkeypatch, capsys):
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        rc = cli_mod._cmd_dialog(self._args())
        assert rc == 1
        assert "未编译" in capsys.readouterr().out

    def _fake_exe(self, monkeypatch, run_fn):
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        import subprocess as _sp
        fake_sp = types.ModuleType("subprocess")
        fake_sp.run = run_fn
        fake_sp.TimeoutExpired = _sp.TimeoutExpired
        monkeypatch.setitem(sys.modules, "subprocess", fake_sp)

    def test_ok_result(self, monkeypatch, capsys):
        proc = types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "value": "v"}),
            stderr="")
        self._fake_exe(
            monkeypatch, lambda *a, **k: proc)
        rc = cli_mod._cmd_dialog(self._args(message="m"))
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True

    def test_result_ok_false(self, monkeypatch, capsys):
        proc = types.SimpleNamespace(
            returncode=0, stdout=json.dumps({"ok": False}), stderr="")
        self._fake_exe(monkeypatch, lambda *a, **k: proc)
        assert cli_mod._cmd_dialog(self._args()) == 1

    def test_nonzero_rc(self, monkeypatch, capsys):
        proc = types.SimpleNamespace(returncode=2, stdout="", stderr="e")
        self._fake_exe(monkeypatch, lambda *a, **k: proc)
        rc = cli_mod._cmd_dialog(self._args())
        assert rc == 1
        assert "退出码 2" in capsys.readouterr().out

    def test_timeout(self, monkeypatch, capsys):
        import subprocess as sp

        def run(*a, **k):
            raise sp.TimeoutExpired(cmd="x", timeout=1)

        self._fake_exe(monkeypatch, run)
        assert cli_mod._cmd_dialog(self._args()) == 1
        assert "超时" in capsys.readouterr().out

    def test_bad_fields_json(self, monkeypatch, capsys):
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        rc = cli_mod._cmd_dialog(self._args(fields="{bad"))
        assert rc == 1
        assert "JSON" in capsys.readouterr().out

    def test_bad_output_json(self, monkeypatch, capsys):
        proc = types.SimpleNamespace(returncode=0, stdout="not-json",
                                     stderr="")
        self._fake_exe(monkeypatch, lambda *a, **k: proc)
        rc = cli_mod._cmd_dialog(self._args())
        assert rc == 1
        assert "无法解析" in capsys.readouterr().out

    def test_request_shape(self, monkeypatch, capsys):
        seen = {}

        def run(argv, **kw):
            seen["req"] = json.loads(argv[1])
            return types.SimpleNamespace(
                returncode=0, stdout=json.dumps({"ok": True}), stderr="")

        self._fake_exe(monkeypatch, run)
        cli_mod._cmd_dialog(self._args(
            message="m", options="a, b", password=True, multiline=True,
            timeout=10, fields='{"f": 1}'))
        req = seen["req"]
        assert req["message"] == "m"
        assert req["options"] == ["a", "b"]
        assert req["password"] is True
        assert req["multiline"] is True
        assert req["timeout"] == 10
        assert req["fields"] == {"f": 1}


# ── evolve ────────────────────────────────────────────────────────────

class _FakeEngine:
    def __init__(self, config=None):
        self.config = config

    def list_evolved_actions(self):
        return []

    def get_status(self, aid):
        return {"status": "ok"}

    def get_history(self, aid):
        return []

    def rollback(self, aid, version):
        return {"status": "ok", "version": version}

    def compare_versions(self, aid, v1, v2):
        return {"status": "ok"}

    def repair(self, aid, expect=None):
        return {"status": "ok"}

    def evolve(self, desc, action_id=None, expect=None):
        return {"status": "ok", "action_id": "x", "rounds": 1,
                "history": [{"round_num": 1, "phase": "generate",
                             "status": "pass", "message": "m"}]}


def _install_fake_evolution(monkeypatch, engine_cls=_FakeEngine):
    fake_evo = types.ModuleType("vools.actus.evolution")
    fake_evo.EvolutionEngine = engine_cls
    fake_evo.EvolutionConfig = lambda **kw: types.SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules, "vools.actus.evolution", fake_evo)


class TestCmdEvolve:
    def _args(self, **kw):
        base = dict(list=None, status=None, history=None, rollback=None,
                    compare=None, v1=None, v2=None, version=None,
                    repair=None, description=None, action_id=None,
                    expect=None, max_rounds=3)
        base.update(kw)
        return NS(**base)

    def test_list_empty(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args(list=True))
        assert rc == 0
        assert "没有进化记录" in capsys.readouterr().out

    def test_list_nonempty(self, monkeypatch, capsys):
        class E(_FakeEngine):
            def list_evolved_actions(self):
                return ["a.b"]

        _install_fake_evolution(monkeypatch, E)
        rc = cli_mod._cmd_evolve(self._args(list=True))
        assert rc == 0
        assert "a.b" in capsys.readouterr().out

    def test_status(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args(status="a.b"))
        assert rc == 0

    def test_history_empty(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args(history="a.b"))
        assert rc == 0
        assert "无进化历史" in capsys.readouterr().out

    def test_history_nonempty(self, monkeypatch, capsys):
        class E(_FakeEngine):
            def get_history(self, aid):
                return [{"round_num": 1, "phase": "generate",
                         "status": "pass", "message": "m"}]

        _install_fake_evolution(monkeypatch, E)
        rc = cli_mod._cmd_evolve(self._args(history="a.b"))
        assert rc == 0

    def test_rollback_needs_version(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args(rollback="a.b"))
        assert rc == 1
        assert "--version" in capsys.readouterr().out

    def test_rollback_ok(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(
            self._args(rollback="a.b", version=2))
        assert rc == 0

    def test_compare_needs_versions(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args(compare="a.b"))
        assert rc == 1
        assert "--v1" in capsys.readouterr().out

    def test_repair_needs_action_id(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args(repair=True))
        assert rc == 1
        assert "--action-id" in capsys.readouterr().out

    def test_repair_ok(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(
            self._args(repair=True, action_id="a.b", expect='{"k": 1}'))
        assert rc == 0

    def test_needs_description(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args())
        assert rc == 1
        assert "描述" in capsys.readouterr().out

    def test_evolve_ok(self, monkeypatch, capsys):
        _install_fake_evolution(monkeypatch)
        rc = cli_mod._cmd_evolve(self._args(description="做一个东西"))
        assert rc == 0
        assert "ok" in capsys.readouterr().out

    def test_evolve_failed(self, monkeypatch, capsys):
        class E(_FakeEngine):
            def evolve(self, desc, action_id=None, expect=None):
                return {"status": "failed", "reason": "no"}

        _install_fake_evolution(monkeypatch, E)
        rc = cli_mod._cmd_evolve(self._args(description="x"))
        assert rc == 1


class TestParseExpect:
    def test_empty(self):
        assert cli_mod._parse_expect("") == {}

    def test_ok(self):
        assert cli_mod._parse_expect('{"a": 1}') == {"a": 1}

    def test_bad_json(self):
        assert cli_mod._parse_expect("{bad") == {}
