# Nim 语言桥接模块

## 1. 语言简介

Nim 是一种静态类型的、编译式的、命令式的编程语言，具有高效的运行性能和表达力。它结合了 Python 的简洁语法和 C/C++ 的性能。`vools.bridge.nim` 模块提供了 Nim 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 Nim 代码为共享库（DLL/SO）
- 通过 ctypes 加载并调用编译后的 Nim 函数
- 使用 `exportc` 编译指示确保 C ABI 兼容
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 Nim 加速函数
- 内置丰富的预置函数（加密、序列处理、日期时间等）

## 2. Bridge 类名

- **类名**: `NimBridge`
- **全局实例**: `_nim_bridge`
- **装饰器**: `@nim` 或 `@nim_bridge.decorator`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@nim` 装饰器快速定义 Nim 加速函数 |
| only_code 模式 | ✅ 支持 | 仅生成 Nim 代码，不编译 |
| project 模式 | ✅ 支持 | 编译整个 Nim 项目目录，可生成可执行文件或共享库 |
| 异步模式 | ✅ 支持 | `async_mode=True`，后台线程编译执行 |
| 回退机制 | ✅ 支持 | `fallback` 参数，编译失败时回退到 Python 实现 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |
| 预置函数库 | ✅ 支持 | 内置加密、序列处理、日期时间等常用函数 |

## 4. 编译器要求

使用 Nim 语言桥接需要安装 Nim 编译器：

### Windows
- 下载并安装 Nim：https://nim-lang.org/install_windows.html
- 或使用 `choosenim` 工具安装：https://github.com/dom96/choosenim
- 安装后确保 `nim` 在系统 PATH 中

### Linux
```bash
# 使用 choosenim 安装（推荐）
curl https://nim-lang.org/choosenim/init.sh -sSf | sh

# 或使用包管理器
# Debian/Ubuntu
sudo apt-get install nim

# Arch Linux
sudo pacman -S nim
```

### macOS
```bash
# 使用 Homebrew
brew install nim

# 或使用 choosenim
curl https://nim-lang.org/choosenim/init.sh -sSf | sh
```

### 验证安装
```python
from vools.bridge.nim import nim_compiler_available, is_nim_available

if nim_compiler_available():
    print("Nim 编译器可用")
else:
    print("Nim 编译器不可用，请安装 Nim 工具链")

if is_nim_available():
    print("Nim 桥接可用（编译器或预编译库）")
```

## 5. 类型映射表

| Python 类型 | Nim 类型 | ctypes 类型 | 说明 |
|------------|---------|------------|------|
| `int` | `cint` | `c_int` | C 兼容整数 |
| `float` | `cdouble` | `c_double` | C 兼容双精度浮点数 |
| `bool` | `cbool` | `c_bool` | C 兼容布尔值 |
| `str` | `cstring` | `c_char_p` | C 字符串（以 null 结尾） |
| `bytes` | `cstring` | `c_char_p` | 字节串 |
| `None` | `void` | `None` | 无返回值 |

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.nim import nim

@nim
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * x

@nim(fallback=python_fallback)
def square(x: int) -> int:
    return "x * x"

result = square(5)
print(result)  # 输出: 25
```

### 字符串处理

```python
@nim
def greet(name: str) -> str:
    return '"Hello, " & name & "!"'

message = greet("World")
print(message)  # 输出: Hello, World!
```

### 递归函数

```python
@nim
def fib(n: int) -> int:
    return """
    if n <= 1:
        return 1
    return fib(n - 1) + fib(n - 2)
    """

result = fib(10)
print(result)  # 输出: 89
```

### 异步模式

```python
import asyncio
from vools.bridge.nim import nim

@nim(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    var result = 0
    for i in 0..<n:
        result += i
    return result
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

### 使用内置预置函数

```python
from vools.bridge.nim import md5, sha256, base64_encode

# 加密函数
hash_md5 = md5(b"hello world")
hash_sha256 = sha256(b"hello world")

# 编码函数
encoded = base64_encode(b"hello world")
```

## 7. only_code 模式示例

仅生成 Nim 代码，不编译执行：

```python
from vools.bridge.nim import NimBridge

