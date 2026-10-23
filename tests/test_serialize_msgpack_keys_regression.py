# -*- coding: utf-8 -*-
"""回归测试：msgpack 后端写读对称（非字符串键，BUG-379）。

`MsgpackBackend.dumps` 用 `msgpack.packb`，天然接受**非字符串键**（如
``{1: 'a'}``）；而 `loads` 调用 `msgpack.unpackb` 时未指定
``strict_map_key``，msgpack >= 1.0 默认 ``strict_map_key=True`` 会直接拒绝：

    dumps({1: 'a'}, backend='msgpack')   # 成功
    loads(..., backend='msgpack')
    # ValueError: int is not allowed for map key when strict_map_key=True

即「写得进去、读不回来」的不对称。修复：读取端显式
``strict_map_key=False``（并对旧版 msgpack 无该参数的情况做退化）。

字符串键与其它类型的行为不变；坏数据仍抛 FormatError。
"""

import pytest

from vools.serialize import MSGPACK_AVAILABLE, dumps, loads

pytestmark = pytest.mark.skipif(not MSGPACK_AVAILABLE, reason='msgpack 未安装')


def _rt(obj):
    return loads(dumps(obj, backend='msgpack'), backend='msgpack')


class TestNonStringKeys:
    def test_int_keys(self):
        # 修复前：ValueError: int is not allowed for map key ...
        assert _rt({1: 'a', 2: 'b'}) == {1: 'a', 2: 'b'}

    def test_float_keys(self):
        assert _rt({1.5: 'a'}) == {1.5: 'a'}

    def test_bool_keys(self):
        assert _rt({True: 'a'}) == {True: 'a'}

    def test_nested(self):
        assert _rt({'x': {1: 'a'}, 'y': [{2: 'b'}]}) == {'x': {1: 'a'}, 'y': [{2: 'b'}]}

    def test_mixed_keys(self):
        assert _rt({'s': 1, 2: 'b'}) == {'s': 1, 2: 'b'}


class TestStringKeysUnchanged:
    @pytest.mark.parametrize('obj', [
        {'a': 1}, {'a': {'b': [1, 2]}}, {'中': '文'},
        [1, 'a', None], b'\x00\xff', 'text', 42, 1.5, True, None,
    ])
    def test_roundtrip(self, obj):
        assert _rt(obj) == obj

    def test_registered_types(self):
        import datetime
        import decimal

        assert _rt(decimal.Decimal('1.5')) == decimal.Decimal('1.5')
        assert _rt(datetime.date(2026, 1, 2)) == datetime.date(2026, 1, 2)


class TestErrorsStillSurface:
    def test_bad_payload(self):
        with pytest.raises(Exception):
            loads(b'\xc1', backend='msgpack')
