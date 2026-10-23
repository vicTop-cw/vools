# -*- coding: utf-8 -*-
"""回归测试：公开 API docstring 不得混入无关的 do() 样板代码（BUG-318）。

四处 docstring 的「用法示例」段落被复制粘贴事故污染——混入了来自其它模块的
`do(self, f=print, pre_f=None, sub_f=None)` 方法体，导致：

- `serializable` 示例看不到真正的类级 serialize/deserialize 用法；
- `serialize_method` / `deserialize_method` 的装饰器用法行**悬空断裂**
  （`@serialize_method` 后直接跟 `def do(...)`）；
- `curry_class` 的链式柯里化示例被样板代码隔断。

本测试锁定 docstring 干净 + 示例描述的行为真实成立。
"""

import inspect

import pytest

from vools.decorators.curry_decorator import curry_class
from vools.serialize import Serializer
from vools.serialize.decorators import (
    deserialize_method,
    serializable,
    serialize_method,
)

_POLLUTING_MARKERS = ('pre_f', 'sub_f', 'Apply a function for side effects')


@pytest.mark.parametrize('obj', [
    serializable, serialize_method, deserialize_method, curry_class,
])
def test_docstring_not_polluted(obj):
    doc = inspect.getdoc(obj) or ''
    for marker in _POLLUTING_MARKERS:
        assert marker not in doc, f'{obj.__name__} docstring 混入样板片段: {marker!r}'


class TestDocumentedBehaviour:
    def test_serializable_example(self):
        @serializable(backend='pickle')
        class MyData:
            def __init__(self, name):
                self.name = name

        data = MyData.serialize(MyData('abc'))
        assert isinstance(data, (bytes, bytearray))
        assert MyData.deserialize(data).name == 'abc'

    def test_serialize_method_example(self):
        class MyService:
            @serialize_method(backend='json')
            def get_state(self):
                return {'status': 'ok'}

        raw = MyService().get_state()
        assert isinstance(raw, (bytes, bytearray))
        assert Serializer(backend='json').loads(raw) == {'status': 'ok'}

    def test_deserialize_method_example(self):
        class MyService:
            @deserialize_method(backend='json')
            def update_state(self, state):
                self._state = state

        svc = MyService()
        svc.update_state(b'{"status": "ok"}')
        assert svc._state == {'status': 'ok'}

    def test_curry_class_example(self):
        @curry_class
        class T:
            def add(self, a, b, c):
                return a + b + c

            def sum_all(self, a, b, *c, **k):
                total = a + b + sum(c)
                if k:
                    total += sum(k.values())
                return total

        assert T().add(1).add(2).add(3) == 6
        assert T().sum_all(1).sum_all(2).sum_all(3, 4) == 10