# FreeBASIC 语言桥接模块

## 1. 语言简介

FreeBASIC 是一款自由开源的 BASIC 语言编译器，完全兼容 QuickBASIC，并提供了现代编程语言的特性。`vools.bridge.freebasic` 模块提供了 FreeBASIC 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 FreeBASIC 代码为共享库（DLL/SO/DYLIB）
- 通过 ctypes 加载并调用编译后的函数
- 使用 `Export` 关键字导出函数，确保 C ABI 兼容
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 FreeBASIC 加速函数
- 列表/数组参数通过指针 + 长度传递，零拷贝
- Transport 抽象层，可注入自定义序列化策略

## 2. Bridge 类名

- **类名**: `FreeBasicBridge`
- **全局实例**: `_fb_bridge`
- **装饰器**: `@freebasic` 或 `@fb_bridge.decorator`
- **类型映射器**: 内置类型映射系统 `PY_TO_FB_TYPE`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@freebasic` 装饰器快速定义 FreeBASIC 加速函数 |
| only_code 模式 | ✅ 支持 | `mode='ONLY_CODE'`，仅生成 FreeBASIC 代码，不编译 |
| project 模式 | ⚠️ 部分 | 可通过 fbc 手动编译整个项目 |
| 异步模式 | ✅ 支持 | `async_mode=True`，返回 Future，可 await |
| 回退机制 | ✅ 支持 | fallback 参数，编译失败时回退 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |
| 免序列化数组 | ✅ 支持 | list 参数通过指针 + 长度传递，零拷贝 |
| Transport 抽象 | ✅ 支持 | 可注入自定义传输层 |

## 4. 编译器要求

使用 FreeBASIC 语言桥接需要安装 FreeBASIC 编译器：

### Windows

从 [FreeBASIC 官网](https://www.freebasic.net/) 下载安装包：

```bash
# 下载并安装 FreeBASIC
# https://www.freebasic.net/
# 将 fbc.exe 添加到系统 PATH
```

### Linux

```bash
# Ubuntu/Debian
sudo apt-get install freebasic

# 或者从官网下载安装包
```

### 验证安装
```bash
fbc --version
```

### Python 端验证
```python
from vools.bridge.freebasic import is_freebasic_available, fbc_available

if fbc_available():
    print("FreeBASIC 编译器可用")
else:
    print("FreeBASIC 编译器不可用，请安装 fbc 并添加到 PATH")
```

## 5. 类型映射表

| Python 类型 | FreeBASIC 类型 | ctypes 类型 | 说明 |
|------------|---------------|------------|------|
| `int` | `Long` | `c_long` | 32 位有符号整数 |
| `float` | `Double` | `c_double` | 双精度浮点数 |
| `bool` | `Long` | `c_long` | 布尔值（0/1） |
| `str` / `bytes` | `ZString Ptr` | `c_char_p` | C 字符串指针 |
| `list[int]` | `Long Ptr` + `n As Long` | `POINTER(c_long)` + `c_long` | 整数数组指针 + 长度 |
| `list[float]` | `Double Ptr` + `n As Long` | `POINTER(c_double)` + `c_long` | 浮点数数组指针 + 长度 |
| `None` | `Sub` 或函数无返回值 | `restype = None` | 无返回值 |

> **注意**：`list` 类型的参数会自动展开为 `(指针, 长度)` 两个参数。例如 `arr: list` 在 FreeBASIC 端会变成 `arr As Long Ptr, n As Long`。

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.freebasic import freebasic

@freebasic
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "Return a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@freebasic
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return """
    If n <= 1 Then
        Return 1
    Else
        Return fib(n - 1) + fib(n - 2)
    End If
    """

result = fib(10)
print(result)  # 输出: 89
```

### 数组求和（免序列化）

```python
@freebasic
def sum_arr(arr: list) -> int:
    """
    数组求和（零拷贝）
    
    list 参数自动展开为 (ptr, n) 两个参数：
    - arr: Long Ptr（数组指针）
    - n: Long（数组长度，由参数名 + '_n' 后缀自动生成）
    """
    return """
    Dim As Long i, total
    total = 0
    For i = 0 To n - 1
        total += arr[i]
    Next
    Return total
    """

print(sum_arr([1, 2, 3, 4, 5]))  # 输出: 15
```

### 字符串处理

```python
@freebasic
def greet(name: str) -> str:
    return """
    ' 字符串处理示例
    ' name 是 ZString Ptr 类型
    Return name
    """

message = greet("World")
print(message)
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * x

@freebasic(fallback=python_fallback)
def square(x: int) -> int:
    return "Return x * x"

result = square(5)
print(result)  # 输出: 25
```

### 异步模式

```python
import asyncio
from vools.bridge.freebasic import freebasic

@freebasic(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    Dim As Long i, total
    total = 0
    For i = 0 To n - 1
        total += i
    Next
    Return total
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

## 7. only_code 模式示例

仅生成 FreeBASIC 代码，不编译执行：

```python
@freebasic(mode='ONLY_CODE')
def generate_code(a: int, b: int) -> int:
    return "Return a + b"

