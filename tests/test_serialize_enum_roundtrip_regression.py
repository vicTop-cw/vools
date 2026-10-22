# -*- coding: utf-8 -*-
"""回归测试：类型注册表 enum 往返（BUG-310）。

原实现两处缺陷：
A) `_deserialize_enum` 用 value 还原 → JSON 无 tuple 概念，tuple 值被编码成
   list，`cls([1, 2])` 找不到成员：`ValueError: [1, 2] is not a valid TupleE`。
   修复：优先按 `name` 还原（`_serialize_enum` 早已保存 name），缺失时回退 value。
B) vb_json 的 `_stringify` 把 `isinstance(obj, (int, float))` 放在类型注册表
   之前 → IntEnum/IntFlag（int 子类）被静默降级成普通 int（值对、类型丢）。
   修复：`isinstance(obj, enum.Enum)` 检查提前到数字分支之前。

本测试锁定两端行为，并覆盖 str 子类枚举与旧 payload（无 name）兼容路径。
"""

import enum

import pytest

from vools.serialize import dumps, loads

BACKENDS = ['json', 'vb_json', 'pickle']


class TupleEnum(enum.Enum):
    PAIR = (1, 2)
    TRIPLE = (1, 2, 3)


class ComplexEnum(enum.Enum):
    Z = 1 + 2j


class IntFlagEnum(enum.IntEnum):
    A = 1
    B = 2


class StrEnum(str, enum.Enum):
    X = 'x'



class PlainIntEnum(enum.Enum):
    ONE = 1


class TestEnumRoundTrip:
    @pytest.mark.parametrize('backend', BACKENDS)
    @pytest.mark.parametrize('member', [
        TupleEnum.PAIR, TupleEnum.TRIPLE,
        ComplexEnum.Z,
        IntFlagEnum.A, IntFlagEnum.B,
        StrEnum.X,
        PlainIntEnum.ONE,
    ])
    def test_roundtrip_preserves_type(self, backend, member):
        back = loads(dumps(member, backend=backend), backend=backend)
        # 类型必须完整保留（缺陷 B 的回归点：IntEnum 不能被降级成 int）
        assert type(back) is type(member)
        assert back is member

    @pytest.mark.parametrize('backend', BACKENDS)
    def test_tuple_value_enum(self, backend):
        # 缺陷 A 的回归点：json/vb_json 曾抛 ValueError: [1, 2] is not a valid
        back = loads(dumps(TupleEnum.PAIR, backend=backend), backend=backend)
        assert back is TupleEnum.PAIR
        assert back.value == (1, 2)

    @pytest.mark.parametrize('backend', BACKENDS)
    def test_enum_inside_containers(self, backend):
        obj = {'m': TupleEnum.TRIPLE, 'list': [IntFlagEnum.B, StrEnum.X]}
        back = loads(dumps(obj, backend=backend), backend=backend)
        assert back['m'] is TupleEnum.TRIPLE
        assert back['list'][0] is IntFlagEnum.B
        assert back['list'][1] is StrEnum.X


class TestLegacyPayloadFallback:
    def test_payload_without_name_falls_back_to_value(self):
        # 旧 payload（无 name 字段）必须仍可用 value 还原
        from vools.serialize.type_registry import _deserialize_enum
        state = {
            'type': f'{__name__}.PlainIntEnum',
            'module': __name__,
            'qualname': 'PlainIntEnum',
            'value': 1,
        }
        assert _deserialize_enum(state) is PlainIntEnum.ONE

    def test_payload_with_name_takes_priority(self):
        from vools.serialize.type_registry import _deserialize_enum
        state = {
            'type': f'{__name__}.TupleEnum',
            'module': __name__,
            'qualname': 'TupleEnum',
            'name': 'PAIR',
            'value': [1, 2],   # JSON 化后的 list：只有 name 才能正确还原
        }
        assert _deserialize_enum(state) is TupleEnum.PAIR