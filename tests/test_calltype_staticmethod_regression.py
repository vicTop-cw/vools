# -*- coding: utf-8 -*-
"""回归测试：get_callable_type 跨模块 staticmethod 识别（BUG-274）。

原实现靠**调用栈帧扫描**找同名类来判断「通过类访问的 staticmethod」——
类不在当前帧的 locals/globals（如定义在另一模块）时必然识别失败，返回
CALLABLE_FUNCTION；帧内匹配还只比较方法名（不比较函数对象身份），
导致帧内存在同名静态方法的不同类时把普通函数误判为 STATICMETHOD。

修复：先用 obj.__qualname__ + obj.__globals__ 做确定性归属解析（跨模块可用），
<locals> 局部类回退栈扫描；栈兜底改为 `class_attr.__func__ is obj` 身份校验。
"""

import importlib.util
import os
import sys
import tempfile
import textwrap

import pytest

from vools.oop.calltype import CallableType, get_callable_type


_OTHER_SRC = textwrap.dedent('''
    class Other:
        @staticmethod
        def smake(x):
            return x

        def imake(self, x):
            return x

        @classmethod
        def cmake(cls, x):
            return x

    class Holder:
        @staticmethod
        def process(x):
            return ("static", x)

    def process(x):
        return ("plain", x)
''')


@pytest.fixture(scope='module')
def other_mod():
    fd, path = tempfile.mkstemp(suffix='.py', prefix='_ct_regression_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(_OTHER_SRC)
    spec = importlib.util.spec_from_file_location('_ct_regression_mod', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['_ct_regression_mod'] = mod
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop('_ct_regression_mod', None)
        try:
            os.unlink(path)
        except OSError:
            pass


class TestCrossModuleStaticmethod:
    def test_staticmethod_via_class(self, other_mod):
        # 修复前：跨模块时返回 CALLABLE_FUNCTION
        assert get_callable_type(other_mod.Other.smake) == \
            CallableType.CALLABLE_STATICMETHOD

    def test_instance_method_via_class_stays_function(self, other_mod):
        assert get_callable_type(other_mod.Other.imake) == \
            CallableType.CALLABLE_FUNCTION

    def test_classmethod(self, other_mod):
        assert get_callable_type(other_mod.Other.cmake) == \
            CallableType.CALLABLE_CLASSMETHOD

    def test_bound_instance_method(self, other_mod):
        assert get_callable_type(other_mod.Other().imake) == \
            CallableType.CALLABLE_INSTANCEMETHOD

    def test_class_itself(self, other_mod):
        assert get_callable_type(other_mod.Other) == \
            CallableType.CALLABLE_CLASS


class TestSameNameNoFalsePositive:
    def test_plain_function_not_mistaken(self, other_mod):
        # 模块级 process 与 Holder.process 同名：不得误判为 staticmethod
        assert get_callable_type(other_mod.process) == \
            CallableType.CALLABLE_FUNCTION

    def test_real_staticmethod_detected(self, other_mod):
        assert get_callable_type(other_mod.Holder.process) == \
            CallableType.CALLABLE_STATICMETHOD


class TestLocalClassFallback:
    def test_locals_staticmethod(self):
        class Local:
            @staticmethod
            def lmake(x):
                return x
        # <locals> 局部类走栈兜底，仍应识别
        assert get_callable_type(Local.lmake) == \
            CallableType.CALLABLE_STATICMETHOD

    def test_locals_plain_method(self):
        class Local2:
            def pmake(self):
                return 1
        assert get_callable_type(Local2.pmake) == \
            CallableType.CALLABLE_FUNCTION