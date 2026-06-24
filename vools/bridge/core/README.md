# vools.bridge.core - 桥接核心基础设施

`vools.bridge.core` 是 `vools.bridge` 跨语言桥接框架的核心基础设施子包，提供共享库加载、类型映射、装饰器和序列化等底层能力，是所有语言桥接实现的基础。

## 目录

- [子包概述](#子包概述)
- [模块说明](#模块说明)
- [核心 API 文档](#核心-api-文档)
  - [LibraryLoader / SharedLibrary](#libraryloader--sharedlibrary)
  - [CTypeMapper](#ctypemapper)
  - [bridge_function / bridge_module / bridge_func_name](#bridge_function--bridge_module--bridge_func_name)
  - [Serializer](#serializer)
- [使用示例](#使用示例)
- [与 LangBridge 的关系](#与-langbridge-的关系)

## 子包概述

`core` 子包位于 `vools.bridge.core`，是整个桥接框架的底层基石。它封装了 ctypes 的底层操作，提供了一套简洁易用的 API，让上层语言桥接模块可以专注于语言特定的代码生成和编译逻辑，而无需重复实现库加载、类型转换等通用功能。

主要功能：

- **共享库加载**：跨平台的 `.dll` / `.so` 加载与管理
- **类型映射**：Python 类型与 ctypes 类型的自动转换和推断
- **装饰器系统**：`@bridge_function` 和 `@bridge_module` 简化桥接函数定义
- **数据序列化**：CSV 和 JSON 格式的序列化 / 反序列化支持

## 模块说明

| 模块 | 文件 | 功能简介 |
|------|------|----------|
| 库加载器 | `loader.py` | 提供 `LibraryLoader` 和 `SharedLibrary`，支持跨平台共享库加载、函数缓存、线程安全 |
| 类型映射 | `types.py` | 提供 `CTypeMapper`，实现 Python ↔ ctypes 类型自动映射、参数推断和转换 |
| 装饰器 | `decorators.py` | 提供 `@bridge_function`、`@bridge_module`、`@bridge_func_name`，支持从类型注解自动推断、fallback 机制 |
| 序列化 | `serialization.py` | 提供 `Serializer`，支持 CSV 和 JSON 格式的数据序列化与反序列化 |

## 核心 API 文档

### LibraryLoader / SharedLibrary

#### SharedLibrary

通用共享库封装类，封装 `ctypes.CDLL`，提供更便捷的函数调用方式。

```python
class SharedLibrary:
    def __init__(self, path, setup_func=None)
    def get_function(self, name, argtypes=None, restype=None)
    def call(self, name, *args, **kwargs)
```

**参数说明：**

- `path`：共享库文件路径
- `setup_func`：可选的设置函数，用于初始化库函数签名
- `argtypes`：参数类型列表（ctypes 类型）
- `restype`：返回值类型（ctypes 类型）

**示例：**

```python
from vools.bridge.core import SharedLibrary

lib = SharedLibrary("/path/to/mylib.dll")

# 方式1：通过 get_function 获取函数
add_func = lib.get_function("add", argtypes=[c_int, c_int], restype=c_int)
result = add_func(1, 2)

# 方式2：通过 call 直接调用
result = lib.call("add", 1, 2, argtypes=[c_int, c_int], restype=c_int)

# 方式3：通过属性访问（便捷方式）
result = lib.add(1, 2)
```

#### LibraryLoader

统一共享库加载器，按语言维度管理共享库，支持自动查找库路径、线程安全的单例加载。

```python
class LibraryLoader:
    def __init__(self, language)
    def load(self, name, setup_func=None)
    def is_available(self, name)
```

**便捷函数：**

```python
from vools.bridge.core import load_library, load_from_path, is_available

# 加载指定语言的共享库
lib = load_library("nim", "vools_crypto")

# 从指定路径加载
lib = load_from_path("/path/to/lib.so")

# 检查语言是否有可用的桥接库
if is_available("nim"):
    print("Nim bridge is available")
```

### CTypeMapper

ctypes 类型映射器，提供 Python 类型与 ctypes 类型之间的转换和推断功能。所有方法均为静态方法。

```python
class CTypeMapper:
    @staticmethod
    def register_type(py_type, c_type)
    @staticmethod
    def get_ctype(py_type)
    @staticmethod
    def infer_arg_types(args)
    @staticmethod
    def infer_ret_type(ret_type)
    @staticmethod
    def convert_args(args, argtypes)
```

**默认类型映射表 `PY_TO_CTYPES`：**

| Python 类型 | ctypes 类型 |
|-------------|-------------|
| `int` | `c_long` |
| `float` | `c_double` |
| `bool` | `c_int` |
| `str` | `c_char_p` |
| `bytes` | `c_char_p` |

**示例：**

```python
from vools.bridge.core import CTypeMapper, PY_TO_CTYPES

# 推断参数类型
argtypes = CTypeMapper.infer_arg_types([1, 3.14, "hello"])
# => [c_long, c_double, c_char_p]

# 推断返回类型
restype = CTypeMapper.infer_ret_type(int)
# => c_long

# 转换参数（str 自动编码为 bytes）
converted = CTypeMapper.convert_args(["hello", 42], [c_char_p, c_int])
# => [b'hello', 42]

# 注册自定义类型映射
CTypeMapper.register_type(MyCustomType, c_void_p)
```

**便捷函数：**

```python
from vools.bridge.core import infer_arg_types, infer_ret_type, convert_args

argtypes = infer_arg_types([1, "hello"])
restype = infer_ret_type(str)
converted = convert_args([1, "hi"], argtypes)
```

### bridge_function / bridge_module / bridge_func_name

#### @bridge_function

桥接函数装饰器，将一个 Python 函数标记为可以使用其他语言实现的桥接函数。支持从类型注解自动推断参数类型、自动 str/bytes 转换、fallback 机制。

```python
def bridge_function(language, fallback=None, lib_name=None, func_name=None,
                    serializer=None, deserializer=None)
```

**参数说明：**

- `language`：目标语言名称（如 `"nim"`）
- `fallback`：Python 回退实现函数，底层库不可用时调用
- `lib_name`：共享库名称（默认根据函数名自动推导）
- `func_name`：库中的函数名称（默认与 Python 函数名相同）
- `serializer`：自定义参数序列化函数
- `deserializer`：自定义返回值反序列化函数

**示例：**

```python
from vools.bridge.core import bridge_function

# 基础用法 - 带 fallback
def _py_md5(data, length):
    import hashlib
    return hashlib.md5(data[:length]).digest()

@bridge_function("nim", fallback=_py_md5)
def md5(data: bytes, length: int) -> bytes:
    pass

# 指定库名和函数名
@bridge_function("nim", lib_name="vools_crypto", func_name="md5_hash")
def md5_hash(data: bytes, length: int) -> bytes:
    pass

# str 类型自动编码/解码
@bridge_function("nim", lib_name="vools_encoding")
def base64_encode(data: str, length: int) -> str:
    pass  # 输入 str 自动编码为 bytes，返回 bytes 自动解码为 str
```

#### @bridge_module

桥接模块装饰器，将一个类标记为桥接模块，类中的所有公共方法自动使用对应语言的实现。方法的第一个参数（`self`）会被自动跳过。

```python
def bridge_module(language, lib_name=None, lib_names=None)
```

**参数说明：**

- `language`：目标语言名称
- `lib_name`：单个共享库名称
- `lib_names`：共享库名称列表，按顺序尝试加载

**示例：**

```python
from vools.bridge.core import bridge_module, bridge_func_name

# 单库模式
@bridge_module("nim", lib_name="vools_crypto")
class CryptoModule:
    def md5_hash(self, data: bytes, length: int) -> bytes:
        pass

    def sha1_hash(self, data: bytes, length: int) -> bytes:
        pass

# 多库模式 - 按顺序尝试
@bridge_module("nim", lib_names=["vools_crypto", "vools_encoding"])
class CombinedModule:
    def md5_hash(self, data: bytes, length: int) -> bytes:
        pass
    def base64_encode(self, data: bytes, length: int) -> bytes:
        pass
```

#### @bridge_func_name

指定桥接函数在底层库中的名称，用于 `@bridge_module` 中的方法单独指定函数名。

```python
def bridge_func_name(name)
```

**示例：**

```python
@bridge_module("nim", lib_name="vools_crypto")
class Crypto:
    @bridge_func_name("md5_hash")
    def md5(self, data: bytes, length: int) -> bytes:
        pass

    @bridge_func_name("sha1_hash")
    def sha1(self, data: bytes, length: int) -> bytes:
        pass
```

### Serializer

数据序列化器，提供 CSV 和 JSON 格式的序列化与反序列化功能，所有方法均为静态方法。

```python
class Serializer:
    @staticmethod
    def csv_serialize(data)
    @staticmethod
    def csv_deserialize(data, data_type='int')
    @staticmethod
    def json_serialize(data)
    @staticmethod
    def json_deserialize(data)
```

**CSV 序列化支持的数据类型：**

- `int`：整数列表
- `float`：浮点数列表
- `string`：字符串列表

**示例：**

```python
from vools.bridge.core import Serializer

# CSV 序列化
csv_bytes = Serializer.csv_serialize([1, 2, 3, 4])
# => b'1,2,3,4'

csv_bytes = Serializer.csv_serialize(["a", "b", "c"])
# => b'a,b,c'

# CSV 反序列化
nums = Serializer.csv_deserialize(b'1,2,3', data_type='int')
# => [1, 2, 3]

floats = Serializer.csv_deserialize(b'1.5,2.5', data_type='float')
# => [1.5, 2.5]

# JSON 序列化
json_bytes = Serializer.json_serialize({"key": "value", "nums": [1, 2]})
# => b'{"key": "value", "nums": [1, 2]}'

# JSON 反序列化
data = Serializer.json_deserialize(json_bytes)
# => {'key': 'value', 'nums': [1, 2]}
```

**便捷函数：**

```python
from vools.bridge.core.serialization import (
    csv_serialize, csv_deserialize,
    json_serialize, json_deserialize,
)

csv_bytes = csv_serialize([1, 2, 3])
data = json_deserialize(json_bytes)
```

## 使用示例

### 示例 1：直接使用 SharedLibrary 调用 C 函数

```python
import ctypes
from vools.bridge.core import SharedLibrary

# 加载共享库
lib = SharedLibrary("path/to/mathlib.dll")

# 设置函数签名并调用
add = lib.get_function("add", 
    argtypes=[ctypes.c_int, ctypes.c_int], 
    restype=ctypes.c_int
)
result = add(3, 4)
print(f"3 + 4 = {result}")  # 3 + 4 = 7
```

### 示例 2：使用装饰器定义桥接函数

```python
from vools.bridge.core import bridge_function

# Python fallback 实现
def _py_factorial(n):
    if n <= 1:
        return 1
    return n * _py_factorial(n - 1)

# 桥接函数 - 如果 nim 库可用则调用 nim，否则用 Python fallback
@bridge_function("nim", fallback=_py_factorial, lib_name="vools_math")
def factorial(n: int) -> int:
    pass

print(factorial(5))  # 120（优先调用 nim，不可用则调用 Python）
```

### 示例 3：使用桥接模块组织相关函数

```python
from vools.bridge.core import bridge_module, bridge_func_name

@bridge_module("nim", lib_name="vools_crypto")
class CryptoUtils:
    def md5_hash(self, data: bytes, length: int) -> bytes:
        """MD5 哈希"""
        pass

    @bridge_func_name("sha1_hash")
    def sha1(self, data: bytes, length: int) -> bytes:
        """SHA1 哈希（函数名映射）"""
        pass

    def sha256_hash(self, data: bytes, length: int) -> bytes:
        """SHA256 哈希"""
        pass

crypto = CryptoUtils()
digest = crypto.md5_hash(b"hello world", 11)
```

### 示例 4：自定义序列化器

```python
from vools.bridge.core import bridge_function
from vools.bridge.core.serialization import json_serialize, json_deserialize

def _my_serializer(data, size):
    return (json_serialize(data), size)

def _my_deserializer(result):
    return json_deserialize(result)

@bridge_function(
    "nim",
    lib_name="vools_json",
    func_name="process_json",
    serializer=_my_serializer,
    deserializer=_my_deserializer,
)
def process_data(data: dict, size: int) -> dict:
    pass
```

### 示例 5：类型映射扩展

```python
from vools.bridge.core import CTypeMapper
import ctypes

# 自定义类型
class MyStruct(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int)]

# 注册自定义映射
CTypeMapper.register_type(tuple, MyStruct)

# 现在 tuple 类型会自动映射为 MyStruct
print(CTypeMapper.get_ctype(tuple))  # <class '__main__.MyStruct'>
```

## 与 LangBridge 的关系

`core` 子包和 `LangBridge` 是 vools.bridge 框架中两个不同层次的组件，各司其职：

### 架构层次

```
┌─────────────────────────────────────────────────┐
│           LangBridge (抽象基类)                 │
│   _base.py - 上层统一抽象接口                   │
│   定义各语言桥接的统一规范 (generate_code,      │
│   compile_code, call_func, decorator 等)        │
└───────────┬─────────────────────────────────────┘
            │
            │ 各语言桥接实现 (nim, rust, c, c++, ...)
            │
┌───────────▼─────────────────────────────────────┐
│           core (核心基础设施)                   │
│   loader.py       - 共享库加载                  │
│   types.py        - 类型映射                    │
│   decorators.py   - 桥接装饰器                  │
│   serialization.py - 序列化                     │
└─────────────────────────────────────────────────┘
```

### 职责分工

| 组件 | 层次 | 职责 |
|------|------|------|
| **core** | 底层基础设施 | 封装 ctypes 底层操作，提供库加载、类型映射、装饰器、序列化等通用工具 |
| **LangBridge** | 上层统一抽象 | 定义语言桥接的统一接口规范，包括代码生成、编译、调用、装饰器工厂等 |
| **各语言桥接模块** | 中间实现层 | 继承 LangBridge，基于 core 的基础设施，实现各语言特定的编译和调用逻辑 |

### 核心区别

- **core** 是**工具库**，提供可复用的底层能力（加载器、类型映射等），可以独立使用
- **LangBridge** 是**框架抽象**，定义了"一个语言桥接应该实现哪些方法"的契约
- 各语言桥接模块**同时依赖两者**：用 LangBridge 定义接口规范，用 core 提供的工具实现底层功能

### 使用场景

- 如果你只是想**直接调用已编译好的共享库**，用 core 的 `SharedLibrary` 或 `@bridge_function` 即可
- 如果你想**实现一个新语言的桥接支持**，需要继承 `LangBridge` 并实现其抽象方法，同时可以利用 core 提供的基础设施简化实现
