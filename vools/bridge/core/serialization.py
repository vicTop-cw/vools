"""
vools.bridge.core.serialization - 统一数据序列化层

提供跨语言调用的数据转换能力，支持 CSV 和 JSON 格式。
"""

import json


class Serializer:
    """数据序列化器"""

    @staticmethod
    def csv_serialize(data):
        """序列化为 CSV 格式字节串"""
        if isinstance(data, (list, tuple)):
            if all(isinstance(x, int) for x in data):
                return ','.join(str(x) for x in data).encode('utf-8')
            elif all(isinstance(x, float) for x in data):
                return ','.join(repr(x) for x in data).encode('utf-8')
            elif all(isinstance(x, str) for x in data):
                return ','.join(x for x in data).encode('utf-8')
            else:
                return ','.join(str(x) for x in data).encode('utf-8')
        elif isinstance(data, str):
            return data.encode('utf-8')
        elif isinstance(data, bytes):
            return data
        else:
            return str(data).encode('utf-8')

    @staticmethod
    def csv_deserialize(data, data_type='int'):
        """从 CSV 格式字节串反序列化"""
        if not data:
            return []
        s = data.decode('utf-8')
        parts = [x.strip() for x in s.split(',') if x.strip()]
        if data_type == 'int':
            return [int(x) for x in parts]
        elif data_type == 'float':
            return [float(x) for x in parts]
        elif data_type == 'string':
            return parts
        else:
            return parts

    @staticmethod
    def json_serialize(data):
        """序列化为 JSON 格式字节串"""
        return json.dumps(data).encode('utf-8')

    @staticmethod
    def json_deserialize(data):
        """从 JSON 格式字节串反序列化"""
        if not data:
            return None
        return json.loads(data.decode('utf-8'))


# 便捷函数
def csv_serialize(data):
    """CSV 序列化"""
    return Serializer.csv_serialize(data)


def csv_deserialize(data, data_type='int'):
    """CSV 反序列化"""
    return Serializer.csv_deserialize(data, data_type)


def json_serialize(data):
    """JSON 序列化"""
    return Serializer.json_serialize(data)


def json_deserialize(data):
    """JSON 反序列化"""
    return Serializer.json_deserialize(data)
