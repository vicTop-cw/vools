"""importsys.py 契约测试（Round 48）。

契约:
- ImportDecl: 构造/repr/source_key
- parse_imports: 有效/无效语法/空
- CompilerBackend: 基类属性
- RustCompiler: is_available/compile/超时/异常
- CCompiler: is_available/compile/gcc/cl.exe
- ShellBackend: is_available/compile/文件不存在
- NodeBackend: is_available/compile
- ImportResolver: init/resolve/ensure_all/resolve_all/_cache_key
- resolve_imports_for_action: 有/无 cfg/strict
- check_imports_available
- 模块导出
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vools.actus.importsys import (
    CCompiler,
    CompilerBackend,
    IMPORT_RE,
    ImportDecl,
    ImportResolver,
    NodeBackend,
    RustCompiler,
    ShellBackend,
    check_imports_available,
    parse_imports,
    resolve_imports_for_action,
)


class TestImportDecl:
    """ImportDecl 基础。"""

    def test_init(self):
        d = ImportDecl("rust", "lib.rs", "mylib")
        assert d.language == "rust"
        assert d.path == "lib.rs"
        assert d.alias == "mylib"

    def test_repr(self):
        d = ImportDecl("rust", "lib.rs", "mylib")
        assert repr(d) == "#!import rust:lib.rs as mylib"

    def test_source_key(self):
        d = ImportDecl("rust", "lib.rs", "mylib")
        assert d.source_key() == "rust:lib.rs"


class TestParseImports:
    """parse_imports 解析。"""

    def test_parse_single(self):
        text = "#!import rust:path/to/lib.rs as mylib"
        decls = parse_imports(text)
        assert len(decls) == 1
        assert decls[0].language == "rust"
        assert decls[0].path == "path/to/lib.rs"
        assert decls[0].alias == "mylib"

    def test_parse_multiple(self):
        text = """
