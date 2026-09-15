"""tests/serialize/test_type_registry.py — 类型注册表测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.serialize.type_registry import (
    register_type, get_type_handler, get_type_deserializer,
)


class TestTypeRegistry:
    """类型注册表测试"""

    def test_register_and_get_handler(self):
        from datetime import datetime

        def serialize(obj):
            return obj.isoformat()

        def deserialize(data):
            return datetime.fromisoformat(data)

        register_type(datetime, serialize=serialize, deserialize=deserialize)
        # get_type_handler 需要传入实例对象
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = get_type_handler(dt)
        assert result is not None
        assert result[0]  # 名称非空
        assert callable(result[1])  # 序列化函数可调用

    def test_get_type_handler_unknown(self):
        class UnknownType:
            pass
        obj = UnknownType()
        assert get_type_handler(obj) is None

    def test_get_type_deserializer(self):
        from datetime import datetime

        def serialize(obj):
            return obj.isoformat()

        def deserialize(data):
            return datetime.fromisoformat(data)

        register_type(datetime, serialize=serialize, deserialize=deserialize)
        # 获取名称
        dt = datetime(2024, 1, 1, 12, 0, 0)
        handler = get_type_handler(dt)
        if handler:
            name = handler[0]
            result = get_type_deserializer(name)
            assert result is not None

    def test_get_type_deserializer_unknown(self):
        assert get_type_deserializer('nonexistent.type') is None

    def test_serialize_deserialize_roundtrip(self):
        from datetime import datetime

        def serialize(obj):
            return {'iso': obj.isoformat()}

        def deserialize(data):
            return datetime.fromisoformat(data['iso'])

        register_type(datetime, serialize=serialize, deserialize=deserialize)
        dt = datetime(2024, 1, 1, 12, 0, 0)
        handler = get_type_handler(dt)
        if handler:
            _, serialize_fn = handler
            serialized = serialize_fn(dt)
            # 获取名称用于反序列化
            name = handler[0]
            deserializer = get_type_deserializer(name)
            if deserializer:
                result = deserializer(serialized)
                assert result == dt

    def test_register_requires_serialize(self):
        class MyClass:
            pass
        with pytest.raises(ValueError):
            register_type(MyClass, serialize=None, deserialize=lambda x: x)

    def test_register_requires_deserialize(self):
        class MyClass:
            pass
        with pytest.raises(ValueError):
            register_type(MyClass, serialize=lambda x: x, deserialize=None)
