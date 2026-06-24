# vools.bridge 架构重构 - C 优先，复用 ctypes 基础设施

## Overview
- **Summary**: 重新设计 bridge 子包架构，以 C/ctypes 为核心基础设施，其他语言（Nim、Rust 等）复用核心 ctypes 加载能力，只增加各自的编译器和代码生成层
- **Purpose**: 避免每种语言重复实现 ctypes 加载逻辑，统一基础能力，降低扩展成本
- **Target Users**: vools 库开发者、需要跨语言性能优化的用户

## Goals
- 以 C/ctypes 为核心，提供统一的共享库加载和类型映射基础设施
- 所有语言桥接复用核心 ctypes 能力
- 其他语言（Nim、Rust 等）只需要添加编译器和代码生成
- 支持动态编译装饰器（类似 fbc.py 的 @fbc）
- 支持异步编译和调用

## Non-Goals
- 实现所有语言的桥接（先做 C 和 Nim，其他预留）
- 提供 GUI 工具
- 支持非 ctypes 方式的调用（如 subprocess 调用）

## 架构设计

### 核心层（bridge/core/）
所有语言共用的 ctypes 基础设施：

| 文件 | 职责 |
|------|------|
| `loader.py` | 共享库加载（Windows .dll / Linux .so）、缓存、路径查找 |
| `types.py` | Python ↔ ctypes 类型映射、自动类型推断 |
| `decorators.py` | `@bridge_function`、`@bridge_module` 通用装饰器 |
| `serialization.py` | 数据序列化（CSV、JSON） |

### C 语言层（bridge/c/）
最薄的一层，直接复用 core：

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出 C 桥接 API |
| `loader.py` | （可选）C 特有的加载逻辑，主要复用 core.loader |

### Nim 语言层（bridge/nim/）
复用 core，增加 Nim 编译器能力：

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出 Nim 桥接 API |
| `compiler.py` | Nim 编译器封装、代码生成、动态编译装饰器 `@nim` |
| `prebuilt/` | 预编译的 Nim 库（crypto、seq 等，从 vools/lib 迁移） |

### 其他语言层（预留）
- `bridge/rust/` - Rust 桥接
- `bridge/cpp/` - C++ 桥接
- `bridge/csharp/` - C# 桥接
- ...

## 核心 API 设计

### 1. C 语言 API
```python
from vools.bridge.c import load_dll, call_func, CDecorator

# 方式1：直接加载和调用
lib = load_dll("mylib.dll")
result = call_func(lib, "add", [1, 2], ret_type=int)

# 方式2：装饰器
@c_dll("mylib.dll")
def add(a: int, b: int) -> int:
    pass  # 实现来自 DLL
```

### 2. Nim 动态编译 API
```python
from vools.bridge.nim import nim

@nim  # 同步
def fib(n: int) -> int:
    return """
if n <= 1:
    result = 1
else:
    result = fib(n-1) + fib(n-2)
"""

@nim(async_mode=True)  # 异步
async def heavy_compute(data: list) -> float:
    return "<nim code>"
```

### 3. 通用桥接装饰器
```python
from vools.bridge import bridge_function, bridge_module

@bridge_function(language="nim", lib="vools_crypto", func="md5_hash")
def md5(data: bytes) -> str:
    pass  # 自动映射到库函数

@bridge_module(language="c", dll_path="math.dll")
class MathLib:
    def add(a: int, b: int) -> int: ...
    def mul(a: float, b: float) -> float: ...
```

## 功能需求

### FR-1: 核心共享库加载器（C 基础）
- 跨平台（Windows/Linux）
- 自动查找库路径
- 库缓存机制
- 线程安全

### FR-2: 类型映射系统
- Python → ctypes 类型自动推断
- 支持基本类型（int/float/bool/str/bytes）
- 支持指针、数组类型
- 可扩展自定义类型

### FR-3: C 桥接模块
- `load_dll()` 加载 C 编译的 DLL
- `call_func()` 直接调用 DLL 函数
- `@c_dll` 装饰器

### FR-4: Nim 动态编译装饰器
- `@nim` 装饰器，接收返回 Nim 代码的函数
- 自动编译为 DLL/SO
- 缓存编译结果（基于代码哈希）
- 支持同步和异步模式

### FR-5: 通用桥接装饰器
- `@bridge_function` 单函数桥接
- `@bridge_module` 模块级桥接
- 支持指定语言、库名、函数名

### FR-6: 回退机制
- 共享库不存在时回退到 Python 实现
- 编译失败时回退到 Python 实现
- 不影响正常使用

## 非功能需求

### NFR-1: 性能
- 编译缓存命中时，调用开销接近原生 ctypes
- 首次编译开销可接受（< 5s 对于小函数）

### NFR-2: 可扩展性
- 添加新语言只需实现编译器接口
- 核心 ctypes 逻辑完全复用

### NFR-3: 兼容性
- 与现有 vools API 完全兼容
- 不破坏现有用户代码

## 约束

### 技术约束
- Python 3.6+
- 标准库 ctypes
- 各语言编译器需用户自行安装

### 平台约束
- Windows (x64)
- Linux (x64/WSL)

## 接受标准

### AC-1: C DLL 加载和调用
- **Given**: 一个 C 编译的 DLL 文件
- **When**: 使用 `load_dll()` 加载并调用函数
- **Then**: 正确返回计算结果
- **Verification**: `programmatic`

### AC-2: @c_dll 装饰器
- **Given**: 一个 C DLL 和对应的 Python 函数声明
- **When**: 使用 `@c_dll` 装饰
- **Then**: 函数自动映射到 DLL 中的实现
- **Verification**: `programmatic`

### AC-3: @nim 动态编译装饰器
- **Given**: 一个返回 Nim 代码的 Python 函数
- **When**: 使用 `@nim` 装饰并调用
- **Then**: 自动编译并执行 Nim 代码，返回结果
- **Verification**: `programmatic`

### AC-4: 编译缓存
- **Given**: 多次调用同一个 @nim 装饰的函数（代码相同）
- **When**: 第二次及以后调用
- **Then**: 直接使用缓存的 DLL，不重新编译
- **Verification**: `programmatic`

### AC-5: 异步模式
- **Given**: 使用 `@nim(async_mode=True)` 装饰的函数
- **When**: await 调用
- **Then**: 在后台线程编译和执行，不阻塞主线程
- **Verification**: `programmatic`

### AC-6: 回退机制
- **Given**: 编译器不存在或编译失败
- **When**: 调用桥接函数
- **Then**: 自动回退到 Python fallback 实现
- **Verification**: `programmatic`

### AC-7: 多语言复用
- **Given**: C 和 Nim 两种桥接
- **When**: 都使用共享库加载
- **Then**: 都复用 core.loader 的 ctypes 基础设施
- **Verification**: `human-judgment`

## 待规划任务（分解）

1. **核心层重构**：将现有 nim 加载逻辑抽象到 core
2. **C 桥接实现**：基于 core 实现 C 模块
3. **Nim 桥接重构**：Nim 模块复用 core，增加编译器
4. **装饰器完善**：@bridge_function、@bridge_module
5. **异步支持**：异步编译和调用
6. **文档和示例**

## 开放问题

- [ ] 是否需要支持 C++ name mangling？
- [ ] 编译缓存的目录结构和清理策略？
- [ ] 是否需要支持更多类型（结构体、回调函数）？
- [ ] 错误处理和调试信息的详细程度？
