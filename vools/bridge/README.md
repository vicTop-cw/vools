# vools.bridge — 跨语言桥接框架

`vools.bridge` 是 vools 库的跨语言桥接子包，提供统一的 Python 到其他编程语言的桥接能力。通过装饰器模式，你可以用 Python 函数签名来定义接口，函数体作为目标语言的代码字符串，框架自动完成编译、加载、缓存和调用。

---

## 目录

- [功能概述](#功能概述)
- [支持的语言](#支持的语言)
- [架构设计](#架构设计)
- [核心概念](#核心概念)
- [三种使用模式](#三种使用模式)
- [快速上手](#快速上手)
- [API 概览](#api-概览)
- [子模块结构](#子模块结构)

---

## 功能概述

- **统一接口**：所有 14 种语言使用相同的装饰器 API，学习成本低
- **即时代码**：函数体即目标语言代码，无需额外源文件
- **自动编译**：首次调用时自动编译，基于内容哈希的编译缓存
- **类型映射**：从 Python 类型注解自动推断目标语言类型
- **依赖管理**：支持声明函数间依赖（deps），自动拓扑排序
- **异步支持**：支持 async/await 异步调用模式
- **回退机制**：编译器不可用时自动回退到 Python 实现
- **运行时管理**：统一的编译器路径、运行时环境配置管理

---

## 支持的语言

`vools.bridge` 目前支持 **14 种编程语言**：

| 语言       | 模块名       | 编译器    | 状态   |
|------------|--------------|-----------|--------|
| FreeBASIC  | `freebasic`  | fbc64     | ✅ 完整 |
| C          | `c`          | gcc / cc  | ✅ 完整 |
| C++        | `cpp`        | g++ / c++ | ✅ 完整 |
| Nim        | `nim`        | nim       | ✅ 完整 |
| Go         | `go`         | go        | ✅ 完整 |
| 仓颉       | `cangjie`    | cjc       | ✅ 完整 |
| Rust       | `rust`       | rustc     | ✅ 完整 |
| Mojo       | `mojo`       | mojo      | ✅ 完整 |
| C#         | `csharp`     | dotnet    | ✅ 完整 |
| Java       | `java`       | java      | ✅ 完整 |
| Scala      | `scala`      | scala     | ✅ 完整 |
| Ruby       | `ruby`       | ruby      | ✅ 完整 |
| Julia      | `julia`      | julia     | ✅ 完整 |
| R          | `r`          | Rscript   | ✅ 完整 |

> 所有语言均已接入 `LangBridge` 抽象基类和统一装饰器接口。

---

## 架构设计

### 整体架构图

```
                    ┌──────────────────────────────────┐
                    │       Python 应用代码             │
                    │  (@装饰器 / 直接调用)             │
                    └───────────────┬──────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │       LangBridge (ABC)           │
                    │   所有语言的统一抽象基类           │
                    │  - decorator() 装饰器工厂         │
                    │  - generate_code() 代码生成       │
                    │  - compile_code() 编译            │
                    │  - call_func() 函数调用           │
                    └───────────────┬──────────────────┘
                                    │
         ┌──────────────┬───────────┴──────────┬──────────────┐
         │              │                      │              │
    ┌────▼────┐   ┌────▼────┐           ┌────▼────┐   ┌────▼────┐
    │  C      │   │  Nim    │   ...     │  Rust   │   │  Mojo   │
    │ FreeBASIC│  │  Go     │  (14种)   │  Java   │   │  Julia  │
    │  C++    │   │  仓颉   │           │  Scala  │   │  R      │
    └────┬────┘   └────┬────┘           └────┬────┘   └────┬────┘
         │              │                      │              │
    ┌────▼──────────────▼──────────────────────▼──────────────▼────┐
    │                   共享核心基础设施 (core/)                     │
    │  FunctionParser | DepResolver | 编译缓存 | 类型映射 | 序列化   │
    └───────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │     BridgeManager (manager.py)    │
                    │  编译器检测 / 路径配置 / 环境设置  │
                    │  状态查询 / 配置持久化             │
                    └──────────────────────────────────┘
```

### LangBridge 抽象基类

`LangBridge` 是所有语言桥接实现的统一抽象基类（定义在 `_base.py`），定义了标准接口规范：

**子类必须实现的抽象方法：**

| 方法 | 说明 |
|------|------|
| `compiler_available() -> bool` | 检测编译器是否可用 |
| `generate_code(spec: FunctionSpec) -> str` | 生成目标语言源代码 |
| `compile_code(code, func_name, cache_dir) -> str` | 编译代码，返回库文件路径 |
| `compile_project(project_dir, entry, output_dir) -> str` | 编译整个项目 |
| `call_func(lib_path, func_name, args, ret_type) -> Any` | 调用编译后的函数 |

**子类可以重写的方法：**

| 方法 | 说明 | 默认值 |
|------|------|--------|
| `supports_nested_functions() -> bool` | 是否支持函数嵌套 | `True` |
| `default_cache_dir() -> str` | 默认编译缓存目录 | 系统临时目录 |

**公共方法（所有语言共享）：**

- `decorator()` — 统一装饰器工厂，支持所有模式
- `check_cache()` / `save_to_cache()` — 编译缓存管理
- `get_cache_key()` — 基于 MD5 的内容哈希缓存键

---

## 核心概念

### 1. deps 依赖

当一个桥接函数需要调用其他辅助函数时，通过 `deps` 参数声明依赖：

```python
def helper(x: int) -> int:
    return "return x * 2"

@bridge.decorator(deps=[helper])
def compute(x: int) -> int:
    return "return helper(x) + 1"
```

框架会自动：
- 提取依赖函数的代码和类型信息
- 按依赖关系进行拓扑排序
- 将所有依赖函数一并编译进共享库

### 2. module_code 模块级代码

通过 `module_code` 参数可以注入模块级别的代码（如类型定义、全局变量、头文件包含等）：

```python
@bridge.decorator(module_code="""
    #include <math.h>
    #define PI 3.1415926
""")
def circle_area(r: float) -> float:
    return "return PI * r * r"
```

### 3. 编译缓存

框架内置基于内容哈希的编译缓存机制：

- 缓存键 = `函数名 + MD5(源代码)`
- 首次调用编译后，后续相同代码直接复用缓存
- 缓存目录默认为系统临时目录，可通过 `cache_dir` 参数自定义
- 项目模式下会计算项目所有源文件的内容哈希

### 4. 异步模式

设置 `async_mode=True` 后，装饰器返回异步函数，编译和调用在线程池中执行：

```python
@bridge.decorator(async_mode=True)
async def heavy_compute(x: int) -> int:
    return "..."  # 耗时计算

result = await heavy_compute(100)
```

异步模式使用 `ThreadPoolExecutor`（默认 4 个工作线程），避免阻塞事件循环。

### 5. fallback 回退函数

当编译器不可用或编译失败时，自动调用 `fallback` 参数指定的 Python 函数：

```python
def py_fib(n):
    if n <= 1:
        return 1
    return py_fib(n-1) + py_fib(n-2)

@bridge.decorator(fallback=py_fib)
def fib(n: int) -> int:
    return "..."  # 目标语言实现
```

---

## 三种使用模式

### 模式一：单函数装饰器模式

最常用的模式，每个 Python 函数对应一个目标语言函数。函数体返回目标语言的代码字符串。

**特点：**
- 即用即编译，首次调用时触发编译
- 自动类型映射（从 Python 注解推断目标语言类型）
- 支持 deps 依赖、module_code、编译缓存、fallback
- 支持同步和异步调用

**适用场景：** 单函数性能优化、算法加速、小型工具函数

### 模式二：only_code 仅代码模式

只生成目标语言代码，不进行编译和调用。可以将代码写入文件，用于代码生成场景。

**特点：**
- 只生成代码，不调用编译器
- 支持多种写入模式：覆盖、追加、插入、替换
- 可通过 `prefix` / `suffix` 包裹代码
- 同步异步均支持

**适用场景：** 代码生成工具、批量输出源文件、项目脚手架

**写入模式：**

| 模式 | 说明 |
|------|------|
| `overwrite` | 覆盖整个文件（默认） |
| `append` | 追加到文件末尾 |
| `insert:NN` | 插入到第 NN 行之后 |
| `replace:MM-NN` | 替换第 MM 到 NN 行 |

### 模式三：project 项目模式

编译整个项目目录，支持多文件项目。入口可以是 `main`（生成可执行文件）或指定函数名（生成共享库）。

**特点：**
- 编译整个项目目录下的所有源文件
- 基于全部源文件内容哈希的缓存
- `entry='main'` 生成可执行文件
- `entry='其他函数名'` 生成共享库并调用指定函数
- 支持同步和异步调用

**适用场景：** 大型项目集成、完整应用构建、已有项目复用

---

## 快速上手

### 示例：用 C 语言计算斐波那契数列

```python
from vools.bridge import c

# 定义回退函数（Python 实现）
def py_fib(n: int) -> int:
    if n <= 1:
        return 1
    return py_fib(n - 1) + py_fib(n - 2)

# 使用装饰器定义 C 语言实现
@c.decorator(
    fallback=py_fib,       # 编译器不可用时回退到 Python
    module_code="""
        #include <stdint.h>
    """,
)
def fib(n: int) -> int:
    return """
    if (n <= 1) {
        return 1;
    }
    return fib(n - 1) + fib(n - 2);
    """

# 调用（首次调用自动编译）
result = fib(20)
print(f"fib(20) = {result}")
```

### 示例：FreeBASIC 仅代码模式

```python
from vools.bridge import freebasic

@freebasic.decorator(
    only_code=True,                     # 启用仅代码模式
    output_file="output/hello.bas",     # 输出文件路径
    write_mode="overwrite",             # 写入模式
    prefix="' 自动生成的代码\n",         # 代码前缀
)
def hello(name: str) -> str:
    return """
    Print "Hello, " & name
    """

# 调用后返回输出文件路径
path = hello("World")
print(f"代码已写入: {path}")
```

### 示例：异步调用 + 项目模式

```python
import asyncio
from vools.bridge import rust

@rust.decorator(
    project_dir="./my_rust_project",    # 项目目录
    entry="main",                       # 入口函数（生成可执行文件）
    async_mode=True,                    # 异步模式
)
def my_app():
    pass  # 函数体留空，使用项目目录中的代码

async def main():
    # 异步编译并运行
    returncode, stdout, stderr = await my_app()
    print(f"退出码: {returncode}")
    print(f"输出: {stdout}")

asyncio.run(main())
```

### 检查语言可用性

```python
from vools.bridge import list_available, is_available, get_version

# 列出所有已注册的语言
all_langs = list_languages()
print(f"支持的语言: {all_langs}")

# 列出当前可用的语言
available = list_available()
print(f"可用的语言: {available}")

# 检查特定语言
if is_available("rust"):
    print(f"Rust 版本: {get_version('rust')}")
```

---

## API 概览

### 顶层导出 (`vools.bridge`)

**核心基础设施：**

| 名称 | 类型 | 说明 |
|------|------|------|
| `bridge_function` | 装饰器 | 通用桥接函数装饰器 |
| `bridge_module` | 装饰器 | 桥接模块（类）装饰器 |
| `bridge_func_name` | 装饰器 | 指定底层函数名 |
| `LibraryLoader` | 类 | 共享库加载器 |
| `SharedLibrary` | 类 | 共享库封装 |
| `load_library` | 函数 | 加载指定语言的共享库 |
| `load_from_path` | 函数 | 从路径加载共享库 |
| `CTypeMapper` | 类 | Python 与 ctypes 类型映射 |
| `Serializer` | 类 | 序列化工具 |

**管理器 API：**

| 名称 | 类型 | 说明 |
|------|------|------|
| `manager` | 单例 | BridgeManager 全局实例 |
| `BridgeManager` | 类 | 跨语言桥接统一管理器 |
| `LanguageConfig` | 数据类 | 语言配置 |
| `LanguageStatus` | 数据类 | 语言运行时状态 |
| `register_language()` | 函数 | 注册语言配置 |
| `is_available()` | 函数 | 检查语言是否可用 |
| `get_status()` | 函数 | 获取语言详细状态 |
| `get_compiler_path()` | 函数 | 获取编译器路径 |
| `get_version()` | 函数 | 获取语言版本 |
| `setup_runtime()` | 函数 | 设置运行时环境 |
| `list_languages()` | 函数 | 列出已注册语言 |
| `list_available()` | 函数 | 列出可用语言 |
| `set_compiler_path()` | 函数 | 设置编译器路径 |
| `add_compiler_path()` | 函数 | 添加编译器路径 |
| `set_runtime_path()` | 函数 | 设置运行时库路径 |
| `add_runtime_path()` | 函数 | 添加运行时库路径 |
| `save_config()` | 函数 | 保存配置到文件 |
| `load_config()` | 函数 | 从文件加载配置 |

### 各语言模块统一接口

每个语言模块都提供一致的装饰器接口：

```python
# 装饰器（所有语言通用）
@lang.decorator(
    deps=None,              # 依赖函数列表
    module_code=None,       # 模块级代码
    async_mode=False,       # 异步模式
    fallback=None,          # 回退函数
    cache_dir=None,         # 缓存目录
    ret_type=None,          # 返回类型覆盖
    only_code=False,        # 仅代码模式
    output_file=None,       # 输出文件路径（仅代码模式）
    write_mode='overwrite', # 写入模式（仅代码模式）
    prefix='',              # 代码前缀（仅代码模式）
    suffix='',              # 代码后缀（仅代码模式）
    project_dir=None,       # 项目目录（项目模式）
    entry='main',           # 入口函数（项目模式）
)
def my_func(x: int) -> int:
    return "..."  # 目标语言代码
```

---

## 子模块结构

```
vools/bridge/
├── __init__.py            # 包入口，延迟导入各语言模块
├── README.md              # 本文件
├── _base.py               # LangBridge 抽象基类 + 工具类
│   ├── FunctionSpec       # 函数规格数据类
│   ├── CompileResult      # 编译结果数据类
│   ├── FunctionParser     # 函数解析器
│   ├── DepResolver        # 依赖解析器
│   └── LangBridge         # 抽象基类
├── manager.py             # BridgeManager 统一管理器
│   ├── LanguageConfig     # 语言配置
│   ├── LanguageStatus     # 语言状态
│   └── BridgeManager      # 管理器主类
├── core/                  # 核心基础设施
│   ├── __init__.py
│   ├── loader.py          # 共享库加载器
│   ├── types.py           # C 类型映射
│   ├── decorators.py      # 通用装饰器
│   └── serialization.py   # 序列化工具
├── c/                     # C 语言桥接
├── cpp/                   # C++ 语言桥接
├── freebasic/             # FreeBASIC 语言桥接
├── nim/                   # Nim 语言桥接
├── go/                    # Go 语言桥接
├── cangjie/               # 仓颉语言桥接
├── rust/                  # Rust 语言桥接
├── mojo/                  # Mojo 语言桥接
├── csharp/                # C# 语言桥接
├── java/                  # Java 语言桥接
├── scala/                 # Scala 语言桥接
├── ruby/                  # Ruby 语言桥接
├── julia/                 # Julia 语言桥接
└── r/                     # R 语言桥接
```

### 各语言模块典型结构

每个语言模块通常包含以下文件：

| 文件 | 说明 |
|------|------|
| `__init__.py` | 模块入口，导出公共 API |
| `compiler.py` | 编译器封装、编译逻辑 |
| `loader.py` / `_loader.py` | 共享库加载、函数调用 |
| `types.py` | 类型映射（Python ↔ 目标语言） |
| `templates.py` | 代码生成模板 |
| `decorator.py` | 语言特定装饰器（可选） |
| `transport.py` | 数据传输层（部分语言） |

> **注意**：不同语言模块的内部结构可能略有差异，但对外暴露的装饰器接口是统一的。
