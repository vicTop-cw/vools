# vools.bridge.csharp — C# 语言桥接

> .NET 生态桥接，支持通过 dotnet CLI 编译并执行 C# 代码

## 语言简介

C# 是微软开发的现代编程语言，属于 .NET 平台，广泛用于企业级应用、游戏开发（Unity）、Web 后端等。本模块提供 C# 代码编译与跨语言桥接能力。

## Bridge 类名

**`CSharpBridge`** — 继承自 `LangBridge` 抽象基类的 C# 桥接实现

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@cs` 装饰器，函数体写在 docstring 中 |
| only_code 模式 | ✅ | 只生成 C# 源码，不编译/执行 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ✅ | `async_mode=True` 返回 CSharpTask |
| 回退机制 | ✅ | `fallback` 参数支持 Python 回退实现 |
| 类型转换 | ✅ | Python ↔ C# 自动转换 |

## 运行环境要求

- **.NET SDK**: >= 6.0（推荐 .NET 9）
- **安装方式**：
  - Windows: `https://dotnet.microsoft.com/download`
  - Linux: `sudo apt install dotnet-sdk-9.0`
  - macOS: `brew install --cask dotnet-sdk`

## 快速开始

### 基本使用

```python
from vools.bridge.csharp import cs, cs_compiler_available

if cs_compiler_available():
    @cs
    def add(a, b):
        """
        public static long Add(long a, long b) => a + b;
        """

    print(add(2, 3))  # 5

    @cs
    def greet(name):
        """
        public static string Greet(string name) => $"Hello, {name}!";
        """

    print(greet("World"))  # Hello, World!
```

### 回退机制

```python
@cs(fallback=lambda a, b: a + b)
def add(a, b):
    """
    public static long Add(long a, long b) => a + b;
    """

# 当 dotnet 不可用时，自动使用 Python lambda
result = add(2, 3)  # 5
```

### 字符串处理

```python
@cs
def to_upper(text):
    """
    public static string ToUpper(string text) => text.ToUpper();
    """
```

## 类型映射

| Python | C# |
|--------|-----|
| `int` | `long` |
| `float` | `double` |
| `str` | `string` |
| `bool` | `bool` |
| `list` | `object[]` |
| `dict` | `Dictionary<string, object>` |
| `None` | `object` |

## 注意事项

- 函数体必须写在 **docstring** 中
- 方法必须声明为 **public static**
- 数据通过 **JSON 序列化** 交换
- 编译需要 .NET SDK，首次调用会编译，后续命中缓存