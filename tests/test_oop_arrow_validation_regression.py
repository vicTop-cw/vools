# -*- coding: utf-8 -*-
"""回归测试：arrow_func 安全警告缺失 + clone/arrow_func 入参校验（BUG-514）。

## 安全文档缺口（本轮核心）

``vools/functional/arrow_func.py`` 里并存两个入口：

* ``arrow_func``：把 expr 当**完整 Python** 编译执行（``env`` 默认带完整
  ``__builtins__``）——实测 ``arrow_func("x => __import__('os')")`` 直接返回
  os 模块（任意代码执行）；
* ``safe_arrow_func``：白名单 AST 沙箱，实测拦截 ``__import__``/``open``/``eval``。

问题：**安全警告只写在 safe 版文档里**，``arrow_func`` 自己的 docstring 没有任何
警告，而它还被 ``vools.oop`` 再导出一层，用户落在错误入口时完全看不出风险。

修复：在 ``arrow_func`` docstring 补 ⚠️ 安全警告 + Raises，并指引改用
``safe_arrow_func``。

## 入参校验

    arrow_func(123)      # AttributeError: 'int' object has no attribute 'strip'
    safe_arrow_func(123) # 同上
    clone(123)           # AttributeError: 'int' object has no attribute '__name__'
"""

import importlib

import pytest

import vools.oop as oop

af = importlib.import_module("vools.functional.arrow_func")


class TestArrowFuncSecurityDocumentation:
    def test_unsafe_variant_documents_the_risk(self):
        doc = af.arrow_func.__doc__ or ""
        assert "安全警告" in doc
        assert "safe_arrow_func" in doc
        assert "__import__" in doc

    def test_safe_variant_exists_and_blocks_import(self):
        from vools.security.safe_eval import SafeEvalError

        with pytest.raises(SafeEvalError):
            af.safe_arrow_func("x => __import__('os')")(1)

    def test_safe_variant_blocks_builtins(self):
        with pytest.raises(Exception):
            af.safe_arrow_func("x => globals()")(1)

    def test_safe_variant_normal_use(self):
        assert af.safe_arrow_func("x => x * 2")(21) == 42


class TestArrowFuncValidation:
    @pytest.mark.parametrize("bad", [123, None, [1]])
    def test_unsafe_expr_type(self, bad):
        with pytest.raises(TypeError) as ei:
            af.arrow_func(bad)
        assert "expr" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None])
    def test_safe_expr_type(self, bad):
        with pytest.raises(TypeError) as ei:
            af.safe_arrow_func(bad)
        assert "expr" in str(ei.value)


class TestArrowFuncSemanticsUnchanged:
    def test_single_param(self):
        assert af.arrow_func("x => x + 1")(2) == 3

    def test_multi_param_comma_syntax(self):
        assert af.arrow_func("x, y => x * y")(2, 3) == 6

    def test_varargs(self):
        assert af.arrow_func("*args => sum(args)")(1, 2, 3) == 6

    def test_env(self):
        assert af.arrow_func("x => x + base", {"base": 10})(1) == 11


class TestCloneValidation:
    @pytest.mark.parametrize("bad", [123, "x", [1]])
    def test_non_class(self, bad):
        with pytest.raises(TypeError) as ei:
            oop.clone(bad)
        assert "cls" in str(ei.value)

    def test_none_returns_decorator(self):
        assert callable(oop.clone())

    def test_clone_class(self):
        class Base:
            count = 1

        assert oop.clone(Base) is not Base
        assert oop.clone(Base, "count:5").count == 5