nim_bridge = NimBridge()

@nim_bridge.decorator(only_code=True)
def generate_code(a: int, b: int) -> int:
    return "a + b"

code = generate_code(1, 2)
print(code)
# 输出:
# proc generate_code*(a: cint, b: cint): cint {.exportc: "generate_code".} =
#   a + b
```

### 输出到文件

```python
@nim_bridge.decorator(only_code=True, output_file='./output/add.nim')
def add(a: int, b: int) -> int:
    return "a + b"

file_path = add(1, 2)
print(f"代码已写入: {file_path}")
```

### 带前缀和后缀

```python
@nim_bridge.decorator(
    only_code=True,
    prefix='import strutils\n\n',
    suffix='\nwhen isMainModule:\n  echo add(1, 2)\n'
)
def add(a: int, b: int) -> int:
    return "a + b"

code = add(1, 2)
print(code)
```

## 8. project 模式示例

### 编译 Nim 项目为可执行文件

```python
from vools.bridge.nim import NimBridge

nim_bridge = NimBridge()

# 项目目录结构:
# my_nim_project/
#   main.nim
#   utils.nim

returncode, stdout, stderr = nim_bridge.decorator(
    project_dir='./my_nim_project',
    entry='main'
)(lambda: None)()

print(f"返回码: {returncode}")
print(f"标准输出: {stdout}")
```

### 编译 Nim 项目为共享库

```python
# 编译为共享库，导出指定函数
@nim_bridge.decorator(project_dir='./my_nim_project', entry='my_function')
def my_function(a: int, b: int) -> int:
    pass

result = my_function(10, 20)
print(result)
```

### 手动调用 project 编译

```python
bridge = NimBridge()

# 编译为可执行文件
exe_path = bridge.compile_project('./my_nim_project', entry='main')
print(f"可执行文件: {exe_path}")

# 编译为共享库
dll_path = bridge.compile_project('./my_nim_project', entry='my_func')
print(f"共享库: {dll_path}")
```

## 9. 注意事项

### 导出函数
- 所有导出函数自动使用 `exportc` 编译指示，确保 C ABI 兼容
- 函数名后面的 `*` 表示该函数是公开导出的
- `exportc` 确保函数符号名与 Python 端调用的名称一致

### 类型兼容性
- 使用 `cint`、`cdouble`、`cbool`、`cstring` 等 C 兼容类型
- 避免使用 Nim 原生的 `int`、`float`、`string` 等类型，它们的大小可能与平台相关
- 字符串使用 `cstring` 类型（以 null 结尾的 C 字符串）

### 字符串处理
- `str` 类型会自动以 UTF-8 编码传递为 `cstring`
- 返回值为 `c_char_p` 时会自动解码为 Python `str`
- Nim 端的 `string` 类型不能直接跨 C ABI 边界传递，需转换为 `cstring`

### 编译缓存
- 缓存目录默认为系统临时目录下的 `vools_nim_cache`
- 相同代码内容只会编译一次，后续调用直接使用缓存
- 可通过 `cache_dir` 参数自定义缓存目录

### 内存管理
- Nim 有自己的垃圾回收机制，跨语言调用时需注意内存所有权
- 不要在 Python 侧释放 Nim 分配的内存
- 字符串返回值确保是 `cstring` 类型，且指向的内存是持久的

### 预置函数库
- 模块内置了丰富的预置函数，无需编译即可使用
- 包括：加密哈希（MD5、SHA1、SHA256、HMAC）、序列处理（map、filter、reduce、sort 等）、日期时间处理、编码（Base64、zlib）等
- 如果 Nim 编译器不可用，预置函数会自动回退到 Python 实现

### 平台差异
- Windows 下生成 `.dll`，Linux 下生成 `.so`
- Windows 上需要 MinGW 运行时支持
- 不同平台的 Nim 编译器选项略有不同

### 缩进语法
- Nim 使用缩进表示代码块（类似 Python）
- 标准缩进为 2 个空格
- 函数体代码会自动缩进，用户只需提供函数体内部的代码

### 相关资源
- [Nim 官方文档](https://nim-lang.org/docs.html)
- [Nim 手册](https://nim-lang.org/docs/manual.html)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
