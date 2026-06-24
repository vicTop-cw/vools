# C++ 语言桥接模块

## 1. 语言简介

C++ 是一种通用的、编译式的编程语言，支持面向对象、泛型编程和低级内存操作。`vools.bridge.cpp` 模块提供了 C++ 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 C++ 代码为共享库（DLL/SO/DYLIB）
- 通过 ctypes 加载并调用编译后的 C++ 函数
- 使用 `extern "C"` 导出函数，避免 name mangling
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 C++ 加速函数
- 支持 GCC、Clang、MSVC 多种编译器

## 2. Bridge 类名

- **类名**: `CppBridge`
- **全局实例**: `_cpp_bridge`
- **装饰器**: `@cpp` 或 `@cpp_bridge.decorator`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@cpp` 装饰器快速定义 C++ 加速函数 |
| only_code 模式 | ✅ 支持 | 仅生成 C++ 代码，不编译 |
| project 模式 | ✅ 支持 | 编译整个 C++ 项目目录，可生成可执行文件或共享库 |
| 异步模式 | ✅ 支持 | `async_mode=True`，后台线程编译执行 |
| 回退机制 | ✅ 支持 | `fallback` 参数，编译失败时回退到 Python 实现 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |

## 4. 编译器要求

使用 C++ 语言桥接需要安装 C++ 编译器：

### Windows
- **MinGW-w64 (GCC)** (推荐)：https://www.mingw-w64.org/
- **Clang**：https://clang.llvm.org/
- **MSVC (Visual Studio)**：https://visualstudio.microsoft.com/
- 安装后确保 `g++`、`clang++` 或 `cl` 在系统 PATH 中

### Linux
```bash
# Debian/Ubuntu (GCC)
sudo apt-get install g++

# Debian/Ubuntu (Clang)
sudo apt-get install clang

# CentOS/RHEL
sudo yum install gcc-c++
```

### macOS
```bash
xcode-select --install
```

### 验证安装
```python
from vools.bridge.cpp import cpp_compiler_available, get_cpp_compiler_info

if cpp_compiler_available():
    info = get_cpp_compiler_info()
    print(f"C++ 编译器可用: {info['type']}")
    print(f"路径: {info['path']}")
    print(f"版本: {info['version']}")
else:
    print("C++ 编译器不可用，请安装 GCC、Clang 或 MSVC")
```

## 5. 类型映射表

| Python 类型 | C++ 类型 | ctypes 类型 | 说明 |
|------------|---------|------------|------|
| `int` | `int` | `c_int` | 有符号整数 |
| `float` | `double` | `c_double` | 双精度浮点数 |
| `bool` | `bool` | `c_bool` | 布尔值 |
| `str` | `const char*` | `c_char_p` | UTF-8 字符串，自动编码/解码 |
| `bytes` | `const char*` | `c_char_p` | 字节串 |
| `None` | `void` | `None` | 无返回值 |

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.cpp import cpp

@cpp
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

@cpp(fallback=python_fallback)
def square(x: int) -> int:
    return "return x * x;"

result = square(5)
print(result)  # 输出: 25
```

### 带 STL 头文件

```python
@cpp(includes=['<vector>', '<algorithm>'])
def sum_of_squares(n: int) -> int:
    return """
    std::vector<int> v;
    for (int i = 1; i <= n; i++) {
        v.push_back(i * i);
    }
    int sum = 0;
    for (int x : v) sum += x;
    return sum;
    """

result = sum_of_squares(10)
print(result)  # 输出: 385
```

### 字符串处理

```python
@cpp(includes=['<cstring>'])
def str_length(s: str) -> int:
    return "return (int)strlen(s);"

length = str_length("hello")
print(length)  # 输出: 5
```

### 异步模式

```python
import asyncio
from vools.bridge.cpp import cpp

@cpp(async_mode=True)
async def fib(n: int) -> int:
    return """
    if (n <= 1) return 1;
    return fib(n - 1) + fib(n - 2);
    """

async def main():
    result = await fib(20)
    print(f"fib(20) = {result}")

asyncio.run(main())
```

## 7. only_code 模式示例

仅生成 C++ 代码，不编译执行：

