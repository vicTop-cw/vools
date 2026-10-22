# -*- coding: utf-8 -*-
"""回归测试：vb_json 后端对未知类型显式报错而非静默 null（BUG-303）。

`VBJsonBackend._stringify` 末尾原为 `return 'null'`——任何不支持的类型
（uuid、自定义对象等）被静默序列化成 null：
- dumps(uuid, backend='vb_json') 成功 -> loads 得到 **None**（数据无声丢失）
- 嵌套场景 {'id': uuid} -> {'id': null}（字段静默变空）
而同库 json 后端对自定义对象抛 TypeError、pickle 后端完整往返。

修复：末尾改为 raise TypeError（消息含类型名与可选后端建议）；None 由开头
显式分支处理，合法空值不受影响。

注（BUG-309）：内置注册类型（datetime/date/set/Decimal/complex）与
`register_type` 自定义类型现已经类型注册表支持，不再落入"未知类型"分支——
它们应正确往返，故不在本测试的"必须报错"清单内（见
tests/test_serialize_vb_json_type_registry_regression.py）。
"""

import uuid

import pytest

from vools.serialize import dumps, loads


class _Custom:
    pass


class TestUnknownTypeRaises:
    @pytest.mark.parametrize('obj', [
        uuid.UUID('12345678-1234-5678-1234-567812345678'),
        _Custom(),
    ])
    def test_dumps_raises_type_error(self, obj):
        # 修复前：静默 'null'，loads 得 None
        with pytest.raises(TypeError):
            dumps(obj, backend='vb_json')

    def test_nested_unknown_raises(self):
        with pytest.raises(TypeError):
            dumps({'id': uuid.uuid4()}, backend='vb_json')

    def test_error_message_mentions_type(self):
        with pytest.raises(TypeError) as ei:
            dumps(uuid.uuid4(), backend='vb_json')
        assert 'UUID' in str(ei.value) or 'serializable' in str(ei.value)


class TestSupportedTypesRoundTrip:
    @pytest.mark.parametrize('obj', [
        42, 3.14, 'text', True, None,
        [1, 2, 3], {'a': 1, 'b': {'c': [1, None]}},
        [None, True, 'x'],
    ])
    def test_roundtrip(self, obj):
        assert loads(dumps(obj, backend='vb_json'), backend='vb_json') == obj

    def test_non_finite_float_still_supported(self):
        # BUG-203 修复面：非有限浮点仍输出标准字面量并正确往返
        got = loads(dumps(float('inf'), backend='vb_json'), backend='vb_json')
        assert got == float('inf')


class TestOtherBackendsUnchanged:
    def test_json_backend_still_raises(self):
        with pytest.raises(TypeError):
            dumps(_Custom(), backend='json')

    def test_pickle_backend_still_works(self):
        obj = _Custom()
        back = loads(dumps(obj, backend='pickle'), backend='pickle')
        assert type(back).__name__ == '_Custom'