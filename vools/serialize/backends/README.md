# vools.serialize.backends — 序列化后端

提供多种序列化后端，支持 JSON、Pickle、MessagePack 等格式，可根据场景选择合适的后端。

## 支持的后端

| 后端 | 类 | 说明 |
|------|-----|------|
| JSON | `JsonBackend` | JSON 格式（跨语言、可读） |
| Pickle | `PickleBackend` | Python pickle（高性能） |
| MessagePack | `MsgpackBackend` | MessagePack 格式（二进制、紧凑） |

## 使用示例

### 获取后端

```python
from vools.serialize.backends import get_backend, register_backend

# 获取内置后端
json_backend = get_backend('json')
pickle_backend = get_backend('pickle')

# 获取可选后端（msgpack 需要额外安装）
try:
    msgpack_backend = get_backend('msgpack')
except ValueError as e:
    print(f"Msgpack 后端不可用: {e}")
```

### JSON 后端

```python
from vools.serialize.backends import JsonBackend

backend = JsonBackend()

# 序列化
data = {'name': 'Alice', 'age': 25, 'scores': [90, 85, 95]}
serialized = backend.dumps(data)
print(type(serialized))  # <class 'str'>

# 反序列化
deserialized = backend.loads(serialized)
print(deserialized)
# {'name': 'Alice', 'age': 25, 'scores': [90, 85, 95]}
```

### Pickle 后端

```python
from vools.serialize.backends import PickleBackend

backend = PickleBackend()

# 序列化（可以序列化更复杂的 Python 对象）
data = {'key': 'value', 'list': [1, 2, 3], 'set': {1, 2, 3}}
serialized = backend.dumps(data)
print(type(serialized))  # <class 'bytes'>

# 反序列化
deserialized = backend.loads(serialized)
print(deserialized)
# {'key': 'value', 'list': [1, 2, 3], 'set': {1, 2, 3}}
```

### MessagePack 后端（可选）

```python
from vools.serialize.backends import MsgpackBackend, MSGPACK_AVAILABLE

if MSGPACK_AVAILABLE:
    backend = MsgpackBackend()
    
    # 序列化（二进制格式，更紧凑）
    data = {'name': 'Bob', 'age': 30}
    serialized = backend.dumps(data)
    print(type(serialized))  # <class 'bytes'>
    
    # 反序列化
    deserialized = backend.loads(serialized)
    print(deserialized)
else:
    print("请先安装 msgpack: pip install msgpack")
```

### 注册自定义后端

```python
from vools.serialize.backends import BaseBackend, register_backend, get_backend

class YamlBackend(BaseBackend):
    def dumps(self, obj):
        import yaml
        return yaml.dump(obj)
    
    def loads(self, s):
        import yaml
        return yaml.safe_load(s)

# 注册自定义后端
register_backend('yaml', YamlBackend)

# 使用自定义后端
backend = get_backend('yaml')
data = {'key': 'value'}
serialized = backend.dumps(data)
```

### 后端对比选择

```python
# 选择建议：
# - 需要跨语言、可读：JSON
# - 纯 Python 环境、高性能：Pickle
# - 二进制、紧凑存储：MessagePack
# - 有特殊需求：自定义后端
```
