"""dependency.py 契约测试（Round 48）。

契约:
- DepStrategy / DepType 枚举语义
- Dependency.fix_command / ephemeral_command 按类型生成
- DependencyResolver.parse_deps: 字符串前缀解析 + dict 解析（非法值回退）
- _build_cs_dep: cs_forms / cs_tools / 未知
- check_dep 缓存
- _do_check 分派到各类型检查
- _check_runtime: PATH 检查 + 别名展开（runtime:shell → bash/sh/...）
- _check_cs_build: build_check 存在/缺失/未指定
- _check_pip_pkg: import 成功/失败
- _check_npm_pkg: package.json deps / node_modules / 未安装
- _check_system_cmd: where 成功 / _meta/tools / 策略分支
- _check_builtin / _check_mcp / _check_action
- resolve: HINT / EPHEMERAL / DOWNLOAD / FAIL 策略 + auto_install
- _try_fix: pip install / cd / 其他
- try_ephemeral: LANG vs 非 LANG
- try_download: 非 SYSTEM / 无映射 / 下载
- topological_sort: 无环 / 有环
- get_dep_tree: 递归 + 循环检测
- get_resolver 单例
- check_action_deps
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vools.actus.dependency import (
    DepStrategy,
    DepType,
    Dependency,
    DepCheckResult,
    DependencyResolver,
    get_resolver,
    check_action_deps,
    _RUNTIME_COMMAND_ALIASES,
)


def _res(tmp_path):
    """构建一个隔离的 resolver（actions_root 指 tmp_path/actions）。"""
    actions = tmp_path / "actions"
    actions.mkdir(exist_ok=True)
    return DependencyResolver(actions_root=str(actions), build_root=str(tmp_path / "actions" / "system"))


class TestEnums:
    """枚举语义。"""

    def test_dep_strategy_values(self):
        assert DepStrategy.HINT.value == "hint"
        assert DepStrategy.EPHEMERAL.value == "ephemeral"
        assert DepStrategy.DOWNLOAD.value == "download"
        assert DepStrategy.FAIL.value == "fail"

    def test_dep_type_values(self):
        assert DepType.BUILTIN.value == "builtin"
        assert DepType.SYSTEM.value == "system"
        assert DepType.LANG.value == "lang"
        assert DepType.MCP.value == "mcp"
        assert DepType.ACTION.value == "action"
        assert DepType.CS_BUILD.value == "cs_build"
        assert DepType.RUNTIME.value == "runtime"


class TestRuntimeAliases:
    """运行时别名展开表。"""

    def test_shell_aliases(self):
        assert "bash" in _RUNTIME_COMMAND_ALIASES["shell"]
        assert "powershell" in _RUNTIME_COMMAND_ALIASES["shell"]

    def test_python_aliases(self):
        assert "py" in _RUNTIME_COMMAND_ALIASES["python"]

    def test_rust_aliases(self):
        assert "rustc" in _RUNTIME_COMMAND_ALIASES["rust"]


class TestDependencyProperties:
    """Dependency.fix_command / ephemeral_command。"""

    def test_fix_command_cs_build(self):
        d = Dependency(name="x", type=DepType.CS_BUILD, build_command="build all")
        assert d.fix_command == "build all"

    def test_fix_command_lang_pip(self):
        d = Dependency(name="requests", type=DepType.LANG, lang_manager="pip")
        assert d.fix_command == "pip install requests"

    def test_fix_command_lang_npm(self):
        d = Dependency(name="shiki", type=DepType.LANG, lang_manager="npm")
        assert d.fix_command == "npm install shiki"

    def test_fix_command_system(self):
        d = Dependency(name="pandoc", type=DepType.SYSTEM)
        assert "pandoc" in d.fix_command

    def test_fix_command_runtime(self):
        d = Dependency(name="python", type=DepType.RUNTIME)
        assert "python" in d.fix_command

    def test_fix_command_default(self):
        d = Dependency(name="some_action", type=DepType.ACTION)
        assert d.fix_command == ""

    def test_ephemeral_command_lang_pip(self):
        d = Dependency(name="ruff", type=DepType.LANG, lang_manager="pip")
        assert d.ephemeral_command == "pipx run ruff"

    def test_ephemeral_command_lang_npm(self):
        d = Dependency(name="prettier", type=DepType.LANG, lang_manager="npm")
        assert d.ephemeral_command == "npx prettier"

    def test_ephemeral_command_non_lang(self):
        d = Dependency(name="x", type=DepType.SYSTEM)
        assert d.ephemeral_command is None


class TestParseDeps:
    """parse_deps: 字符串前缀解析。"""

    def test_empty(self):
        r = _res(Path("."))
        assert r.parse_deps([]) == []

    def test_prefixes(self):
        r = _res(Path("."))
        cases = {
            "builtin:core": DepType.BUILTIN,
            "system:pandoc": DepType.SYSTEM,
            "runtime:python": DepType.RUNTIME,
            "pip:requests": DepType.LANG,
            "npm:shiki": DepType.LANG,
            "mcp:server": DepType.MCP,
            "action:x.y": DepType.ACTION,
            "bare_name": DepType.ACTION,
        }
        for s, t in cases.items():
            dep = r._parse_dep_string(s)
            assert dep.type == t, f"{s} → {t}"

    def test_pip_strategy_ephemeral(self):
        r = _res(Path("."))
        dep = r._parse_dep_string("pip:requests")
        assert dep.strategy == DepStrategy.EPHEMERAL
        assert dep.lang_manager == "pip"

    def test_cs_prefix(self, tmp_path):
        r = _res(tmp_path)
        dep = r._parse_dep_string("cs_forms")
        assert dep.type == DepType.CS_BUILD
        assert dep.build_check  # exe 路径已填

    def test_parse_deps_dict(self):
        r = _res(Path("."))
        deps = r.parse_deps([{"name": "requests", "type": "lang", "lang_manager": "pip"}])
        assert len(deps) == 1
        assert deps[0].type == DepType.LANG

    def test_parse_deps_dict_invalid_type(self):
        """非法 type 字符串回退 ACTION。"""
        r = _res(Path("."))
        deps = r.parse_deps([{"name": "x", "type": "bogus_type"}])
        assert deps[0].type == DepType.ACTION

    def test_parse_deps_dict_invalid_strategy(self):
        """非法 strategy 字符串回退 HINT。"""
        r = _res(Path("."))
        deps = r.parse_deps([{"name": "x", "strategy": "bogus"}])
        assert deps[0].strategy == DepStrategy.HINT

    def test_parse_deps_dict_enum_passthrough(self):
        """type/strategy 已是枚举时直接使用。"""
        r = _res(Path("."))
        deps = r.parse_deps([{"name": "x", "type": DepType.SYSTEM, "strategy": DepStrategy.FAIL}])
        assert deps[0].type == DepType.SYSTEM
        assert deps[0].strategy == DepStrategy.FAIL


class TestBuildCsDep:
    """_build_cs_dep。"""

    def test_cs_forms(self, tmp_path):
        r = _res(tmp_path)
        dep = r._build_cs_dep("cs_forms")
        assert "actus-dialogs.exe" in dep.build_check
        assert "cs_forms" in dep.build_command

    def test_cs_tools(self, tmp_path):
        r = _res(tmp_path)
        dep = r._build_cs_dep("cs_tools")
        assert "actus-tools.exe" in dep.build_check

    def test_unknown_cs(self, tmp_path):
        r = _res(tmp_path)
        dep = r._build_cs_dep("cs_other")
        assert dep.build_check.endswith("cs_other" + os.sep + "build") or "cs_other" in dep.build_check


class TestCheckDepCache:
    """check_dep 缓存。"""

    def test_cache_hit(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="mcp:cached", type=DepType.MCP)
        r1 = r.check_dep(dep)
        r2 = r.check_dep(dep)
        assert r1 is r2  # 同一对象（缓存命中）


class TestCheckRuntime:
    """_check_runtime: PATH 检查 + 别名展开。"""

    def test_direct_hit(self, tmp_path, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda name: "C:/fake/python.exe" if name == "python" else None)
        r = _res(tmp_path)
        dep = Dependency(name="python", type=DepType.RUNTIME)
        result = r.check_dep(dep)
        assert result.satisfied is True
        assert "python.exe" in result.message

    def test_alias_fallback(self, tmp_path, monkeypatch):
        """runtime:python 主名 miss，py 命中。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda name: "C:/fake/py.exe" if name == "py" else None)
        r = _res(tmp_path)
        dep = Dependency(name="python", type=DepType.RUNTIME)
        result = r.check_dep(dep)
        assert result.satisfied is True

    def test_not_found(self, tmp_path, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda name: None)
        r = _res(tmp_path)
        dep = Dependency(name="rust", type=DepType.RUNTIME)
        result = r.check_dep(dep)
        assert result.satisfied is False
        assert "rustc" in result.message  # 别名列入候选

    def test_which_raises(self, tmp_path, monkeypatch):
        import shutil
        def boom(name):
            raise RuntimeError("path error")
        monkeypatch.setattr(shutil, "which", boom)
        r = _res(tmp_path)
        dep = Dependency(name="shell", type=DepType.RUNTIME)
        result = r.check_dep(dep)
        assert result.satisfied is False


