# vools.bridge.vbnet — VB.NET 语言桥接

> .NET 生态桥接，支持通过 dotnet CLI 编译并执行 VB.NET 代码

## 语言简介

VB.NET 是微软开发的现代编程语言，属于 .NET 平台，是 Visual Basic 的后继者。语法简洁易学，广泛用于 Windows 桌面应用、Web 开发等。本模块提供 VB.NET 代码编译与跨语言桥接能力。

## Bridge 类名

**`VBNetBridge`** — 继承自 `LangBridge` 抽象基类的 VB.NET 桥接实现

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@vbnet` 装饰器，函数体 return VB.NET 代码字符串 |
| only_code 模式 | ✅ | 只生成 VB.NET 源码，不编译/执行 |
| project 模式 | ✅ | 编译整个 VB.NET 项目目录 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ✅ | `async_mode=True` 返回 VBNetFuture |
| 回退机制 | ✅ | `fallback` 参数支持 Python 回退实现 |
| 依赖函数 | ✅ | `deps` 参数支持函数依赖 |
| 模块代码 | ✅ | `module_code` 参数支持模块级代码 |
| 类型转换 | ✅ | Python ↔ VB.NET 自动转换 |

## 运行环境要求

- **.NET SDK**: >= 6.0（推荐 .NET 9）
- **安装方式**：
  - Windows: <https://dotnet.microsoft.com/download>
  - Linux: `sudo apt install dotnet-sdk-9.0`
  - macOS: `brew install --cask dotnet-sdk`

## 类型映射

| Python | VB.NET |
|--------|--------|
| `int` | `Integer` |
| `float` | `Double` |
| `str` | `String` |
| `bool` | `Boolean` |
| `bytes` | `Byte()` |
| `list` | `Integer()` |
| `dict` | `Object` |
| `None` | `Void` |

## 快速使用示例

### 基本使用

```python
from vools.bridge.vbnet import vbnet, vbnet_compiler_available

if vbnet_compiler_available():
    @vbnet
    def add(a: int, b: int) -> int:
        return "Return a + b"

    print(add(2, 3))  # 5

    @vbnet
    def greet(name: str) -> str:
        return 'Return $"Hello, {name}!"'

    print(greet("World"))  # Hello, World!
```

### 异步执行

```python
import asyncio
from vools.bridge.vbnet import vbnet

@vbnet(async_mode=True)
async def compute(x: int) -> int:
    return "Return x * x"

async def main():
    result = await compute(5)
    print(result)  # 25

asyncio.run(main())
```

### 回退机制

```python
from vools.bridge.vbnet import vbnet

@vbnet(fallback=lambda a, b: a + b)
def add(a: int, b: int) -> int:
    return "Return a + b"

# 当 dotnet 不可用时，自动使用 Python lambda
result = add(2, 3)  # 5
```

## only_code 模式示例

```python
from vools.bridge.vbnet import vbnet

@vbnet(only_code=True, output_file="output.vb")
def add(a: int, b: int) -> int:
    return "Return a + b"

code = add(1, 2)
print(code)  # 输出生成的 VB.NET 代码
# 代码同时写入 output.vb 文件
```

## project 模式示例

```python
from vools.bridge.vbnet import vbnet

@vbnet(project_dir="./my_vb_project", entry="main")
def my_app():
    pass

# 编译整个项目目录并生成可执行文件
# 项目目录中需要有 .vbproj 文件
result = my_app()
```

### 依赖函数示例

```python
from vools.bridge.vbnet import vbnet

def helper(x: int) -> int:
    return "Return x * 2"

@vbnet(deps=[helper])
def compute(a: int, b: int) -> int:
    return "Return helper(a) + b"

print(compute(3, 1))  # 7
```

### 模块级代码示例

```python
from vools.bridge.vbnet import vbnet

module_code = """
Imports System.Linq
Imports System.Collections.Generic
"""

@vbnet(module_code=module_code)
def sum_list(numbers: list) -> int:
    return "Return numbers.Sum()"
```

## 注意事项

- 函数体通过 `return` 语句返回 VB.NET 代码字符串
- 方法会自动添加 `DllExport` 属性和 `Public Shared` 修饰符
- 字符串参数通过 UTF-8 编码传递，返回字符串自动解码
- 编译需要 .NET SDK，首次调用会编译，后续命中缓存
- 依赖函数按声明顺序生成，支持多级依赖
- VB.NET 不区分大小写，但建议保持一致的命名风格
