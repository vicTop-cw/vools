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

## API.tlb COM 组件桥接

除了编译器桥接模式外，`vools.bridge.vbnet` 还提供了 `api` 子包，用于直接调用已注册的 API.tlb COM 组件，提供 Windows 自动化能力。

### 功能概述

`api` 子包封装了 API.tlb 中的 7 个功能模块：

| 模块 | 说明 |
|------|------|
| `api.Window` | 窗口操作（查找、移动、大小、状态等） |
| `api.Mouse` | 鼠标操作（移动、点击、滚轮等） |
| `api.Keyboard` | 键盘操作（按键模拟、状态查询等） |
| `api.Image` | 图像处理（截图、像素、变换等） |
| `api.FileSystem` | 文件系统操作（文件/目录管理） |
| `api.Process` | 进程管理（启动、查询、终止等） |
| `api.Network` | 网络功能（下载、URL编解码等） |

### 前置条件

- Windows 操作系统
- API.dll / API.tlb 已正确注册为 COM 组件
- pywin32 (`pip install pywin32`)

### 快速示例

```python
from vools.bridge.vbnet import api

if api.is_api_available():
    # 查找记事本窗口
    hwnd = api.Window.FindWindow("Notepad", None)
    if hwnd:
        print(f"记事本句柄: {hwnd}")
        title = api.Window.GetWindowText(hwnd)
        print(f"窗口标题: {title}")

    # 鼠标操作
    api.Mouse.MouseMove(100, 200)
    api.Mouse.LeftClick()

    # 键盘输入
    api.Keyboard.SendKeys("Hello, World!")
```

### 详细文档

更多详细信息请参考 [api 子包 README](api/README.md)。

## 注意事项

- 函数体通过 `return` 语句返回 VB.NET 代码字符串
- 方法会自动添加 `DllExport` 属性和 `Public Shared` 修饰符
- 字符串参数通过 UTF-8 编码传递，返回字符串自动解码
- 编译需要 .NET SDK，首次调用会编译，后续命中缓存
- 依赖函数按声明顺序生成，支持多级依赖
- VB.NET 不区分大小写，但建议保持一致的命名风格
