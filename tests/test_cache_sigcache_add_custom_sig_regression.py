# -*- coding: utf-8 -*-
"""回归测试：add_custom_sig 返回是否生效（BUG-472）。

``force=False`` 时若该可调用对象**已有缓存**，``add_custom_sig`` 会按文档
"不覆盖"语义跳过——但原实现返回 ``None``，调用方无法区分"已注册"与
"被既有缓存挡下"（只有 DEBUG 日志能看出）。

修复后返回 bool：True=本次写入生效，False=被既有缓存挡下（未生效）。
行为与校验保持不变（``force=True`` 覆盖、非法 sig/非可调用各自响亮报错）。
"""

import inspect

import pytest

import vools.cache as ca


def _sig(*names):
    return inspect.Signature(
        [inspect.Parameter(n, inspect.Parameter.POSITIONAL_OR_KEYWORD) for n in names])


def _fresh_func():
    """每次返回全新的函数对象（缓存键是 id(func)）。"""
    def target(a):
        return a
    return target


class TestReturnValue:
    def test_registered_returns_true(self):
        f = _fresh_func()
        try:
            assert ca.add_custom_sig(f, _sig("x", "y")) is True
            assert str(ca.get_signature(f)) == "(x, y)"
        finally:
            ca.remove_signature(f)

    def test_cached_without_force_returns_false(self):
        f = _fresh_func()
        try:
            ca.get_signature(f)                       # 先把真实签名写入缓存
            assert ca.add_custom_sig(f, _sig("p", "q")) is False
            assert str(ca.get_signature(f)) == "(a)"  # 未生效（文档语义）
        finally:
            ca.remove_signature(f)

    def test_force_overrides(self):
        f = _fresh_func()
        try:
            ca.get_signature(f)
            assert ca.add_custom_sig(f, _sig("p", "q"), force=True) is True
            assert str(ca.get_signature(f)) == "(p, q)"
        finally:
            ca.remove_signature(f)

    def test_remove_falls_back_to_real_signature(self):
        f = _fresh_func()
        ca.add_custom_sig(f, _sig("only"), force=True)
        assert str(ca.get_signature(f)) == "(only)"
        assert ca.remove_signature(f) is True
        assert str(ca.get_signature(f)) == "(a)"


class TestValidationUnchanged:
    def test_non_callable(self):
        with pytest.raises(TypeError):
            ca.add_custom_sig(123, _sig("x"))

    def test_bad_signature_type(self):
        with pytest.raises(ValueError):
            ca.add_custom_sig(_fresh_func(), "not-a-signature")

    def test_remove_unknown_returns_false(self):
        assert ca.remove_signature(_fresh_func()) is False


class TestNoCrossContamination:
    def test_two_functions_independent(self):
        f1 = _fresh_func()
        f2 = _fresh_func()
        try:
            ca.add_custom_sig(f1, _sig("only"), force=True)
            assert str(ca.get_signature(f1)) == "(only)"
            assert str(ca.get_signature(f2)) == "(a)"
        finally:
            ca.remove_signature(f1)
            ca.remove_signature(f2)
