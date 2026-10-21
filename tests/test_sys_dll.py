# -*- coding: utf-8 -*-
"""测试 vools.sys.dll 装饰器。"""

import os
import ctypes
import asyncio
import importlib
import pytest
from vools.sys.dll import dll, _get_executor

# vools.sys.__init__ L41 用 `from .dll import dll` 把名字 dll 绑定为装饰器函数，
# 遮蔽同名子模块 vools.sys.dll；因此「属性访问路径」（`import vools.sys.dll as m`、
# monkeypatch 字符串路径 `"vools.sys.dll._load_dll"`）会解析到 function 而非模块。
# 此处用 importlib.import_module 直取 sys.modules 中的真模块，绕过遮蔽。
DLL_MODULE = importlib.import_module("vools.sys.dll")

__all__ = ["TestMapPyToCtype", "TestConvertArg", "TestConvertResult",
           "TestParseDllSpec", "TestExtractAnnotations", "TestFunctionBodyIsPass",
           "TestDllSync", "TestDllFallback", "TestDllAsync", "TestImport"]


class TestMapPyToCtype:
    """_map_py_to_ctype 测试。"""

    def test_none(self):
        from vools.sys.dll import _map_py_to_ctype
        assert _map_py_to_ctype(None) is ctypes.c_int

    def test_int(self):
        from vools.sys.dll import _map_py_to_ctype
        assert _map_py_to_ctype(int) is ctypes.c_int

    def test_float(self):
        from vools.sys.dll import _map_py_to_ctype
        assert _map_py_to_ctype(float) is ctypes.c_double

    def test_str(self):
        from vools.sys.dll import _map_py_to_ctype
        assert _map_py_to_ctype(str) is ctypes.c_char_p

    def test_bytes(self):
        from vools.sys.dll import _map_py_to_ctype
        assert _map_py_to_ctype(bytes) is ctypes.c_char_p

    def test_bool(self):
        from vools.sys.dll import _map_py_to_ctype
        assert _map_py_to_ctype(bool) is ctypes.c_bool

    def test_unknown(self):
        from vools.sys.dll import _map_py_to_ctype
        assert _map_py_to_ctype(dict) is ctypes.c_int


class TestConvertArg:
    """_convert_arg 测试。"""

    def test_str_to_bytes(self):
        from vools.sys.dll import _convert_arg
        assert _convert_arg("hello", ctypes.c_char_p) == b"hello"

    def test_non_charp(self):
        from vools.sys.dll import _convert_arg
        assert _convert_arg("hello", ctypes.c_int) == "hello"

    def test_bytes_passthrough(self):
        from vools.sys.dll import _convert_arg
        assert _convert_arg(b"hi", ctypes.c_char_p) == b"hi"


class TestConvertResult:
    """_convert_result 测试。"""

    def test_bytes_to_str(self):
        from vools.sys.dll import _convert_result
        assert _convert_result(b"hi", ctypes.c_char_p, str) == "hi"

    def test_other_type(self):
        from vools.sys.dll import _convert_result
        assert _convert_result(b"hi", ctypes.c_char_p, None) == b"hi"


class TestParseDllSpec:
    """_parse_dll_spec 测试。"""

    def test_with_func(self):
        from vools.sys.dll import _parse_dll_spec
        assert _parse_dll_spec("a.dll::foo") == ("a.dll", "foo")

    def test_without_func(self):
        from vools.sys.dll import _parse_dll_spec
        assert _parse_dll_spec("a.dll") == ("a.dll", None)


class TestExtractAnnotations:
    """_extract_annotations 测试。"""

    def test_full(self):
        from vools.sys.dll import _extract_annotations

        def f(a: int, b: str) -> bool:
            pass

        arg_types, ret, params = _extract_annotations(f)
        assert arg_types == [int, str]
        assert ret is bool
        assert len(params) == 2

    def test_no_annotations(self):
        from vools.sys.dll import _extract_annotations

        def f(a, b):
            pass

        arg_types, ret, params = _extract_annotations(f)
        assert arg_types == [None, None]
        assert ret is None
        assert len(params) == 2


class TestFunctionBodyIsPass:
    """_function_body_is_pass 测试。"""

    def test_pass(self):
        from vools.sys.dll import _function_body_is_pass

        def f():
            pass

        assert _function_body_is_pass(f) is True

    def test_none(self):
        from vools.sys.dll import _function_body_is_pass

        def f():
            None

        assert _function_body_is_pass(f) is True

    def test_impl(self):
        from vools.sys.dll import _function_body_is_pass

        def f():
            return 1

        assert _function_body_is_pass(f) is False


