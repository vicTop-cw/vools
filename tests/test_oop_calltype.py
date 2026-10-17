# -*- coding: utf-8 -*-
"""测试 vools.oop.calltype — CallableType / get_callable_type / create_fake。"""

import inspect
import pytest

from vools.oop.calltype import CallableType, get_callable_type, create_fake

__all__ = ["TestCallableTypeEnum", "TestGetCallableType",
           "TestCreateFake", "TestImport"]


class TestCallableTypeEnum:
    """CallableType 枚举。"""

    def test_values(self):
        assert CallableType.CALLABLE_CLASS.value == 0
        assert CallableType.CALLABLE_CLASSMETHOD.value == 1
        assert CallableType.CALLABLE_INSTANCEMETHOD.value == 2
        assert CallableType.CALLABLE_STATICMETHOD.value == 3
        assert CallableType.CALLABLE_FUNCTION.value == 4
        assert CallableType.CALLABLE_INSTANCE.value == 5
        assert CallableType.NOT_CALLABLE_INSTANCE_ATTR.value == 6
        assert CallableType.NOT_CALLABLE_INSTANCE.value == 7
        assert CallableType.UNKNOWN.value == -1

    def test_iter(self):
        values = list(CallableType)
        assert len(values) >= 8


class TestGetCallableType:
    """get_callable_type 测试。"""

    class Sample:
        attr = 10

        def instance_method(self):
            pass

        @classmethod
        def class_method(cls):
            pass

        @staticmethod
        def static_method():
            pass

    class CallableInstance:
        def __call__(self):
            pass

    def test_class(self):
        assert get_callable_type(TestGetCallableType.Sample) == CallableType.CALLABLE_CLASS

    def test_classmethod(self):
        assert get_callable_type(TestGetCallableType.Sample.class_method) == CallableType.CALLABLE_CLASSMETHOD

    def test_instancemethod(self):
        obj = TestGetCallableType.Sample()
        assert get_callable_type(obj.instance_method) == CallableType.CALLABLE_INSTANCEMETHOD

    def test_staticmethod(self):
        assert get_callable_type(TestGetCallableType.Sample.static_method) == CallableType.CALLABLE_STATICMETHOD

    def test_function(self):
        def f():
            pass
        assert get_callable_type(f) == CallableType.CALLABLE_FUNCTION

    def test_lambda(self):
        assert get_callable_type(lambda x: x) == CallableType.CALLABLE_FUNCTION

    def test_callable_instance(self):
        obj = TestGetCallableType.CallableInstance()
        assert get_callable_type(obj) == CallableType.CALLABLE_INSTANCE

    def test_builtin(self):
        assert get_callable_type(len) == CallableType.CALLABLE_FUNCTION

    def test_not_callable_attr(self):
        obj = TestGetCallableType.Sample()
        assert get_callable_type(obj.attr) == CallableType.NOT_CALLABLE_INSTANCE_ATTR

    def test_not_callable_instance(self):
        class NotCallable:
            pass
        obj = NotCallable()
        # NotCallable 是模块内类，非 builtins → NOT_CALLABLE_INSTANCE
        assert get_callable_type(obj) == CallableType.NOT_CALLABLE_INSTANCE

    def test_int(self):
        assert get_callable_type(123) == CallableType.NOT_CALLABLE_INSTANCE_ATTR

    def test_string(self):
        assert get_callable_type("hello") == CallableType.NOT_CALLABLE_INSTANCE_ATTR

    def test_list(self):
        assert get_callable_type([]) == CallableType.NOT_CALLABLE_INSTANCE_ATTR

    def test_dict(self):
        assert get_callable_type({}) == CallableType.NOT_CALLABLE_INSTANCE_ATTR

    def test_none(self):
        assert get_callable_type(None) == CallableType.NOT_CALLABLE_INSTANCE_ATTR

    def test_bool(self):
        assert get_callable_type(True) == CallableType.NOT_CALLABLE_INSTANCE_ATTR

    def test_module_static(self):
        # 模块级静态方法通过函数调用栈查找
        class Outer:
            @staticmethod
            def static2():
                pass
        assert get_callable_type(Outer.static2) == CallableType.CALLABLE_STATICMETHOD


class TestCreateFake:
    """create_fake 测试。"""

    def test_returns_wrapper(self):
        def target(a, b=1, *, c=None):
            return a + b

        wrapper = create_fake(target)
        assert callable(wrapper)
        assert wrapper.__name__ == "target"

    def test_signature_preserved(self):
        def target(a, b=1, *, c=None):
            return a + b

        wrapper = create_fake(target)
        sig = inspect.signature(wrapper)
        names = list(sig.parameters.keys())
        assert names == ["a", "b", "c"]
        assert sig.parameters["b"].default == 1

    def test_returns_callable_type(self):
        class Sample:
            pass

        wrapper = create_fake(Sample)
        assert wrapper() == CallableType.CALLABLE_CLASS

    def test_invalid_sig(self):
        # 传入不可 inspect 的对象，走 except 分支
        class Obj:
            pass
        wrapper = create_fake(Obj)
        assert wrapper() == CallableType.CALLABLE_CLASS

    def test_none(self):
        wrapper = create_fake(None)
        assert wrapper() == CallableType.NOT_CALLABLE_INSTANCE_ATTR


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.oop.calltype import __all__
        assert "CallableType" in __all__
        assert "get_callable_type" in __all__
        assert "create_fake" in __all__
