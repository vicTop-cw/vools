# -*- coding: utf-8 -*-
"""回归测试：uuid 类型注册与反序列化失败可见（BUG-332）。

`vools.serialize` 的 json 后端此前对 `uuid.UUID` **写读不对称**：
- `dumps(uuid, backend='json')` 成功（`vools_default` 写出通用 `__vools_obj__`
  标记，写入侧接受任何对象）；
- `loads(...)` 得到 **dict** `{'int': ...}` 而不是 UUID——因为
  `_import_class` 的模块白名单 `_ALLOWED_IMPORT_MODULES` 不含 `uuid`，
  且 `_reconstruct_object` 在 `cls is None` 时 `return state`（静默降级）。

修复：
1. `type_registry` 注册 `uuid.UUID`（`__vools_type__` 通道，`{'hex': ...}`，
   与 Decimal/date 同路径）→ json / vb_json / pickle 三后端均可往返；
2. `codec._reconstruct_object` 在无法导入类时抛 `ValueError`（说明类型名与
   白名单限制），不再静默返回内部 state。
"""

import uuid

import pytest

from vools.serialize import dumps, loads
from vools.serialize.codec import _reconstruct_object

UUID = uuid.UUID('12345678-1234-5678-1234-567812345678')


class TestUuidRoundTrip:
    @pytest.mark.parametrize('backend', ['json', 'vb_json', 'pickle'])
    def test_roundtrip(self, backend):
        back = loads(dumps(UUID, backend=backend), backend=backend)
        assert isinstance(back, uuid.UUID)
        assert back == UUID

    def test_nested(self):
        back = loads(dumps({'id': UUID, 'list': [UUID]}, backend='json'),
                     backend='json')
        assert isinstance(back['id'], uuid.UUID)
        assert isinstance(back['list'][0], uuid.UUID)

    def test_uuid4_roundtrip(self):
        u = uuid.uuid4()
        assert loads(dumps(u, backend='json'), backend='json') == u


class TestReconstructFailsLoudly:
    @pytest.mark.parametrize('type_name', [
        'uuidx.NotAllowed',
        'subprocess.Popen',
        '_io.FileIO',
        'not_a_module.Thing',
    ])
    def test_unimportable_raises_value_error(self, type_name):
        # 修复前：静默 return state（dict），调用方毫无察觉
        with pytest.raises(ValueError, match='白名单|无法还原'):
            _reconstruct_object(type_name, {})

    def test_registered_type_still_reconstructs(self):
        from vools.serialize.type_registry import get_type_deserializer
        assert get_type_deserializer('uuid.UUID') is not None
        assert get_type_deserializer('uuid.UUID')({'hex': UUID.hex}) == UUID

    def test_whitelisted_vools_class_still_reconstructed(self):
        from vools.cache.persist import FileLock
        assert isinstance(_reconstruct_object('vools.cache.persist.FileLock', {}),
                          FileLock)


class TestOtherTypesUnaffected:
    @pytest.mark.parametrize('backend', ['json', 'vb_json', 'pickle'])
    def test_stdlib_registry_types(self, backend):
        import datetime
        import decimal
        for obj in (datetime.date(2026, 1, 2), decimal.Decimal('1.25'),
                    {1, 2}, 1 + 2j):
            assert loads(dumps(obj, backend=backend), backend=backend) == obj