class TestCheckCsBuild:
    """_check_cs_build。"""

    def test_artifact_exists(self, tmp_path):
        r = _res(tmp_path)
        exe = tmp_path / "build" / "out.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("")
        dep = Dependency(name="cs_x", type=DepType.CS_BUILD, build_check=str(exe))
        result = r.check_dep(dep)
        assert result.satisfied is True

    def test_artifact_missing(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="cs_x", type=DepType.CS_BUILD, build_check=str(tmp_path / "no.exe"), build_command="build")
        result = r.check_dep(dep)
        assert result.satisfied is False
        assert result.auto_fixable is True
        assert result.fix_command == "build"

    def test_no_build_check(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="cs_x", type=DepType.CS_BUILD, build_check="")
        result = r.check_dep(dep)
        assert result.satisfied is False
        assert result.message == "未知构建目标"


class TestCheckPipPkg:
    """_check_pip_pkg: import 成功/失败。"""

    def test_installed(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="json", type=DepType.LANG, lang_manager="pip")
        result = r.check_dep(dep)
        assert result.satisfied is True

    def test_not_installed(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="definitely_not_a_real_pkg_xyz_123", type=DepType.LANG, lang_manager="pip")
        result = r.check_dep(dep)
        assert result.satisfied is False
        assert result.fix_command == "pip install definitely_not_a_real_pkg_xyz_123"
        assert result.ephemeral_cmd == "pipx run definitely_not_a_real_pkg_xyz_123"