code = generate_code(1, 2)
print(code)
# 输出完整的 FreeBASIC 源码，包括函数声明和 Export 关键字
```

### 使用 LangBridge 的 only_code 模式

```python
from vools.bridge.freebasic import FreeBasicBridge

fb_bridge = FreeBasicBridge()

@fb_bridge.decorator(only_code=True)
def add(a: int, b: int) -> int:
    return "Return a + b"

code = add(1, 2)
print(code)
```

### 输出到文件

```python
@fb_bridge.decorator(only_code=True, output_file='./output/add.bas')
def add(a: int, b: int) -> int:
    return "Return a + b"

file_path = add(1, 2)
print(f"代码已写入: {file_path}")
```

## 8. project 模式示例

### 手动编译 FreeBASIC 代码

```python
import subprocess

# 手动调用 fbc 编译
source_file = 'my_program.bas'
output_dll = 'my_program.dll'

result = subprocess.run(
    ['fbc', '-dll', source_file, '-o', output_dll],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print(f"编译成功: {output_dll}")
else:
    print(f"编译失败: {result.stderr}")
```

### 加载 DLL 并调用

```python
import ctypes
from vools.bridge.core.types import CTypeMapper

# 加载 DLL
lib = ctypes.CDLL('./my_program.dll')

# 设置函数签名
add_func = lib.add
add_func.argtypes = [CTypeMapper.get_ctype(int), CTypeMapper.get_ctype(int)]
add_func.restype = CTypeMapper.get_ctype(int)

# 调用函数
result = add_func(10, 20)
print(f"结果: {result}")
```

### 使用 FreeBASIC 模块

```python
from vools.bridge.freebasic import compile_freebasic_code, call_freebasic_function

# 手动编译
dll_path = compile_freebasic_code(
    code='''
    Function add Alias "add" (a As Long, b As Long) As Long Export
        Return a + b
    End Function
    ''',
    func_name='add'
)

# 调用
result = call_freebasic_function(dll_path, 'add', [5, 3], ret_type=int)
print(result)  # 输出: 8
```

## 9. 注意事项

### 函数签名
- FreeBASIC 导出函数必须使用 `Export` 关键字
- 使用 C 调用约定时需注意参数传递方式
- 自动签名生成模式下会自动处理这些细节

### 数组传递（免序列化）
- `list` 类型的参数会自动展开为 `(指针, 长度)` 两个参数
- 例如 `arr: list` → `arr As Long Ptr, n As Long`
- 长度参数名规则：原参数名 + `_n` 后缀
- 这种方式是零拷贝的，性能远高于序列化/反序列化

### 字符串处理
- 字符串通过 `ZString Ptr` 传递（以 null 结尾的 C 字符串）
- FreeBASIC 字符串与 C 字符串转换需注意编码
- 返回字符串时注意内存管理

### 编译缓存
- 缓存目录基于系统临时目录 + vools_freebasic_cache
- 命名：`<func_name>_<md5[:12]>.bas` 与 `<func_name>_<md5[:12]>.dll`
- 命中规则：相同源码 → 相同 md5 → 复用 DLL，不重新编译
- 强制重编：`mode='DEBUG'`

### Transport 扩展点
默认使用 ctypes 实现。如需注入自定义策略：

```python
from vools.bridge.freebasic import set_transport

# 自定义 transport 实现
class MyTransport:
    def prepare_arg(self, arg, fb_type): ...
    def prepare_ret(self, fb_type): ...
    def decode_result(self, value, fb_type): ...

set_transport(MyTransport())
```

### 运行模式

| mode | 行为 |
|------|------|
| `DEBUG` | 强制重编译 + 执行 |
| `FORCE` | 只强制重编译，不执行（返回 DLL 路径） |
| `NORMAL` | 命中缓存跳过编译；未命中则编译（默认） |
| `ONLY_RUN` | 缓存未命中抛异常 |
| `ONLY_CODE` | 只返回生成的 FreeBASIC 源码字符串，不编译 |

### FreeBASIC 语法特点
- 不区分大小写（`Function` 和 `function` 相同）
- 行尾不需要分号
- 注释使用 `'` 单引号
- 数组下标默认从 0 开始
- 字符串操作使用 `+` 连接

### 性能提示
- 首次调用需要编译 FreeBASIC 代码，后续调用使用缓存
- 数组使用免序列化传递，性能远高于序列化方式
- FreeBASIC 编译为原生机器码，性能接近 C
- 小函数调用开销主要来自 ctypes 边界

### 平台支持
- Windows 支持最好（官方主要平台）
- Linux 支持（需安装 freebasic 包）
- macOS 理论支持（可能需要自行编译）
- 自动检测平台并生成对应格式的共享库

### 相关资源
- [FreeBASIC 官方网站](https://www.freebasic.net/)
- [FreeBASIC 文档](https://www.freebasic.net/wiki/DocToc)
- [FreeBASIC 论坛](https://www.freebasic.net/forum/)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