class TestDllSync:
    """同步 dll 装饰器测试。"""

    def test_file_not_found_no_fallback(self):
        @dll("nonexistent.dll::foo")
        def foo():
            pass

        with pytest.raises(FileNotFoundError):
            foo()

    def test_file_not_found_with_fallback_func_body(self):
        @dll("nonexistent.dll::foo")
        def foo(a, b):
            return a + b

        assert foo(1, 2) == 3

    def test_file_not_found_with_explicit_fallback(self):
        @dll("nonexistent.dll::foo", fallback=lambda a, b: a * b)
        def foo(a, b):
            pass

        assert foo(3, 4) == 12

    def test_load_failure_fallback(self, monkeypatch):
        monkeypatch.setattr("os.path.exists", lambda p: True)
        monkeypatch.setattr(
            DLL_MODULE,
            "_load_dll",
            lambda p: (_ for _ in ()).throw(OSError("boom"))
        )

        @dll("x.dll::foo", fallback=lambda: "fb")
        def foo():
            pass

        assert foo() == "fb"

    def test_load_failure_no_fallback(self, monkeypatch):
        monkeypatch.setattr("os.path.exists", lambda p: True)
        monkeypatch.setattr(
            DLL_MODULE,
            "_load_dll",
            lambda p: (_ for _ in ()).throw(OSError("boom"))
        )

        @dll("x.dll::foo")
        def foo():
            pass

        with pytest.raises(OSError):
            foo()

    def test_success_int(self, monkeypatch, tmp_path):
        # 创建真实 DLL？Windows 没有 gcc。用假 _load_dll 返回带 func 的对象。
        dll_file = tmp_path / "lib.dll"
        dll_file.write_bytes(b"fake")
        monkeypatch.setattr("os.path.exists", lambda p: str(dll_file) in str(p))

        class FakeFunc:
            def __init__(self):
                self.argtypes = None
                self.restype = None
                self.called_with = None

            def __call__(self, *a):
                self.called_with = a
                return 7

        fake_func = FakeFunc()

        class FakeLib:
            def __getattr__(self, name):
                return fake_func

        monkeypatch.setattr(DLL_MODULE, "_load_dll", lambda p: FakeLib())

        @dll(f"{dll_file}::add")
        def add(a: int, b: int) -> int:
            pass

        assert add(3, 5) == 7
        assert fake_func.argtypes == [ctypes.c_int, ctypes.c_int]
        assert fake_func.restype is ctypes.c_int

    def test_kwargs_binding(self, monkeypatch, tmp_path):
        dll_file = tmp_path / "lib.dll"
        dll_file.write_bytes(b"fake")
        monkeypatch.setattr("os.path.exists", lambda p: str(dll_file) in str(p))

        calls = []

        def fake_load(p):
            class FakeLib:
                def __getattr__(self, name):
                    def _f(*a):
                        calls.append(a)
                        return a[0] + a[1]
                    return _f
            return FakeLib()

        monkeypatch.setattr(DLL_MODULE, "_load_dll", fake_load)

        @dll(f"{dll_file}::add")
        def add(a: int, b: int) -> int:
            pass

        assert add(b=2, a=3) == 5


class TestDllAsync:
    """异步 dll 装饰器测试。"""

    def test_async_file_not_found_no_fallback(self):
        @dll("nonexistent.dll::foo", async_mode=True)
        async def foo():
            pass

        with pytest.raises(FileNotFoundError):
            asyncio.run(foo())

    def test_async_with_fallback(self):
        @dll("nonexistent.dll::foo", async_mode=True)
        async def foo(a):
            return a + 1

        assert asyncio.run(foo(1)) == 2

    def test_async_success(self, monkeypatch, tmp_path):
        dll_file = tmp_path / "lib.dll"
        dll_file.write_bytes(b"fake")
        monkeypatch.setattr("os.path.exists", lambda p: str(dll_file) in str(p))

        def fake_load(p):
            class FakeLib:
                def __getattr__(self, name):
                    def _f(a):
                        return a * 2
                    return _f
            return FakeLib()

        monkeypatch.setattr(DLL_MODULE, "_load_dll", fake_load)

        @dll(f"{dll_file}::foo", async_mode=True)
        async def foo(a: int) -> int:
            pass

        assert asyncio.run(foo(21)) == 42


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        m = DLL_MODULE
        assert m.__all__ == ["dll"]

    def test_executor(self):
        assert _get_executor() is not None
