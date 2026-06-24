# C 语言桥接模块

## 1. 语言简介

C 语言是一种通用的、过程式的计算机编程语言，被广泛应用于系统编程和底层开发。`vools.bridge.c` 模块提供了 C 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 C 代码为共享库（DLL/SO/DYLIB）
- 通过 ctypes 加载并调用编译后的 C 函数
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 C 加速函数

## 2. Bridge 类名

- **类名**: `CBridge`
- **全局实例**: `_c_bridge`
- **装饰器**: `@c_bridge.decorator` 或直接使用 `CDLLWrapper` / `load_dll` / `c_dll`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `CBridge` 实例的 `decorator()` 方法，或直接使用 `c_dll` 装饰器加载预编译 DLL |
| only_code 模式 | ✅ 支持 | 仅生成 C 代码，不编译 |
| project 模式 | ✅ 支持 | 编译整个 C 项目目录，可生成可执行文件或共享库 |
| 异步模式 | ✅ 支持 | `async_mode=True`，后台线程编译执行 |
| 回退机制 | ✅ 支持 | `fallback` 参数，编译失败时回退到 Python 实现 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |

## 4. 编译器要求

使用 C 语言桥接需要安装 C 编译器：

### Windows
- **MinGW-w64** (推荐)：https://www.mingw-w64.org/
- **MSVC** (Visual Studio)：https://visualstudio.microsoft.com/
- 安装后确保 `gcc` 或 `cl` 在系统 PATH 中

### Linux
```bash
# Debian/Ubuntu
sudo apt-get install gcc

# CentOS/RHEL
sudo yum install gcc
```

### macOS
```bash
xcode-select --install
```

### 验证安装
```python
from vools.bridge.c import c_compiler_available

if c_compiler_available():
    print("C 编译器可用")
else:
    print("C 编译器不可用，请安装 GCC 或 Clang")
```

## 5. 类型映射表

| Python 类型 | C 类型 | ctypes 类型 | 说明 |
|------------|--------|------------|------|
| `int` | `int` | `c_int` | 有符号整数 |
| `float` | `double` | `c_double` | 双精度浮点数 |
| `bool` | `int` | `c_int` | 布尔值（0/1） |
| `str` | `const char*` | `c_char_p` | UTF-8 字符串，自动编码/解码 |
| `bytes` | `const char*` | `c_char_p` | 字节串 |
| `None` | `void` | `None` | 无返回值 |

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.c import CBridge

c_bridge = CBridge()

@c_bridge.decorator
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "return a + b;"

result = add(3, 5)
print(result)  # 输出: 8
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * x

@c_bridge.decorator(fallback=python_fallback)
def square(x: int) -> int:
    return "return x * x;"

result = square(5)
print(result)  # 输出: 25
```

### 字符串处理

```python
@c_bridge.decorator(module_code='#include <string.h>')
def str_length(s: str) -> int:
    return "return (int)strlen(s);"

length = str_length("hello")
print(length)  # 输出: 5
```

### 异步模式

```python
import asyncio

@c_bridge.decorator(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    int result = 0;
    for (int i = 0; i < n; i++) {
        result += i;
    }
    return result;
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

## 7. only_code 模式示例

仅生成 C 代码，不编译执行：

```python
@c_bridge.decorator(only_code=True)
def generate_code(a: int, b: int) -> int:
    return "return a + b;"

code = generate_code(1, 2)
print(code)
# 输出:
# int generate_code(int a, int b) {
#     return a + b;
# }
```

### 输出到文件

```python
@c_bridge.decorator(only_code=True, output_file='./output/add.c')
def add(a: int, b: int) -> int:
    return "return a + b;"

file_path = add(1, 2)
print(f"代码已写入: {file_path}")
```

### 带前缀和后缀

```python
@c_bridge.decorator(
    only_code=True,
    prefix='#include <stdio.h>\n\n',
    suffix='\nint main() { return add(1, 2); }\n'
)
def add(a: int, b: int) -> int:
    return "return a + b;"

code = add(1, 2)
print(code)
```

## 8. project 模式示例

### 编译 C 项目为可执行文件

```python
from vools.bridge.c import CBridge

c_bridge = CBridge()

# 项目目录结构:
# my_c_project/
#   main.c
#   utils.c
#   utils.h

returncode, stdout, stderr = c_bridge.decorator(
    project_dir='./my_c_project',
    entry='main'
)(lambda: None)()

print(f"返回码: {returncode}")
print(f"标准输出: {stdout}")
```

### 编译 C 项目为共享库

```python
# 编译为共享库，导出指定函数
@c_bridge.decorator(project_dir='./my_c_project', entry='my_function')
def my_function(a: int, b: int) -> int:
    pass

result = my_function(10, 20)
print(result)
```

### 手动调用 project 编译

```python
bridge = CBridge()

# 编译为可执行文件
exe_path = bridge.compile_project('./my_c_project', entry='main')
print(f"可执行文件: {exe_path}")

# 编译为共享库
dll_path = bridge.compile_project('./my_c_project', entry='my_func')
print(f"共享库: {dll_path}")
```

## 9. 注意事项

### 调用约定
- C 函数默认使用 `cdecl` 调用约定，与 Python ctypes 默认一致
- 如果需要使用其他调用约定（如 `stdcall`），需手动调整

### 字符串处理
- `str` 类型会自动以 UTF-8 编码传递给 C 函数（`const char*`）
- 返回值为 `c_char_p` 时会自动解码为 Python `str`
- 注意：C 函数返回的字符串指针必须指向静态存储或堆内存，避免返回局部变量地址

### 头文件包含
- 使用 `module_code` 参数添加头文件包含和宏定义
- 或使用 `set_includes()` 方法设置全局头文件列表：
  ```python
  c_bridge.set_includes(['<stdio.h>', '<stdlib.h>', '"my_header.h"'])
  ```

### 编译缓存
- 缓存目录默认为系统临时目录下的 `vools_c_cache`
- 相同代码内容只会编译一次，后续调用直接使用缓存
- 可通过 `cache_dir` 参数自定义缓存目录

### 内存安全
- C 语言没有内存安全保证，编写代码时需注意缓冲区溢出、空指针等问题
- 传递数组时需确保长度参数正确
- 建议在 Python 侧做好参数校验

### 平台差异
- Windows 下生成 `.dll`，Linux 下生成 `.so`，macOS 下生成 `.dylib`
- Windows 下可使用 MinGW 或 MSVC 编译器
- 不同平台的 C 标准库可能存在细微差异

### 相关资源
- [C 语言参考手册](https://en.cppreference.com/w/c)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
