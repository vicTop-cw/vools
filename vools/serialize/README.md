# vools.serialize

序列化模块，提供对象序列化和反序列化功能。

## 主要功能

- **序列化**: 将 Python 对象转换为可存储格式
- **反序列化**: 将存储格式转换为 Python 对象
- **后端支持**: JSON、MsgPack、Pickle

## 核心类

| 名称 | 说明 |
|------|------|
| `Serializer` | 序列化器 |
| `deserialize` | 反序列化函数 |

## 使用示例

```python
from vools.serialize import Serializer, deserialize

# 序列化
data = {'key': 'value'}
serialized = Serializer.serialize(data, format='json')

# 反序列化
deserialized = deserialize(serialized, format='json')
```

## 注意事项

- Pickle 格式存在安全风险，仅用于可信数据

## 子包

| 路径 | 说明 |
|------|------|
| `vools.serialize.backends` | 序列化后端（JsonBackend, PickleBackend, MsgpackBackend） |
| `vools.serialize.callable` | 可调用对象序列化（DecoratorHandler, FunctionalHandler） |