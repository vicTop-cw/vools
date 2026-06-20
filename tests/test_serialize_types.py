"""
vools.serialize 类型注册表测试

验证 datetime、set、complex、Decimal 等 Python 标准类型
可以通过 json/msgpack 后端正确序列化/反序列化。
"""

import datetime
import decimal
import enum
import fractions
import pathlib
import pytest

from vools.serialize import Serializer, register_type


class Color(enum.Enum):
    RED = 1
    GREEN = 2
    BLUE = 3


class TestTypeRegistryJson:
    """JSON 后端类型注册表测试"""

    def test_datetime_round_trip(self):
        s = Serializer(backend='json')
        dt = datetime.datetime(2026, 6, 19, 17, 30, 45, 123456)
        data = s.dumps(dt)
        restored = s.loads(data)
        assert restored == dt

    def test_date_round_trip(self):
        s = Serializer(backend='json')
        d = datetime.date(2026, 6, 19)
        data = s.dumps(d)
        restored = s.loads(data)
        assert restored == d

    def test_time_round_trip(self):
        s = Serializer(backend='json')
        t = datetime.time(17, 30, 45)
        data = s.dumps(t)
        restored = s.loads(data)
        assert restored == t

    def test_timedelta_round_trip(self):
        s = Serializer(backend='json')
        td = datetime.timedelta(days=1, seconds=3600, microseconds=500)
        data = s.dumps(td)
        restored = s.loads(data)
        assert restored == td

    def test_complex_round_trip(self):
        s = Serializer(backend='json')
        c = complex(3.0, -4.5)
        data = s.dumps(c)
        restored = s.loads(data)
        assert restored == c

    def test_decimal_round_trip(self):
        s = Serializer(backend='json')
        d = decimal.Decimal('12345.6789')
        data = s.dumps(d)
        restored = s.loads(data)
        assert restored == d

    def test_fraction_round_trip(self):
        s = Serializer(backend='json')
        f = fractions.Fraction(22, 7)
        data = s.dumps(f)
        restored = s.loads(data)
        assert restored == f

    def test_enum_round_trip(self):
        s = Serializer(backend='json')
        c = Color.GREEN
        data = s.dumps(c)
        restored = s.loads(data)
        assert restored is c

    def test_path_round_trip(self):
        s = Serializer(backend='json')
        p = pathlib.PurePath('/home/user/file.txt')
        data = s.dumps(p)
        restored = s.loads(data)
        assert restored == p

    def test_bytearray_round_trip(self):
        s = Serializer(backend='json')
        b = bytearray(b'\x00\x01\x02\xff')
        data = s.dumps(b)
        restored = s.loads(data)
        assert restored == b
        assert isinstance(restored, bytearray)

    def test_set_round_trip(self):
        s = Serializer(backend='json')
        st = {1, 2, 3}
        data = s.dumps(st)
        restored = s.loads(data)
        assert restored == st
        assert isinstance(restored, set)

    def test_frozenset_round_trip(self):
        s = Serializer(backend='json')
        fs = frozenset([1, 2, 3])
        data = s.dumps(fs)
        restored = s.loads(data)
        assert restored == fs
        assert isinstance(restored, frozenset)

    def test_nested_types(self):
        s = Serializer(backend='json')
        payload = {
            'created': datetime.datetime(2026, 1, 1),
            'tags': {'a', 'b'},
            'ratio': fractions.Fraction(1, 3),
            'amount': decimal.Decimal('99.99'),
            'meta': {
                'path': pathlib.PurePath('/tmp'),
                'flag': Color.RED,
            },
        }
        data = s.dumps(payload)
        restored = s.loads(data)
        assert restored['created'] == payload['created']
        assert restored['tags'] == payload['tags']
        assert restored['ratio'] == payload['ratio']
        assert restored['amount'] == payload['amount']
        assert restored['meta']['path'] == payload['meta']['path']
        assert restored['meta']['flag'] is payload['meta']['flag']


class TestTypeRegistryMsgpack:
    """msgpack 后端类型注册表测试"""

    def test_datetime_round_trip(self):
        pytest.importorskip('msgpack')
        s = Serializer(backend='msgpack')
        dt = datetime.datetime(2026, 6, 19, 17, 30, 45)
        data = s.dumps(dt)
        restored = s.loads(data)
        assert restored == dt

    def test_set_and_complex_round_trip(self):
        pytest.importorskip('msgpack')
        s = Serializer(backend='msgpack')
        payload = {
            'values': {1, 2, 3},
            'cplx': complex(1, 2),
            'money': decimal.Decimal('0.1'),
        }
        data = s.dumps(payload)
        restored = s.loads(data)
        assert restored['values'] == payload['values']
        assert restored['cplx'] == payload['cplx']
        assert restored['money'] == payload['money']


class TestTypeRegistryCustom:
    """自定义类型注册测试"""

    def test_custom_type_registration(self):
        class Point:
            def __init__(self, x, y):
                self.x = x
                self.y = y

            def __eq__(self, other):
                return isinstance(other, Point) and self.x == other.x and self.y == other.y

        register_type(
            Point,
            name='Point',
            serialize=lambda p: {'x': p.x, 'y': p.y},
            deserialize=lambda state: Point(state['x'], state['y']),
        )

        s = Serializer(backend='json')
        p = Point(10, 20)
        data = s.dumps(p)
        restored = s.loads(data)
        assert restored == p