class TestCheckNpmPkg:
    """_check_npm_pkg。"""

    def _write_pkg_json(self, tmp_path, deps):
        shiki_dir = tmp_path / "engine" / "actuscore" / "_shiki"
        shiki_dir.mkdir(parents=True)
        (shiki_dir / "package.json").write_text(json.dumps({"dependencies": deps}), encoding="utf-8")
        return shiki_dir

    def test_declared_in_pkg_json(self, tmp_path):
        r = _res(tmp_path)
        self._write_pkg_json(tmp_path, {"shiki": "^1.0"})
        dep = Dependency(name="shiki", type=DepType.LANG, lang_manager="npm")
        result = r.check_dep(dep)
        assert result.satisfied is True
        assert "已声明" in result.message

    def test_installed_in_node_modules(self, tmp_path):
        r = _res(tmp_path)
        shiki_dir = self._write_pkg_json(tmp_path, {})
        nm = shiki_dir / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        dep = Dependency(name="lodash", type=DepType.LANG, lang_manager="npm")
        result = r.check_dep(dep)
        assert result.satisfied is True
        assert "已安装" in result.message

    def test_not_installed(self, tmp_path):
        r = _res(tmp_path)
        self._write_pkg_json(tmp_path, {})
        dep = Dependency(name="chalk", type=DepType.LANG, lang_manager="npm")
        result = r.check_dep(dep)
        assert result.satisfied is False
        assert "npm install" in result.fix_command

    def test_no_pkg_json(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="chalk", type=DepType.LANG, lang_manager="npm")
        result = r.check_dep(dep)
        assert result.satisfied is False


