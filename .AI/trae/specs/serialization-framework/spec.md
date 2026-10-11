# Callable 序列化子包规格

## Why
项目中缺乏对 **callable 对象**（装饰器包装的函数、柯里化函数、响应式对象等）的序列化支持。现有 `encoding` 模块仅支持数据格式转换，无法序列化 `curry` 装饰的函数、`Pipe`/`Ops` 等函数式对象、`Observable`/`Subject` 等响应式对象。

## What Changes
- 新增 `vools/serialize` 子包（独立于 `encoding`）
- 支持多种序列化后端：pickle、json（via orjson）、msgpack
- 提供 `@serialize` / `@deserialize` 装饰器，自动序列化函数返回值/参数
- 提供 `@serializable` 类装饰器，为类添加序列化/反序列化能力
- **核心特性**：支持序列化 **callable 对象**（被装饰器包装的函数、lambda、类实例等）

## Impact
- 新增包：`vools.serialize`
- 无破坏性变更
- 可选后端（msgpack、orjson）未安装时回退到内置实现

## 现有 API 分析

### 需要序列化支持的 Callable 类型

| 类型 | 示例 | 序列化难点 |
|------|------|-----------|
| 装饰器包装函数 | `@curry`, `@memorize` 装饰的函数 | 闭包、函数属性 |
| 柯里化函数 | `curry(func)(arg1)(arg2)` | Partial 参数绑定 |
| 函数式对象 | `Pipe`, `Ops`, `P`, `Box` | 链式调用状态 |
| 响应式对象 | `Observable`, `Subject` | 订阅关系、内部状态 |
| lambda 表达式 | `lambda x: x * 2` | 闭包环境 |
| 偏函数 | `functools.partial` | 参数绑定 |

## ADDED Requirements

### Requirement: 序列化后端支持
系统 SHALL 支持以下序列化后端：
- `pickle`：Python 内置，支持任意对象（包括 callable）
- `json`：跨语言友好，通过 orjson 高性能实现（可选）
- `msgpack`：高效二进制格式（可选）

#### Scenario: 选择不同后端
- **WHEN** 用户创建 `Serializer(backend='pickle')`
- **THEN** 使用 pickle 进行序列化

### Requirement: 函数装饰器 `@serialize`
系统 SHALL 提供 `@serialize` 装饰器，自动将函数返回值序列化

#### Scenario: 基本用法
- **WHEN** 在函数上使用 `@serialize(backend='pickle')`
- **THEN** 函数返回值自动序列化为字节串

#### Scenario: 支持 callable 序列化
- **WHEN** 返回值是 `@curry` 装饰的函数
- **THEN** curry 函数连同其绑定参数一起被正确序列化

### Requirement: 函数装饰器 `@deserialize`
系统 SHALL 提供 `@deserialize` 装饰器，自动将函数参数反序列化

#### Scenario: 基本用法
- **WHEN** 在函数上使用 `@deserialize(backend='pickle')`
- **THEN** 函数参数自动从序列化数据反序列化

### Requirement: 类装饰器 `@serializable`
系统 SHALL 提供 `@serializable` 类装饰器，为类添加序列化/反序列化能力

#### Scenario: 基本用法
- **WHEN** 在类上使用 `@serializable(backend='pickle')`
- **THEN** 类自动获得 `serialize()` 和 `deserialize()` 类方法

#### Scenario: 类的序列化/反序列化
- **WHEN** 对类的实例调用 `MyClass.serialize(instance)`
- **THEN** 实例及其 callable 属性（如被装饰的方法）被正确序列化

### Requirement: 实例方法装饰器
系统 SHALL 提供 `@serialize_method` 和 `@deserialize_method` 实例方法装饰器

#### Scenario: 序列化实例方法返回值
- **WHEN** 在实例方法上使用 `@serialize_method`
- **THEN** 方法返回值自动序列化

### Requirement: 全局配置
系统 SHALL 提供全局默认后端配置

#### Scenario: 设置默认后端
- **WHEN** 调用 `set_default_backend('pickle')`
- **THEN** 后续未指定后端的序列化操作使用 pickle

### Requirement: Callable 特殊处理
系统 SHALL 对 callable 对象提供特殊序列化支持

#### Scenario: 序列化被装饰的函数
- **WHEN** 序列化包含 `@curry`, `@memorize` 等装饰器的函数
- **THEN** 装饰器状态和绑定参数被正确保存和恢复

#### Scenario: 序列化函数式对象
- **WHEN** 序列化 `Pipe`, `Ops`, `Box` 等函数式对象
- **THEN** 对象状态和链式调用关系被正确保存

## 实现设计

### 包结构
```
vools/serialize/
├── __init__.py          # 导出主要 API
├── core.py              # 核心 Serializer 类
├── decorators.py        # @serialize, @deserialize, @serializable 等装饰器
├── backends/            # 序列化后端
│   ├── __init__.py
│   ├── base.py          # 后端基类
│   ├── pickle_backend.py
│   ├── json_backend.py
│   └── msgpack_backend.py
├── callable/            # Callable 特殊处理
│   ├── __init__.py
│   ├── curry_handler.py   # 处理 curry 化的函数
│   ├── decorator_handler.py # 处理被装饰器包装的函数
│   ├── functional_handler.py # 处理 Pipe, Ops, Box 等
│   └── reactive_handler.py  # 处理 Observable, Subject 等
└── config.py            # 全局配置
```

### 使用示例

```python
from vools.serialize import serialize, deserialize, set_default_backend
from vools import curry

# 序列化被装饰的函数
@curry
def add(a, b):
    return a + b

@serialize(backend='pickle')
def get_adder():
    return add(10)  # 返回部分应用的 curry 函数

# 序列化函数返回值（包含 callable）
serialized = get_adder()  # 自动序列化
result = deserialize(serialized, backend='pickle')  # 反序列化后仍是可调用函数

# 类装饰器
from vools.serialize import serializable

@serializable(backend='pickle')
class MyService:
    def __init__(self, name: str):
        self.name = name

    def process(self, data):
        return f"{self.name}: {data}"

service = MyService("test")
data = MyService.serialize(service)
restored = MyService.deserialize(data)
```

### 后端选择建议
| 场景 | 推荐后端 |
|------|----------|
| 跨语言互通 | json |
| 序列化 callable 对象 | pickle |
| 高性能存储 | msgpack |
| 调试/日志 | json (orjson) |
