# vools.serialize.callable — 可调用对象序列化

提供对各种可调用对象（装饰器包装的函数、柯里化函数、函数式对象等）的序列化支持，通过处理器模式实现可扩展的序列化机制。

## 核心组件

| 名称 | 说明 |
|------|------|
| `CallableHandler` | 可调用对象处理器抽象基类 |
| `DecoratorHandler` | 装饰器处理器 |
| `FunctionalHandler` | 函数式处理器 |
| `register_handler` | 注册自定义处理器 |
| `get_handler` | 获取能处理给定对象的处理器 |
| `serialize_callable` | 序列化可调用对象 |
| `deserialize_callable` | 反序列化可调用对象 |

## 使用示例

### 序列化可调用对象

```python
from vools.serialize.callable import serialize_callable, deserialize_callable
from vools.serialize.backends import PickleBackend

backend = PickleBackend()

# 假设有一个被装饰的函数
from vools.decorators import curry

@curry
def add(a, b, c):
    return a + b + c

# 序列化可调用对象
handler_name, handler_state = serialize_callable(add, backend)

# 反序列化可调用对象
restored = deserialize_callable(handler_name, handler_state, backend)

# 使用恢复的函数
result = restored(1)(2)(3)
print(result)  # 6
```

### 自定义处理器

```python
from vools.serialize.callable import CallableHandler, register_handler, serialize_callable

class MyFunctionHandler(CallableHandler):
    def can_handle(self, obj):
        return hasattr(obj, '__my_func__')
    
    def get_state(self, obj):
        return {
            'func_name': obj.__name__,
            'module': obj.__module__,
            'custom_data': obj.__my_func__
        }
    
    def restore(self, state):
        import importlib
        module = importlib.import_module(state['module'])
        func = getattr(module, state['func_name'])
        func.__my_func__ = state['custom_data']
        return func

# 注册自定义处理器
register_handler(MyFunctionHandler())
```

### 获取处理器

```python
from vools.serialize.callable import get_handler

# 检查对象能否被处理
def my_func():
    pass

handler = get_handler(my_func)
if handler:
    print(f"使用处理器: {handler.handler_name}")
    state = handler.get_state(my_func)
else:
    print("没有匹配的处理器，将使用原始 pickle 序列化")
```

### 处理器注册顺序

```python
# 处理器按注册顺序匹配，先注册的先匹配
# 建议注册顺序：具体类型 → 通用兜底
# 内置处理器顺序：
# 1. DecoratorHandler - 处理装饰器包装的函数
# 2. FunctionalHandler - 处理函数式对象
```

### 与序列化模块配合使用

```python
from vools.serialize import Serializer
from vools.serialize.backends import JsonBackend

# 使用序列化器时，callable 处理器会自动集成
serializer = Serializer(backend='json')

# 可以序列化包含可调用对象的复杂结构
data = {
    'name': 'my_transform',
    'func': lambda x: x * 2  # 注意：lambda 可能需要特殊处理
}

# 简单对象直接序列化
simple_data = {'key': 'value', 'numbers': [1, 2, 3]}
serialized = serializer.serialize(simple_data)
```

## 注意事项

- 可调用对象的序列化有一定局限性，不是所有函数都能被完美序列化
- lambda 函数和闭包可能无法正确序列化
- 建议优先使用模块级函数，避免依赖闭包变量
- 自定义处理器时，确保 get_state 和 restore 方法对称
- 序列化结果包含处理器名称和状态两部分
