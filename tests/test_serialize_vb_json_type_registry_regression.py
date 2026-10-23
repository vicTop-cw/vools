# -*- coding: utf-8 -*-
"""回归测试：vb_json 后端接入类型注册表（BUG-309）。

原 vb_json 后端的 `_stringify` 与 `parse` 完全未接入
`codec.vools_preprocess` / `vools_object_hook`，导致：
- `register_type` 注册的自定义类型在 vb_json 下 **dumps 抛 TypeError**
  （BUG-303 修复前更糟：静默 'null' → loads None）
- 内置注册类型（datetime/date/set/Decimal/complex）与 NONE 哨兵同样不可用
而 json/pickle 后端均正常 —— 两个 JSON 后端能力不对等。

修复：`_stringify` 未知类型分支先查 `vools_preprocess`（内置/注册类型标记），
再接受 `vools_default` 产出的**可还原**标记（`__vools_singleton__` /
`__vools_type__`）；`loads` 结果递归应用 `vools_object_hook`。未注册类型
（uuid/自定义对象）仍显式 TypeError，不静默丢数据（BUG-303 不回归）。
"""

import datetime
import decimal

import pytest

from vools.serialize import NONE, dumps, loads, register_type


class _Point:
    def __init__(self, x, y):
        self.x, self.y = x, y

    def __eq__(self, other):
        return isinstance(other, _Point) and (self.x, self.y) == (other.x, other.y)

    def __repr__(self):
        return f'_Point({self.x},{self.y})'


register_type(_Point, 'point',
              serialize=lambda p: {'x': p.x, 'y': p.y},
              deserialize=lambda s: _Point(s['x'], s['y']))


class TestRegisteredTypeRoundTrip:
    @pytest.mark.parametrize('backend', ['json', 'vb_json', 'pickle'])
    def test_custom_registered_type(self, backend):
        # 修复前 vb_json: TypeError（未注册前还会静默 null）
        back = loads(dumps(_Point(1, 2), backend=backend), backend=backend)
        assert isinstance(back, _Point)
        assert back == _Point(1, 2)


class TestBuiltinRegistryTypesRoundTrip:
    @pytest.mark.parametrize('backend', ['json', 'vb_json', 'pickle'])
    @pytest.mark.parametrize('obj', [
        datetime.date(2026, 1, 2),
        datetime.datetime(2026, 1, 2, 3, 4, 5),
        {1, 2, 3},
        decimal.Decimal('1.25'),
        1 + 2j,
    ])
    def test_roundtrip(self, backend, obj):
        assert loads(dumps(obj, backend=backend), backend=backend) == obj

    @pytest.mark.parametrize('backend', ['json', 'vb_json', 'pickle'])
    def test_none_sentinel(self, backend):
        # NONE 哨兵与 None 必须区分（NONE 走 singleton 标记，None 走 null）
        assert loads(dumps(NONE, backend=backend), backend=backend) is NONE
        assert loads(dumps(None, backend=backend), backend=backend) is None


class TestUnknownTypesStillRejected:
    def test_uuid_still_raises(self):
        # BUG-332: uuid 已加入类型注册表，vb_json 不再拒绝——改为验证可正确往返
        import uuid
        u = uuid.uuid4()
        data = dumps(u, backend='vb_json')
        result = loads(data, backend='vb_json')
        assert isinstance(result, uuid.UUID)
        assert result == u

    def test_custom_object_still_raises(self):
        class Plain:
            pass
        with pytest.raises(TypeError):
            dumps(Plain(), backend='vb_json')

    def test_nested_registered_type_inside_dict(self):
        obj = {'p': _Point(3, 4), 'date': datetime.date(2026, 5, 6)}
        back = loads(dumps(obj, backend='vb_json'), backend='vb_json')
        assert back['p'] == _Point(3, 4)
        assert back['date'] == datetime.date(2026, 5, 6)