```python
@cpp(mode='ONLY_CODE')
def generate_code(a: int, b: int) -> int:
    return "return a + b;"

code = generate_code(1, 2)
print(code)
# 输出:
# extern "C" int generate_code(int a, int b) {
#     return a + b;
# }
```

### 使用 LangBridge 的 only_code 模式

```python
from vools.bridge.cpp import CppBridge

cpp_bridge = CppBridge()

@cpp_bridge.decorator(only_code=True)
def add(a: int, b: int) -> int:
    return "return a + b;"

code = add(1, 2)
print(code)
```

### 输出到文件

```python
@cpp_bridge.decorator(only_code=True, output_file='./output/add.cpp')
def add(a: int, b: int) -> int:
    return "return a + b;"

file_path = add(1, 2)
print(f"代码已写入: {file_path}")
```

## 8. project 模式示例

### 编译 C++ 项目为可执行文件

```python
from vools.bridge.cpp import CppBridge

cpp_bridge = CppBridge()

# 项目目录结构:
# my_cpp_project/
#   main.cpp
#   utils.cpp
#   utils.h

returncode, stdout, stderr = cpp_bridge.decorator(
    project_dir='./my_cpp_project',
    entry='main'
)(lambda: None)()

print(f"返回码: {returncode}")
print(f"标准输出: {stdout}")
```

### 编译 C++ 项目为共享库

```python
# 编译为共享库，导出指定函数
@cpp_bridge.decorator(project_dir='./my_cpp_project', entry='my_function')
def my_function(a: int, b: int) -> int:
    pass

result = my_function(10, 20)
print(result)
```

### 手动调用 project 编译

```python
bridge = CppBridge()

# 编译为可执行文件
exe_path = bridge.compile_project('./my_cpp_project', entry='main')
print(f"可执行文件: {exe_path}")

# 编译为共享库
dll_path = bridge.compile_project('./my_cpp_project', entry='my_func')
print(f"共享库: {dll_path}")
```

## 9. 注意事项

### extern "C" 导出
- 所有导出函数自动使用 `extern "C"` 声明，避免 C++ name mangling
- 这样 ctypes 才能正确找到并调用函数
- 如果需要 C++ 类和成员函数，需通过 `extern "C"` 包装函数调用

### 头文件包含
- 使用 `includes` 参数添加头文件，如 `includes=['<vector>', '<string>']`
- 或使用 `module_code` 参数添加自定义代码和头文件
- 也可使用 `set_includes()` 方法设置全局头文件列表

### 编译器选择
- 自动检测可用的 C++ 编译器（GCC、Clang、MSVC）
- Windows 优先使用 MinGW GCC，也支持 Clang 和 MSVC
- 可通过 `get_cpp_compiler_info()` 查看当前使用的编译器

### 编译缓存
- 缓存目录默认为系统临时目录下的 `vools_cpp_cache`
- 相同代码内容只会编译一次，后续调用直接使用缓存
- 可通过 `cache_dir` 参数自定义缓存目录

### 内存安全
- C++ 虽然比 C 更安全，但仍需注意内存管理
- 避免返回局部变量的指针或引用
- 使用 STL 容器时注意对象生命周期

### 字符串处理
- `str` 类型会自动以 UTF-8 编码传递为 `const char*`
- 返回值为 `c_char_p` 时会自动解码为 Python `str`
- 如需返回 C++ `std::string`，需通过 `c_str()` 转换并注意内存管理

### 平台差异
- Windows 下生成 `.dll`，Linux 下生成 `.so`，macOS 下生成 `.dylib`
- MSVC 编译器使用 `/LD` 选项生成 DLL，GCC/Clang 使用 `-shared`
- 不同编译器的 C++ 标准库实现可能存在差异

### 异常处理
- C++ 异常不能跨越 C ABI 边界传递
- 建议在 C++ 代码内部捕获异常，通过返回值或错误码传递错误
- 或使用 `extern "C"` 包装函数统一处理异常

### 相关资源
- [C++ 参考手册](https://en.cppreference.com/w/)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
- [MinGW-w64 官网](https://www.mingw-w64.org/)