#!import rust:a.rs as x
#!import c:b.c as y
#!import shell:c.sh as sh
"""
        decls = parse_imports(text)
        assert len(decls) == 3
        assert decls[0].alias == "x"
        assert decls[1].alias == "y"
        assert decls[2].alias == "sh"

    def test_parse_empty(self):
        decls = parse_imports("")
        assert decls == []

    def test_parse_no_imports(self):
        decls = parse_imports("#!cfg action: test")
        assert decls == []

    def test_parse_invalid_syntax(self):
        decls = parse_imports("#!import invalid syntax")
        assert decls == []

    def test_parse_no_alias(self):
        decls = parse_imports("#!import rust:lib.rs")
        assert decls == []

    def test_import_regex(self):
        """IMPORT_RE 应能匹配各种格式。"""
        m = IMPORT_RE.search("#!import rust:foo/bar.rs as baz")
        assert m is not None
        assert m.group(1) == "rust"
        assert m.group(2) == "foo/bar.rs"
        assert m.group(3) == "baz"


class TestCompilerBackend:
    """CompilerBackend 基类。"""

    def test_base_class_abstract(self):
        """基类方法应返回 None。"""
        b = CompilerBackend()
        # language property 应返回 None（未实现）
        assert b.language is None


class TestRustCompiler:
    """RustCompiler。"""

    def test_language(self):
        assert RustCompiler().language == "rust"

    def test_is_available_no_rustc(self, monkeypatch):
        """无 rustc 时 is_available 返回 False。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: None)
        assert RustCompiler().is_available() is False

    def test_is_available_with_rustc(self, monkeypatch):
        """有 rustc 时 is_available 返回 True。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/rustc")
        assert RustCompiler().is_available() is True

    def test_compile_rustc_unavailable(self, monkeypatch):
        """rustc 不可用时应返回失败。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: None)
        c = RustCompiler()
        ok, msg = c.compile(Path("test.rs"), Path("out.pyd"))
        assert ok is False
        assert "rustc" in msg

    def test_compile_success(self, monkeypatch):
        """编译成功。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/rustc")
        c = RustCompiler()

        class MockResult:
            returncode = 0
            stderr = ""

        monkeypatch.setattr("vools.actus.importsys.run_cmd_safe",
                            lambda *a, **kw: MockResult())
        ok, msg = c.compile(Path("test.rs"), Path("out.pyd"))
        assert ok is True

    def test_compile_timeout(self, monkeypatch):
        """编译超时应返回超时错误。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/rustc")
        c = RustCompiler()

        class MockResult:
            returncode = -9
            stderr = ""

        monkeypatch.setattr("vools.actus.importsys.run_cmd_safe",
                            lambda *a, **kw: MockResult())
        ok, msg = c.compile(Path("test.rs"), Path("out.pyd"))
        assert ok is False
        assert "超时" in msg

    def test_compile_exception(self, monkeypatch):
        """编译异常应返回错误信息。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/rustc")
        c = RustCompiler()

        def raise_err(*a, **kw):
            raise OSError("spawn failed")

        monkeypatch.setattr("vools.actus.importsys.run_cmd_safe", raise_err)
        ok, msg = c.compile(Path("test.rs"), Path("out.pyd"))
        assert ok is False
        assert "spawn failed" in msg


class TestCCompiler:
    """CCompiler。"""

    def test_language(self):
        assert CCompiler().language == "c"

    def test_is_available_no_compiler(self, monkeypatch):
        """无编译器时 is_available 返回 False。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: None)
        assert CCompiler().is_available() is False

    def test_is_available_with_gcc(self, monkeypatch):
        """有 gcc 时 is_available 返回 True。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/gcc" if x == "gcc" else None)
        assert CCompiler().is_available() is True

    def test_is_available_with_cl(self, monkeypatch):
        """有 cl.exe 时 is_available 返回 True。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/cl.exe" if x == "cl.exe" else None)
        assert CCompiler().is_available() is True

    def test_compile_no_compiler(self, monkeypatch):
        """无编译器时应返回失败。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: None)
        c = CCompiler()
        ok, msg = c.compile(Path("test.c"), Path("out.pyd"))
        assert ok is False

    def test_compile_gcc(self, monkeypatch):
        """gcc 编译路径。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/gcc" if x == "gcc" else None)
        c = CCompiler()

        class MockResult:
            returncode = 0
            stderr = ""

        monkeypatch.setattr("vools.actus.importsys.run_cmd_safe",
                            lambda *a, **kw: MockResult())
        ok, msg = c.compile(Path("test.c"), Path("out.pyd"))
        assert ok is True

    def test_compile_timeout(self, monkeypatch):
        """编译超时。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/gcc" if x == "gcc" else None)
        c = CCompiler()

        class MockResult:
            returncode = -9
            stderr = ""

        monkeypatch.setattr("vools.actus.importsys.run_cmd_safe",
                            lambda *a, **kw: MockResult())
        ok, msg = c.compile(Path("test.c"), Path("out.pyd"))
        assert ok is False
        assert "超时" in msg


class TestShellBackend:
    """ShellBackend。"""

    def test_language(self):
        assert ShellBackend().language == "shell"

    def test_is_available(self):
        """Shell 总是可用。"""
        assert ShellBackend().is_available() is True

    def test_compile_source_not_exists(self):
        """源文件不存在时应返回失败。"""
        b = ShellBackend()
        ok, msg = b.compile(Path("nonexistent.sh"), Path("out"))
        assert ok is False
        assert "不存在" in msg

    def test_compile_success(self, tmp_path):
        """源文件存在时应返回成功。"""
        src = tmp_path / "test.sh"
        src.write_text("echo hi", encoding="utf-8")
        b = ShellBackend()
        ok, msg = b.compile(src, tmp_path / "out")
        assert ok is True


class TestNodeBackend:
    """NodeBackend。"""

    def test_language(self):
        assert NodeBackend().language == "node"

    def test_is_available_no_node(self, monkeypatch):
        """无 node 时 is_available 返回 False。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: None)
        assert NodeBackend().is_available() is False

    def test_is_available_with_node(self, monkeypatch):
        """有 node 时 is_available 返回 True。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/node")
        assert NodeBackend().is_available() is True

    def test_compile_no_node(self, monkeypatch):
        """无 node 时应返回失败。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: None)
        b = NodeBackend()
        ok, msg = b.compile(Path("test.mjs"), Path("out"))
        assert ok is False

    def test_compile_success(self, monkeypatch, tmp_path):
        """node 可用且源文件存在时应返回成功。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/node")
        src = tmp_path / "test.mjs"
        src.write_text("export function test() {}", encoding="utf-8")
        b = NodeBackend()
        ok, msg = b.compile(src, tmp_path / "out")
        assert ok is True

    def test_compile_source_not_exists(self, monkeypatch):
        """node 可用但源文件不存在时应返回失败。"""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda x: "/fake/node")
        b = NodeBackend()
        ok, msg = b.compile(Path("nonexistent.mjs"), Path("out"))
        assert ok is False
        assert "不存在" in msg


class TestImportResolver:
    """ImportResolver。"""

    def _make_resolver_with_shell(self, tmp_path):
        """创建测试用的 ImportResolver，shell 后端 mock 成真正创建文件。"""
        src = tmp_path / "test.sh"
        src.write_text("echo hi", encoding="utf-8")
        r = ImportResolver(str(tmp_path))
        # shell 后端不创建输出文件，所以 mock compile 让它创建
        def mock_shell_compile(source_path, output_path):
            output_path.write_text("echo hi", encoding="utf-8")
            return True, ""
        r._backends["shell"] = ShellBackend()
        r._backends["shell"].compile = mock_shell_compile
        return r, src

    def test_init(self, tmp_path):
        """初始化。"""
        r = ImportResolver(str(tmp_path))
        assert r.repo_root == Path(str(tmp_path))
        assert r.cache_dir == Path(str(tmp_path)) / "_meta" / "imports_cache"

    def test_init_default(self):
        """默认构造。"""
        r = ImportResolver()
        assert r.repo_root == Path(".")

    def test_resolve_unsupported_lang(self, tmp_path):
        """不支持的语言。"""
        r = ImportResolver(str(tmp_path))
        decl = ImportDecl("python", "test.py", "p")
        ok, msg, path = r.resolve(decl)
        assert ok is False
        assert "不支持" in msg

    def test_resolve_source_not_exists(self, tmp_path):
        """源文件不存在。"""
        r = ImportResolver(str(tmp_path))
        decl = ImportDecl("shell", "nonexistent.sh", "sh")
        ok, msg, path = r.resolve(decl)
        assert ok is False
        assert "不存在" in msg

    def test_resolve_shell_success(self, tmp_path):
        """Shell 解析成功。"""
        r, src = self._make_resolver_with_shell(tmp_path)
        decl = ImportDecl("shell", "test.sh", "sh")
        ok, msg, path = r.resolve(decl)
        assert ok is True
        assert path is not None

    def test_resolve_cache_hit(self, tmp_path):
        """缓存命中。"""
        r, src = self._make_resolver_with_shell(tmp_path)
        decl = ImportDecl("shell", "test.sh", "sh")
        # 第一次编译
        ok1, msg1, path = r.resolve(decl)
        assert ok1 is True
        # 第二次应缓存命中
        ok2, msg2, path2 = r.resolve(decl)
        assert ok2 is True
        assert "缓存命中" in msg2
        assert path2 == path

    def test_ensure_all(self, tmp_path):
        """ensure_all 全部成功。"""
        r, src = self._make_resolver_with_shell(tmp_path)
        decls = [ImportDecl("shell", "test.sh", "sh")]
        ok, missing, results = r.ensure_all(decls)
        assert ok is True
        assert missing == []
        assert "sh" in results

    def test_ensure_all_missing(self, tmp_path):
        """ensure_all 有缺失。"""
        r = ImportResolver(str(tmp_path))
        decls = [ImportDecl("shell", "nonexistent.sh", "sh")]
        ok, missing, results = r.ensure_all(decls)
        assert ok is False
        assert missing == ["sh"]
        assert results == {}

    def test_resolve_all_alias(self, tmp_path):
        """resolve_all 是 ensure_all 的别名。"""
        r, src = self._make_resolver_with_shell(tmp_path)
        decls = [ImportDecl("shell", "test.sh", "sh")]
        ok1, missing1, results1 = r.ensure_all(decls)
        ok2, missing2, results2 = r.resolve_all(decls)
        assert ok1 == ok2
        assert missing1 == missing2

    def test_cache_key(self, tmp_path):
        """_cache_key 应基于内容生成。"""
        src = tmp_path / "test.sh"
        src.write_text("echo hi", encoding="utf-8")
        r = ImportResolver(str(tmp_path))
        key1 = r._cache_key(src)
        assert len(key1) == 12

    def test_cache_key_stable(self, tmp_path):
        """相同内容应生成相同 key。"""
        src = tmp_path / "test.sh"
        src.write_text("echo hi", encoding="utf-8")
        r = ImportResolver(str(tmp_path))
        key1 = r._cache_key(src)
        key2 = r._cache_key(src)
        assert key1 == key2


class TestResolveImportsForAction:
    """resolve_imports_for_action。"""

    @pytest.fixture
    def mock_shell(self, monkeypatch):
        """mock shell backend 的 compile 让它真正创建输出文件。"""
        def mock_compile(self, source_path, output_path):
            output_path.write_text("echo hi", encoding="utf-8")
            return True, ""
        monkeypatch.setattr(ShellBackend, "compile", mock_compile)

    def test_no_cfg(self):
        """无 _cfg_text。"""
        ok, missing, results = resolve_imports_for_action({"id": "act.a"})
        assert ok is True
        assert missing == []
        assert results == {}

    def test_no_imports(self):
        """cfg 无 import。"""
        ok, missing, results = resolve_imports_for_action({"id": "act.a", "_cfg_text": "#!cfg action: test"})
        assert ok is True
        assert missing == []

    def test_shell_import(self, tmp_path, mock_shell):
        """shell import 成功。"""
        src = tmp_path / "test.sh"
        src.write_text("echo hi", encoding="utf-8")
        action_meta = {"id": "act.a", "_cfg_text": "#!import shell:test.sh as sh"}
        ok, missing, results = resolve_imports_for_action(action_meta, repo_root=str(tmp_path))
        assert ok is True
        assert "sh" in results

    def test_shell_import_strict_fail(self, tmp_path):
        """shell import 失败且 strict=True 应抛 ImportError。"""
        action_meta = {"id": "act.a", "_cfg_text": "#!import shell:nonexistent.sh as sh"}
        with pytest.raises(ImportError):
            resolve_imports_for_action(action_meta, repo_root=str(tmp_path), strict=True)

    def test_shell_import_strict_pass(self, tmp_path, mock_shell):
        """shell import 成功且 strict=True。"""
        src = tmp_path / "test.sh"
        src.write_text("echo hi", encoding="utf-8")
        action_meta = {"id": "act.a", "_cfg_text": "#!import shell:test.sh as sh"}
        ok, missing, results = resolve_imports_for_action(action_meta, repo_root=str(tmp_path), strict=True)
        assert ok is True


class TestCheckImportsAvailable:
    """check_imports_available。"""

    @pytest.fixture
    def mock_shell(self, monkeypatch):
        """mock shell backend 的 compile 让它真正创建输出文件。"""
        def mock_compile(self, source_path, output_path):
            output_path.write_text("echo hi", encoding="utf-8")
            return True, ""
        monkeypatch.setattr(ShellBackend, "compile", mock_compile)

    def test_no_cfg(self):
        """无 _cfg_text。"""
        results = check_imports_available({"id": "act.a"})
        assert results == []

    def test_shell_import(self, tmp_path, mock_shell):
        """shell import 检查。"""
        src = tmp_path / "test.sh"
        src.write_text("echo hi", encoding="utf-8")
        action_meta = {"id": "act.a", "_cfg_text": "#!import shell:test.sh as sh"}
        results = check_imports_available(action_meta, repo_root=str(tmp_path))
        assert len(results) == 1
        assert results[0]["ok"] is True

    def test_shell_import_missing(self, tmp_path):
        """shell import 不存在。"""
        action_meta = {"id": "act.a", "_cfg_text": "#!import shell:nonexistent.sh as sh"}
        results = check_imports_available(action_meta, repo_root=str(tmp_path))
        assert len(results) == 1
        assert results[0]["ok"] is False


class TestModuleExports:
    """模块导出。"""

    def test_all_exports(self):
        """__all__ 应包含主要类。"""
        mod = __import__('vools.actus.importsys', fromlist=['__all__'])
        for name in ['ImportDecl', 'ImportResolver', 'RustCompiler', 'CCompiler',
                      'ShellBackend', 'NodeBackend', 'CompilerBackend',
                      'parse_imports', 'resolve_imports_for_action', 'check_imports_available']:
            assert name in mod.__all__, f"{name} not in __all__"