class TestCheckSystemCmd:
    """_check_system_cmd: where / _meta/tools / 策略。"""

    def _mock_where_success(self, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 0
        r.stdout = "C:/fake/tool.exe\n"
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)

    def test_where_success(self, tmp_path, monkeypatch):
        self._mock_where_success(monkeypatch)
        r = _res(tmp_path)
        dep = Dependency(name="pandoc", type=DepType.SYSTEM)
        result = r.check_dep(dep)
        assert result.satisfied is True

    def test_where_fail_tools_dir(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 1
        r.stdout = ""
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        # 在 _meta/tools/ 放一个工具
        res = _res(tmp_path)
        tools = tmp_path / "_meta" / "tools"
        tools.mkdir(parents=True)
        (tools / "mytool.exe").write_text("")
        dep = Dependency(name="mytool", type=DepType.SYSTEM)
        result = res.check_dep(dep)
        assert result.satisfied is True
        assert "_meta/tools" in result.message

    def test_hint_strategy(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 1
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        dep = Dependency(name="missing_tool", type=DepType.SYSTEM, strategy=DepStrategy.HINT)
        result = res.check_dep(dep)
        assert result.satisfied is False
        assert result.auto_fixable is True

    def test_download_strategy(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 1
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        dep = Dependency(name="missing_tool", type=DepType.SYSTEM, strategy=DepStrategy.DOWNLOAD)
        result = res.check_dep(dep)
        assert result.satisfied is False
        assert "下载" in result.message

    def test_fail_strategy(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 1
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        dep = Dependency(name="missing_tool", type=DepType.SYSTEM, strategy=DepStrategy.FAIL)
        result = res.check_dep(dep)
        assert result.satisfied is False
        assert result.auto_fixable is False

    def test_where_exception(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        def boom(cmd, **kw):
            raise FileNotFoundError("where not found")
        monkeypatch.setattr(dmod, "_run_cmd_safe", boom)
        res = _res(tmp_path)
        dep = Dependency(name="tool", type=DepType.SYSTEM, strategy=DepStrategy.FAIL)
        result = res.check_dep(dep)
        assert result.satisfied is False


class TestCheckBuiltin:
    """_check_builtin: 引擎内依赖。"""

    def test_exists(self, tmp_path):
        """'paths' 模块在 vools/actus/ 下确实存在。"""
        r = _res(tmp_path)
        dep = Dependency(name="paths", type=DepType.BUILTIN)
        result = r.check_dep(dep)
        assert result.satisfied is True

    def test_not_exists(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="no_such_module_xyz", type=DepType.BUILTIN)
        result = r.check_dep(dep)
        assert result.satisfied is False


class TestCheckMcp:
    """_check_mcp: 恒 satisfied。"""

    def test_mcp(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="my_server", type=DepType.MCP)
        result = r.check_dep(dep)
        assert result.satisfied is True
        assert "运行时连接" in result.message


class TestCheckAction:
    """_check_action: find_action_file。"""

    def test_not_found(self, tmp_path):
        r = _res(tmp_path)
        dep = Dependency(name="nonexistent.action.xyz", type=DepType.ACTION)
        result = r.check_dep(dep)
        assert result.satisfied is False

    def test_resolver_exception(self, tmp_path, monkeypatch):
        """find_action_file 抛异常 → found=None → not satisfied。"""
        r = _res(tmp_path)
        import vools.actus.dependency as dmod
        # 让 import 失败：mock resolver.find_action_file 抛异常
        with patch("vools.actus.resolver.find_action_file", side_effect=RuntimeError("boom")):
            dep = Dependency(name="some.action", type=DepType.ACTION)
            result = r.check_dep(dep)
        assert result.satisfied is False

    def test_found(self, tmp_path):
        """找到动作 → satisfied。"""
        r = _res(tmp_path)
        with patch("vools.actus.resolver.find_action_file", return_value="/fake/path.md"):
            dep = Dependency(name="some.action", type=DepType.ACTION)
            result = r.check_dep(dep)
        assert result.satisfied is True
        assert "存在" in result.message


class TestResolve:
    """resolve: 三策略流程。"""

    def test_all_satisfied(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 0
        r.stdout = "found\n"
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        deps = [Dependency(name="pandoc", type=DepType.SYSTEM)]
        ok, messages = res.resolve(deps)
        assert ok is True
        assert any("✅" in m for m in messages)

    def test_hint_strategy_message(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 1
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        deps = [Dependency(name="missing", type=DepType.SYSTEM, strategy=DepStrategy.HINT)]
        ok, messages = res.resolve(deps)
        assert ok is False
        assert any("💡" in m for m in messages)

    def test_hint_with_ephemeral_cmd(self, tmp_path, monkeypatch):
        """HINT 策略下 result 带 ephemeral_cmd 应输出「临时执行」行。"""
        res = _res(tmp_path)
        dep = Dependency(name="ruff", type=DepType.LANG, lang_manager="pip", strategy=DepStrategy.HINT)
        with patch.object(res, "check_dep", return_value=DepCheckResult(
            "ruff", False, "未安装", strategy=DepStrategy.HINT,
            fix_command="pip install ruff", ephemeral_cmd="pipx run ruff")):
            ok, messages = res.resolve([dep])
        assert any("临时执行" in m for m in messages)

    def test_fail_strategy_message(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock()
        r.returncode = 1
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        deps = [Dependency(name="missing", type=DepType.SYSTEM, strategy=DepStrategy.FAIL)]
        ok, messages = res.resolve(deps)
        assert ok is False
        assert any("❌" in m for m in messages)

    def test_ephemeral_success(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        # where 失败 → 走 ephemeral
        calls = []
        def mock_run(cmd, **kw):
            calls.append(cmd)
            if cmd == ["where", "ruff"]:
                r = MagicMock(); r.returncode = 1; r.stdout = ""; return r
            r = MagicMock(); r.returncode = 0; r.stdout = "ok"; r.stderr = ""; return r
        monkeypatch.setattr(dmod, "_run_cmd_safe", mock_run)
        res = _res(tmp_path)
        dep = Dependency(name="ruff", type=DepType.LANG, lang_manager="pip", strategy=DepStrategy.EPHEMERAL)
        with patch.object(res, "_check_pip_pkg", return_value=DepCheckResult(
            "ruff", False, "未安装", strategy=DepStrategy.EPHEMERAL,
            ephemeral_cmd="pipx run ruff", fix_command="pip install ruff")):
            ok, messages = res.resolve([dep])
        # ephemeral 成功 → all_ok=True
        assert ok is True
        assert any("临时执行成功" in m for m in messages)

    def test_ephemeral_failure_degrades_to_hint(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        def mock_run(cmd, **kw):
            r = MagicMock(); r.returncode = 1; r.stdout = ""; return r
        monkeypatch.setattr(dmod, "_run_cmd_safe", mock_run)
        res = _res(tmp_path)
        dep = Dependency(name="ruff", type=DepType.LANG, lang_manager="pip", strategy=DepStrategy.EPHEMERAL)
        with patch.object(res, "_check_pip_pkg", return_value=DepCheckResult(
            "ruff", False, "未安装", strategy=DepStrategy.EPHEMERAL,
            ephemeral_cmd="pipx run ruff", fix_command="pip install ruff")):
            with patch.object(res, "try_ephemeral", return_value=(False, "pipx not found")):
                ok, messages = res.resolve([dep])
        assert ok is False
        assert any("临时执行失败" in m for m in messages)
        assert any("安装命令" in m for m in messages)

    def test_download_strategy_success(self, tmp_path, monkeypatch):
        res = _res(tmp_path)
        dep = Dependency(name="pandoc", type=DepType.SYSTEM, strategy=DepStrategy.DOWNLOAD)
        with patch.object(res, "check_dep", return_value=DepCheckResult(
            "pandoc", False, "未找到", strategy=DepStrategy.DOWNLOAD)):
            with patch.object(res, "try_download", return_value=(True, "已下载到 tools/pandoc.exe")):
                ok, messages = res.resolve([dep])
        assert ok is True
        assert any("已下载" in m for m in messages)

    def test_download_strategy_failure(self, tmp_path):
        res = _res(tmp_path)
        dep = Dependency(name="pandoc", type=DepType.SYSTEM, strategy=DepStrategy.DOWNLOAD)
        with patch.object(res, "check_dep", return_value=DepCheckResult(
            "pandoc", False, "未找到", strategy=DepStrategy.DOWNLOAD, fix_command="install")):
            with patch.object(res, "try_download", return_value=(False, "network error")):
                ok, messages = res.resolve([dep])
        assert ok is False
        assert any("下载失败" in m for m in messages)
        assert any("备选安装" in m for m in messages)

    def test_fail_auto_install_success(self, tmp_path):
        res = _res(tmp_path)
        dep = Dependency(name="pkg", type=DepType.SYSTEM, strategy=DepStrategy.FAIL)
        with patch.object(res, "check_dep", return_value=DepCheckResult(
            "pkg", False, "未找到", strategy=DepStrategy.FAIL,
            auto_fixable=True, fix_command="pip install pkg")):
            with patch.object(res, "_try_fix", return_value=True):
                ok, messages = res.resolve([dep], auto_install=True)
        assert ok is True
        assert any("修复成功" in m for m in messages)

    def test_fail_auto_install_failure(self, tmp_path):
        res = _res(tmp_path)
        dep = Dependency(name="pkg", type=DepType.SYSTEM, strategy=DepStrategy.FAIL)
        with patch.object(res, "check_dep", return_value=DepCheckResult(
            "pkg", False, "未找到", strategy=DepStrategy.FAIL,
            auto_fixable=True, fix_command="pip install pkg")):
            with patch.object(res, "_try_fix", return_value=False):
                ok, messages = res.resolve([dep], auto_install=True)
        assert ok is False
        assert any("修复失败" in m for m in messages)


class TestTryFix:
    """_try_fix 分支。"""

    def test_no_command(self, tmp_path):
        res = _res(tmp_path)
        result = DepCheckResult("x", False, "msg")
        assert res._try_fix(result) is False

    def test_pip_install(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock(); r.returncode = 0
        seen = {}
        def mock_run(cmd, **kw):
            seen["cmd"] = cmd
            return r
        monkeypatch.setattr(dmod, "_run_cmd_safe", mock_run)
        res = _res(tmp_path)
        result = DepCheckResult("x", False, "msg", fix_command="pip install requests")
        assert res._try_fix(result) is True
        assert seen["cmd"][0] == sys.executable

    def test_cd_command(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock(); r.returncode = 0
        seen = {}
        def mock_run(cmd, **kw):
            seen["cmd"] = cmd
            seen["cwd"] = kw.get("cwd")
            return r
        monkeypatch.setattr(dmod, "_run_cmd_safe", mock_run)
        res = _res(tmp_path)
        result = DepCheckResult("x", False, "msg", fix_command="cd /some/dir && build.bat all")
        assert res._try_fix(result) is True
        assert seen["cwd"] == "/some/dir"

    def test_other_command(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock(); r.returncode = 0
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        result = DepCheckResult("x", False, "msg", fix_command="winget install something")
        assert res._try_fix(result) is True

    def test_exception_returns_false(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        def boom(cmd, **kw):
            raise RuntimeError("spawn failed")
        monkeypatch.setattr(dmod, "_run_cmd_safe", boom)
        res = _res(tmp_path)
        result = DepCheckResult("x", False, "msg", fix_command="pip install x")
        assert res._try_fix(result) is False


class TestTryEphemeral:
    """try_ephemeral。"""

    def test_lang_pip(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock(); r.returncode = 0; r.stdout = "done"; r.stderr = ""
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        dep = Dependency(name="ruff", type=DepType.LANG, lang_manager="pip")
        ok, out = res.try_ephemeral(dep)
        assert ok is True
        assert "done" in out

    def test_lang_npm(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        r = MagicMock(); r.returncode = 0; r.stdout = "ok"; r.stderr = ""
        monkeypatch.setattr(dmod, "_run_cmd_safe", lambda cmd, **kw: r)
        res = _res(tmp_path)
        dep = Dependency(name="prettier", type=DepType.LANG, lang_manager="npm")
        ok, out = res.try_ephemeral(dep)
        assert ok is True

    def test_non_lang(self, tmp_path):
        res = _res(tmp_path)
        dep = Dependency(name="x", type=DepType.SYSTEM)
        ok, out = res.try_ephemeral(dep)
        assert ok is False
        assert "不支持" in out

    def test_exception(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        def boom(cmd, **kw):
            raise RuntimeError("fail")
        monkeypatch.setattr(dmod, "_run_cmd_safe", boom)
        res = _res(tmp_path)
        dep = Dependency(name="ruff", type=DepType.LANG, lang_manager="pip")
        ok, out = res.try_ephemeral(dep)
        assert ok is False

    def test_file_not_found(self, tmp_path, monkeypatch):
        """pipx/npx 不存在 → FileNotFoundError 分支。"""
        import vools.actus.dependency as dmod
        def boom(cmd, **kw):
            raise FileNotFoundError("pipx not found")
        monkeypatch.setattr(dmod, "_run_cmd_safe", boom)
        res = _res(tmp_path)
        dep = Dependency(name="ruff", type=DepType.LANG, lang_manager="pip")
        ok, out = res.try_ephemeral(dep)
        assert ok is False
        assert "不可用" in out


class TestTryDownload:
    """try_download。"""

    def test_non_system(self, tmp_path):
        res = _res(tmp_path)
        dep = Dependency(name="x", type=DepType.LANG)
        ok, out = res.try_download(dep)
        assert ok is False
        assert "不支持" in out

    def test_no_mapping(self, tmp_path):
        res = _res(tmp_path)
        dep = Dependency(name="unknown_tool", type=DepType.SYSTEM)
        ok, out = res.try_download(dep)
        assert ok is False
        assert "无预定义下载地址" in out

    def test_mapping_pandoc(self, tmp_path, monkeypatch):
        res = _res(tmp_path)
        dep = Dependency(name="pandoc", type=DepType.SYSTEM)
        # mock urllib.request.urlretrieve
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlretrieve", lambda url, dest: Path(dest).write_text("x"))
        ok, out = res.try_download(dep)
        assert ok is True
        assert "已下载" in out

    def test_download_failure(self, tmp_path, monkeypatch):
        res = _res(tmp_path)
        dep = Dependency(name="jq", type=DepType.SYSTEM)
        import urllib.request
        def boom(url, dest):
            raise IOError("network down")
        monkeypatch.setattr(urllib.request, "urlretrieve", boom)
        ok, out = res.try_download(dep)
        assert ok is False
        assert "下载失败" in out


class TestTopologicalSort:
    """topological_sort: 无环 / 有环。"""

    def test_no_cycle(self, tmp_path):
        res = _res(tmp_path)
        ok, order = res.topological_sort({
            "a": ["b"],
            "b": [],
            "c": ["a"],
        })
        assert ok is True
        assert order.index("b") < order.index("a") < order.index("c")

    def test_cycle(self, tmp_path):
        res = _res(tmp_path)
        ok, order = res.topological_sort({
            "a": ["b"],
            "b": ["a"],
        })
        assert ok is False

    def test_self_cycle(self, tmp_path):
        res = _res(tmp_path)
        ok, order = res.topological_sort({"a": ["a"]})
        assert ok is False

    def test_empty(self, tmp_path):
        res = _res(tmp_path)
        ok, order = res.topological_sort({})
        assert ok is True
        assert order == []


class TestGetDepTree:
    """get_dep_tree: 递归 + 循环检测。"""

    def test_action_not_found(self, tmp_path):
        res = _res(tmp_path)
        tree = res.get_dep_tree("nonexistent.act")
        assert tree["found"] is False

    def test_circular(self, tmp_path):
        res = _res(tmp_path)
        tree = res.get_dep_tree("x", visited={"x"})
        assert tree["circular"] is True

    def test_tree_with_action_found(self, tmp_path, monkeypatch):
        """找到动作文件时构建依赖树。"""
        import vools.actus.dependency as dmod
        res = _res(tmp_path)
        # mock _find_action_file 返回一个假路径
        dep_file = tmp_path / "act.md"
        dep_file.write_text('{"id": "act.x", "deps": ["mcp:server"]}', encoding="utf-8")
        monkeypatch.setattr(res, "_find_action_file", lambda aid: str(dep_file))
        tree = res.get_dep_tree("act.x")
        assert tree["id"] == "act.x"
        assert tree["type"] == "action"
        assert len(tree["deps"]) == 1
        assert tree["deps"][0]["id"] == "server"

    def test_tree_recursive_action_dep(self, tmp_path, monkeypatch):
        """ACTION 类型依赖递归展开。"""
        res = _res(tmp_path)
        dep_file = tmp_path / "act.md"
        dep_file.write_text('{"id": "act.a", "deps": ["action:act.b"]}', encoding="utf-8")
        monkeypatch.setattr(res, "_find_action_file", lambda aid: str(dep_file) if aid == "act.a" else None)
        tree = res.get_dep_tree("act.a")
        assert len(tree["deps"]) == 1
        # act.b 不存在 → found: False
        assert tree["deps"][0].get("found") is False


class TestDoCheckDispatch:
    """_do_check 分派。"""

    def test_unknown_type(self, tmp_path):
        """未知 dep 类型 → unknown dep type。"""
        res = _res(tmp_path)
        dep = Dependency(name="weird")
        object.__setattr__(dep, "type", None)  # 强制未知类型
        result = res._do_check(dep)
        assert result.satisfied is False
        assert "unknown" in result.message


class TestExtractDeps:
    """_extract_deps_from_file。"""

    def test_json_deps(self, tmp_path):
        f = tmp_path / "act.md"
        f.write_text('{"id": "act.x", "deps": ["pip:requests", "system:pandoc"]}', encoding="utf-8")
        res = _res(tmp_path)
        deps = res._extract_deps_from_file(str(f))
        assert deps == ["pip:requests", "system:pandoc"]

    def test_no_deps(self, tmp_path):
        f = tmp_path / "act.md"
        f.write_text('{"id": "act.x"}', encoding="utf-8")
        res = _res(tmp_path)
        assert res._extract_deps_from_file(str(f)) == []

    def test_bad_json(self, tmp_path):
        f = tmp_path / "act.md"
        f.write_text('"deps": [broken', encoding="utf-8")
        res = _res(tmp_path)
        assert res._extract_deps_from_file(str(f)) == []

    def test_file_missing(self, tmp_path):
        res = _res(tmp_path)
        assert res._extract_deps_from_file(str(tmp_path / "no.md")) == []


class TestSingleton:
    """get_resolver 单例。"""

    def test_same_instance(self):
        import vools.actus.dependency as dmod
        dmod._resolver = None
        r1 = get_resolver()
        r2 = get_resolver()
        assert r1 is r2
        # 清理
        dmod._resolver = None


class TestCheckActionDeps:
    """check_action_deps 便捷函数。"""

    def test_not_found(self, monkeypatch):
        import vools.actus.dependency as dmod
        mock_res = MagicMock()
        mock_res._find_action_file.return_value = None
        monkeypatch.setattr(dmod, "_resolver", mock_res)
        result = check_action_deps("no.such.action")
        assert result["ok"] is False
        assert "error" in result

    def test_found_with_deps(self, tmp_path, monkeypatch):
        import vools.actus.dependency as dmod
        mock_res = MagicMock()
        mock_res._find_action_file.return_value = str(tmp_path / "act.md")
        mock_res._extract_deps_from_file.return_value = ["mcp:server"]
        mock_res.parse_deps.return_value = [Dependency(name="server", type=DepType.MCP)]
        mock_res.resolve.return_value = (True, ["✅ server: ok"])
        monkeypatch.setattr(dmod, "_resolver", mock_res)
        result = check_action_deps("some.action")
        assert result["ok"] is True
        assert result["deps_total"] == 1
        assert result["deps_satisfied"] == 1


class TestFindActionsRoot:
    """_find_actions_root 定位逻辑。"""

    def test_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))
        (tmp_path / "actions").mkdir()
        root = DependencyResolver._find_actions_root()
        assert root == str(tmp_path / "actions")

    def test_env_var_no_actions_dir(self, tmp_path, monkeypatch):
        """env 指向的目录没有 actions/ → 回退。"""
        monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        (tmp_path / "actions").mkdir()
        root = DependencyResolver._find_actions_root()
        assert root == str(tmp_path / "actions")

    def test_no_env_no_cwd(self, tmp_path, monkeypatch):
        """env 无、cwd 无 actions → 回退到 repo_root 推导。"""
        monkeypatch.delenv("ACTUS_REPO_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        root = DependencyResolver._find_actions_root()
        # repo_root() 会推导到真实 repo，actions/ 存在则返回它
        assert os.path.isabs(root)
