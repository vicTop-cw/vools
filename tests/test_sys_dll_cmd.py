# -*- coding: utf-8 -*-
"""测试 vools.sys.dll_cmd — DllCommands / _lib_dir / _find_dll_path / _setup_funcs。"""

import ctypes
import os
import sys
import pytest

from vools.sys.dll_cmd import (
    DllCommands, _lib_dir, _find_dll_path, _setup_funcs,
    _NIM_DLLS, _IS_WINDOWS,
)

__all__ = ["TestLibDir", "TestFindDllPath", "TestSetupFuncs",
           "TestDllCommands", "TestNimDlls", "TestImport"]


class TestLibDir:
    """_lib_dir 测试。"""

    def test_returns_path(self, monkeypatch):
        monkeypatch.setattr("vools.bridge.core.loader._LIB_DIR", "/tmp/lib")
        assert _lib_dir() == "/tmp/lib"

    def test_none_on_import_error(self, monkeypatch):
        # monkeypatch 模块，使 `from ..bridge.core.loader import _LIB_DIR` 触发 ImportError
        import vools.bridge.core.loader as loader_mod
        original = loader_mod._LIB_DIR
        del loader_mod._LIB_DIR
        try:
            assert _lib_dir() is None
        finally:
            loader_mod._LIB_DIR = original


class TestFindDllPath:
    """_find_dll_path 测试。"""

    def test_none_without_lib_dir(self, monkeypatch):
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: None)
        assert _find_dll_path("vools_crypto") is None

    def test_find_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: str(tmp_path))
        monkeypatch.setattr("vools.sys.dll_cmd._IS_WINDOWS", True)
        (tmp_path / "vools_crypto.dll").write_bytes(b"x")
        path = _find_dll_path("vools_crypto")
        assert path is not None
        assert path.endswith("vools_crypto.dll")

    def test_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: str(tmp_path))
        monkeypatch.setattr("vools.sys.dll_cmd._IS_WINDOWS", True)
        assert _find_dll_path("nope") is None

    def test_non_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: str(tmp_path))
        monkeypatch.setattr("vools.sys.dll_cmd._IS_WINDOWS", False)
        # 非 Windows 恒返回 None
        assert _find_dll_path("vools_crypto") is None


class TestSetupFuncs:
    """_setup_funcs 测试。"""

    def test_crypto(self):
        class FakeLib:
            pass
        lib = FakeLib()
        # 设置属性
        for fn in ["md5_hash", "sha1_hash", "sha256_hash", "hmac_sha256", "hmac_md5"]:
            setattr(lib, fn, lambda *a: b"")
        _setup_funcs(lib, "vools_crypto")
        assert lib.md5_hash.argtypes == [ctypes.c_char_p, ctypes.c_int]
        assert lib.md5_hash.restype == ctypes.c_char_p
        assert lib.hmac_sha256.argtypes == [ctypes.c_char_p, ctypes.c_int,
                                             ctypes.c_char_p, ctypes.c_int]

    def test_encoding(self):
        class FakeLib:
            pass
        lib = FakeLib()
        for fn in ["base64_encode", "base64_decode", "zlib_compress", "zlib_decompress"]:
            setattr(lib, fn, lambda *a: b"")
        _setup_funcs(lib, "vools_encoding")
        assert lib.base64_encode.argtypes == [ctypes.c_char_p, ctypes.c_int]
        assert lib.zlib_compress.argtypes == [ctypes.c_char_p, ctypes.c_int]

    def test_unknown_dll(self):
        class FakeLib:
            pass
        lib = FakeLib()
        # 未知 DLL 不设置任何签名，不崩溃
        _setup_funcs(lib, "vools_unknown")
        assert lib is not None


class TestDllCommands:
    """DllCommands 行为测试。"""

    def test_list_no_dlls(self, capsys, monkeypatch):
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: None)
        DllCommands().list()
        out = capsys.readouterr().out
        assert "可用 Nim DLL" in out
        assert "共 0 个可用 DLL" in out

    def test_list_with_dlls(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: str(tmp_path))
        monkeypatch.setattr("vools.sys.dll_cmd._IS_WINDOWS", True)
        (tmp_path / "vools_crypto.dll").write_bytes(b"x")
        DllCommands().list()
        out = capsys.readouterr().out
        assert "可用 Nim DLL" in out
        assert "✓ vools_crypto" in out
        assert "共 1 个可用 DLL" in out

    def test_dll_not_found(self, capsys, monkeypatch):
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: None)
        with pytest.raises(SystemExit) as e:
            DllCommands().dll("vools_crypto", "md5_hash", "hello")
        assert e.value.code == 1
        out = capsys.readouterr().out
        assert "未找到" in out

    def test_dll_cdll_error(self, capsys, monkeypatch, tmp_path):
        # 假 DLL 不是有效 Win32 程序 → ctypes.CDLL 会抛 OSError → 走到 except Exception 分支
        monkeypatch.setattr("vools.sys.dll_cmd._lib_dir", lambda: str(tmp_path))
        monkeypatch.setattr("vools.sys.dll_cmd._IS_WINDOWS", True)
        (tmp_path / "vools_crypto.dll").write_bytes(b"not a real dll")
        with pytest.raises(SystemExit):
            DllCommands().dll("vools_crypto", "md5_hash", "hello")
        out = capsys.readouterr().out
        assert "错误" in out

    def test_func_known(self, capsys):
        DllCommands().func("vools_crypto", "md5_hash")
        out = capsys.readouterr().out
        assert "vools_crypto 中的函数" in out
        assert "md5_hash" in out

    def test_func_unknown(self, capsys):
        with pytest.raises(SystemExit):
            DllCommands().func("unknown_dll", "f")
        out = capsys.readouterr().out
        assert "未知 DLL" in out


class TestNimDlls:
    """_NIM_DLLS 常量测试。"""

    def test_keys(self):
        for dll in ["vools_crypto", "vools_encoding", "vools_seq",
                     "vools_datetime", "vools_curried"]:
            assert dll in _NIM_DLLS

    def test_crypto_funcs(self):
        funcs = _NIM_DLLS["vools_crypto"]
        assert "md5_hash" in funcs
        assert "sha256_hash" in funcs
        assert "hmac_sha256" in funcs

    def test_encoding_funcs(self):
        funcs = _NIM_DLLS["vools_encoding"]
        assert "base64_encode" in funcs
        assert "zlib_compress" in funcs


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sys.dll_cmd import __all__
        assert "DllCommands" in __all__
