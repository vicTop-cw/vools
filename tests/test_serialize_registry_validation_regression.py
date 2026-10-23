# -*- coding: utf-8 -*-
"""回归测试：serialize 的三个注册入口参数校验（BUG-399）。

与 encoding/crypto 注册表（BUG-398）同族，`vools.serialize` 里同样存在
「裸字典/裸全局变量赋值」：

1. `set_default_backend('nope_backend')` / `set_default_backend(123)`
   → 原实现接受任意值并写入全局默认，直到下次 `dumps()` 才抛
   `ValueError: Unknown backend`（或更奇怪的错误）；
2. `register_backend(123, cls)` / `register_backend('x', object())`
   → 零校验，任意对象都能"注册成功"；同名覆盖内置后端也无声；
3. `register_type('not-a-class')` → 裸 `AttributeError: 'str' object has no
   attribute '__module__'`；`serialize='nope'`（不可调用）也能注册成功，
   直到 dumps 时才炸；`name` 非 str 同样不校验。

修复：三个入口统一显式校验（名称非空 str / 类型是类 / 函数可调用），
同名覆盖发 RuntimeWarning。既有 BUG-325（同名不同类型 ValueError）与正常
注册/往返行为不变。
"""

import warnings

import pytest

from vools.serialize import (
    dumps,
    get_default_backend,
    loads,
    register_type,
    set_default_backend,
)
from vools.serialize.backends import get_backend, register_backend


@pytest.fixture(autouse=True)
def _restore_default_backend():
    yield
    set_default_backend(None)


class TestSetDefaultBackend:
    @pytest.mark.parametrize('bad', ['nope_backend', '', 123, object()])
    def test_invalid_rejected(self, bad):
        with pytest.raises(ValueError):
            set_default_backend(bad)

    def test_valid(self):
        set_default_backend('json')
        assert get_default_backend() == 'json'
        set_default_backend(None)
        assert get_default_backend() is None

    def test_builtins_usable(self):
        for name in ('json', 'pickle'):
            assert get_backend(name) is not None


class TestRegisterBackend:
    @pytest.mark.parametrize('bad_name', [123, '', '   ', None])
    def test_bad_name(self, bad_name):
        class B:
            def dumps(self, o):
                return b''

            def loads(self, d):
                return None

        with pytest.raises(ValueError):
            register_backend(bad_name, B)

    @pytest.mark.parametrize('bad_cls', [object(), 'str', 42])
    def test_bad_class(self, bad_cls):
        with pytest.raises(TypeError):
            register_backend('some_name', bad_cls)

    def test_valid_and_overwrite_warns(self):
        class B1:
            def dumps(self, o):
                return b'1'

            def loads(self, d):
                return None

        class B2:
            def dumps(self, o):
                return b'2'

            def loads(self, d):
                return None

        register_backend('probe_backend', B1)
        assert get_backend('probe_backend') is B1
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            register_backend('probe_backend', B2)
        assert caught
        assert get_backend('probe_backend') is B2


class TestRegisterType:
    @pytest.mark.parametrize('bad', ['not-a-class', 42, object()])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError):
            register_type(bad)

    def test_bad_name(self):
        class C:
            pass

        with pytest.raises(TypeError):
            register_type(C, name=123, serialize=lambda o: {},
                          deserialize=lambda d: C())
        with pytest.raises(ValueError):
            register_type(C, name='', serialize=lambda o: {},
                          deserialize=lambda d: C())

    def test_non_callable_handlers(self):
        class C:
            pass

        with pytest.raises(TypeError):
            register_type(C, serialize='nope', deserialize=lambda d: C())
        with pytest.raises(TypeError):
            register_type(C, serialize=lambda o: {}, deserialize=42)

    def test_missing_handlers(self):
        class C:
            pass

        with pytest.raises(ValueError):
            register_type(C, deserialize=lambda d: C())

    def test_normal_roundtrip(self):
        class V:
            def __init__(self, v):
                self.v = v

        register_type(V, name='_probe_reg_v',
                      serialize=lambda o: {'v': o.v},
                      deserialize=lambda d: V(d['v']))
        assert loads(dumps(V(7), backend='json'), backend='json').v == 7

    def test_default_name_works(self):
        class W:
            def __init__(self, v):
                self.v = v

        register_type(W, serialize=lambda o: {'v': o.v},
                      deserialize=lambda d: W(d['v']))
        assert loads(dumps(W(9), backend='json'), backend='json').v == 9

    def test_same_name_different_type_still_rejected(self):
        # BUG-325 既有契约
        class V2:
            pass

        with pytest.raises(ValueError):
            register_type(V2, name='_probe_reg_v',
                          serialize=lambda o: {}, deserialize=lambda d: V2())