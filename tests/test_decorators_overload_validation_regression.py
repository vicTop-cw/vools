# -*- coding: utf-8 -*-
"""回归测试：@overload 的 mode / register 参数校验（BUG-475）。

修复前：

    overload(mode='x')(f)     # TypeError: unsupported operand type(s) for &: 'str' and 'OverloadMode'
    overload(mode=None)(f)    # 同上（NoneType）
    add.register(123)         # AttributeError: 'int' object has no attribute '__name__'
    add.register('x')         # AttributeError: 'str' object has no attribute '__name__'

修复后均为带参数名的 TypeError。合法模式（含 `mode=0` 与各 IntFlag 组合）、
文档用法（`@overload(mode=Priority|AllowSyncName|Strict|Ambiguous)` + 异名
`@add.register`）完全不变。
"""

import importlib

import pytest

_mod = importlib.import_module("vools.decorators.overload")
overload = _mod.overload
Priority, AllowSyncName, Strict, Ambiguous = (
    _mod.Priority, _mod.AllowSyncName, _mod.Strict, _mod.Ambiguous)


class TestModeValidation:
    @pytest.mark.parametrize("bad", ["x", None, 1.5, True, [1]])
    def test_non_int_mode(self, bad):
        with pytest.raises(TypeError) as ei:
            overload(mode=bad)(lambda x: x)
        assert "mode" in str(ei.value)

    @pytest.mark.parametrize("mode", [
        Priority, Strict, Priority | Strict, 0,
        Priority | AllowSyncName | Strict | Ambiguous,
    ])
    def test_valid_modes_accepted(self, mode):
        mgr = overload(mode=mode)(lambda x: x)
        assert type(mgr).__name__ == "OverloadManager"


class TestRegisterValidation:
    @pytest.mark.parametrize("bad", [123, "x", None if False else [1], 1.5])
    def test_non_callable_rejected(self, bad):
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def fn(a):
            return a

        with pytest.raises(TypeError) as ei:
            fn.register(bad)
        assert "可调用" in str(ei.value) or "callable" in str(ei.value)

    def test_valid_registration(self):
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def fn(a):
            return "main"

        assert callable(fn.register(lambda a: "other"))


class TestDocumentedUsageUnchanged:
    def test_type_dispatch(self):
        @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register
        def add_int(a: int, b: int):
            return a + b

        assert add(1, 2) == 3
        assert add("a", "b") == "ab"

    def test_unmatched_is_loud(self):
        @overload(mode=Priority | AllowSyncName | Strict)
        def only_int(x: int):
            return x * 2

        with pytest.raises(TypeError):
            only_int("a")

    def test_no_annotation_handles_all(self):
        @overload(mode=Priority | AllowSyncName | Strict)
        def any_fn(x):
            return "any"

        assert any_fn(1) == "any"
        assert any_fn("a") == "any"
