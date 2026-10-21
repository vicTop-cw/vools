# -*- coding: utf-8 -*-
"""回归测试：overload/strict 兼容 PEP 563 字符串注解（BUG-273）。

`from __future__ import annotations` 下注解是字符串；原实现直接读
``func.__annotations__`` 并传给 isinstance → 每次分派抛
``TypeError: isinstance() arg 2 must be a type, a tuple of types, or a union``：
- `@overload(mode=...|Strict|...)` 的任何调用都崩溃；
- `@strict` 装饰的函数任何调用都崩溃。

修复：`_resolve_annotations(func)`（get_type_hints 优先、失败回退原始注解、
剔除仍为字符串的项）供两处使用，无法解析的注解按「不限制」降级而非崩溃。

本测试通过临时模块注入 `from __future__ import annotations` 复现（当前文件
本身不能带该 future，否则本文件其他断言也会被字符串化）。
"""

import importlib.util
import os
import sys
import tempfile
import textwrap

import pytest


def _load_future_module(src: str, name: str):
    fd, path = tempfile.mkstemp(suffix='.py', prefix=f'_{name}_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(src)
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.modules.pop(name, None)
        return mod
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


_SRC = textwrap.dedent('''
    from __future__ import annotations
    from vools.decorators.overload import (
        overload, Strict, Priority, AllowSyncName, Ambiguous, strict)

    @overload(mode=Priority | Strict | AllowSyncName | Ambiguous)
    def add(a, b):
        return "base"

    @add.register
    def add_int(a: int, b: int):
        return "int"

    @add.register
    def add_str(a: str, b: str):
        return "str"

    @strict
    def typed(a: int, b: str) -> str:
        return f"{a}-{b}"
''')


@pytest.fixture(scope='module')
def future_mod():
    return _load_future_module(_SRC, '_pep563_regression_mod')


class TestOverloadUnderPep563:
    def test_int_call_no_crash(self, future_mod):
        # 修复前：TypeError: isinstance() arg 2 must be a type...
        assert future_mod.add(1, 2) in ('base', 'int')

    def test_str_call_no_crash(self, future_mod):
        assert future_mod.add('a', 'b') in ('base', 'str')


class TestStrictUnderPep563:
    def test_valid_call(self, future_mod):
        assert future_mod.typed(1, 'x') == '1-x'

    def test_type_violation_still_raises(self, future_mod):
        with pytest.raises(TypeError):
            future_mod.typed('1', 'x')


class TestResolveAnnotationsHelper:
    def test_resolves_string_annotations(self, future_mod):
        from vools.decorators.overload import _resolve_annotations
        ann = _resolve_annotations(future_mod.typed)
        assert ann.get('a') is int
        assert ann.get('b') is str
        assert ann.get('return') is str

    def test_filters_unresolvable_strings(self):
        from vools.decorators.overload import _resolve_annotations

        def f(x: 'NotDefinedAnywhere'):  # noqa: F821 字符串前向引用
            return x

        ann = _resolve_annotations(f)
        # 不可解析的字符串注解被剔除（降级为不限制，避免 isinstance 崩溃）
        assert 'x' not in ann