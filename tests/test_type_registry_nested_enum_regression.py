# -*- coding: utf-8 -*-
"""回归测试：嵌套 enum 序列化/反序列化（BUG-204）。

_serialize_enum 原把 module 与嵌套 __qualname__ 拼成一个 'type' 串，
_deserialize_enum 用 rsplit('.', 1) 切开时误判模块路径，嵌套 enum
（__qualname__ 含 '.'，如 Outer.E）被 __import__ 抛 ModuleNotFoundError 崩溃。
修复：序列化额外输出 module / qualname 分开字段，反序列化优先按 module 精确
导入 + 逐级 getattr 沿 qualname 解析。
"""

import enum
import sys
import types

import pytest

from vools.serialize.type_registry import _deserialize_enum, _serialize_enum


class Outer:
    class E(enum.Enum):
        A = 1
        B = 2


# 挂到白名单前缀 'vools' 下的模块，避免 __main__ 被拒
_NESTED_MODULE_NAME = 'vools.test_nested_enum_regression'
_NESTED_MOD = types.ModuleType(_NESTED_MODULE_NAME)
Outer.E.__module__ = _NESTED_MODULE_NAME
_NESTED_MOD.Outer = Outer
sys.modules[_NESTED_MODULE_NAME] = _NESTED_MOD


class TestNestedEnumRoundTrip:
    """嵌套 enum 必须可 round-trip（BUG-204）。"""

    def test_serialize_has_separate_fields(self):
        state = _serialize_enum(Outer.E.A)
        assert state['module'] == _NESTED_MODULE_NAME
        assert state['qualname'] == 'Outer.E'
        assert state['name'] == 'A'

    def test_nested_round_trip(self):
        state = _serialize_enum(Outer.E.A)
        assert _deserialize_enum(state) is Outer.E.A

    def test_nested_second_member(self):
        state = _serialize_enum(Outer.E.B)
        assert _deserialize_enum(state) is Outer.E.B


class TestSimpleEnumStillWorks:
    """简单 enum（qualname 无 '.'）不受影响。"""

    def test_simple_round_trip(self):
        state = _serialize_enum(Outer.E.A)
        state['qualname'] = 'E'  # 模拟非嵌套
        mod = types.ModuleType('vools.test_flat_enum_regression')
        mod.E = Outer.E
        sys.modules['vools.test_flat_enum_regression'] = mod
        state['module'] = 'vools.test_flat_enum_regression'
        assert _deserialize_enum(state) is Outer.E.A


class TestInvalidEnumRejected:
    """非法 enum 仍被拒绝（BUG-96/BUG-100 白名单 + 类型校验）。"""

    def test_unknown_module_rejected(self):
        state = {
            'type': 'os.path.something',
            'module': 'os.path',
            'qualname': 'something',
            'name': 'A',
            'value': 1,
        }
        with pytest.raises(ValueError):
            _deserialize_enum(state)