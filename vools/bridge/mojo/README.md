# Mojo 语言桥接模块

## 1. 语言简介

Mojo 是由 Modular 公司开发的一种新编程语言，结合了 Python 的易用性和 C/C++ 的性能，专为 AI 和高性能计算设计。`vools.bridge.mojo` 模块提供了 Mojo 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 Mojo 代码为共享库（SO/DYLIB）
- 通过 ctypes 实现免序列化跨语言交互
- 列表/数组参数通过 `UnsafePointer[T] + 长度` 传递，零拷贝
- 字符串参数通过 `UnsafePointer[c_char]` 传递（UTF-8）
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 Mojo 加速函数
- Transport 抽象层，可注入自定义序列化策略（如 zinc zero-copy）

## 2. Bridge 类名

- **类名**: `MojoBridge`
- **全局实例**: `_mojo_bridge`
- **装饰器**: `@mojo` 或 `@mojo_bridge.decorator`
- **异步 Future**: `MojoFuture`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@mojo` 装饰器快速定义 Mojo 加速函数 |
| only_code 模式 | ✅ 支持 | `mode='ONLY_CODE'`，仅生成 Mojo 代码，不编译 |
| project 模式 | ⚠️ 部分 | 可通过 `mojo build` 手动编译整个项目 |
| 异步模式 | ✅ 支持 | `async_mode=True`，返回 `MojoFuture`，可 await |
| 回退机制 | ✅ 支持 | 编译失败时可通过 fallback 回退 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |
| 免序列化数组 | ✅ 支持 | list 参数通过指针 + 长度传递，零拷贝 |
| Transport 抽象 | ✅ 支持 | 可注入自定义传输层（如 Zinc zero-copy） |
| 预编译库加载 | ✅ 支持 | `get_mojo_lib()` 加载预编译的 .so 库 |

## 4. 编译器要求

使用 Mojo 语言桥接需要安装 Mojo 工具链：

### 运行环境
- **WSL Linux**（主测平台，Modular Mojo 官方支持）
- **原生 Linux**（理论支持）
- **macOS**（理论支持）
- **Windows 原生不支持**（Mojo 1.0b1 仅支持 Linux/macOS）

### 安装 Mojo

```bash
# Modular 官方安装脚本
curl -s https://get.modular.com | sh -
modular install mojo

# 验证安装
mojo --version
# 期望输出：mojo 1.0b1 ... 之类
```

### 验证安装
```python
from vools.bridge.mojo import mojo_compiler_available, is_mojo_available

if mojo_compiler_available():
    print("Mojo 编译器可用")
else:
    print("Mojo 编译器不可用，请在 WSL/Linux/macOS 中安装 Mojo 工具链")

if is_mojo_available():
    print("Mojo 桥接可用（编译器或预编译库）")
```

> ⚠️ **注意**：在 Windows 主机的 Python 中直接 `from vools.bridge.mojo import mojo` 也能 import（API 都已实现），但任何编译/调用尝试都会失败，因为 Mojo 工具链不在 Windows PATH，且编译产物 `.so` 是 Linux ABI，Windows ctypes 加载不了。

## 5. 类型映射表

| Python 类型 | Mojo 类型 | ctypes 类型 | 说明 |
|------------|----------|------------|------|
| `int` | `Int64` | `c_longlong` | 64 位有符号整数 |
| `float` | `Float64` | `c_double` | 双精度浮点数 |
| `bool` | `Bool` | `c_int` | 布尔值（0/1） |
| `str` / `bytes` | `UnsafePointer[c_char]` | `c_char_p` | UTF-8 字符串，自动编码/解码 |
| `list[int]` | `UnsafePointer[Int64]` + `n: Int64` | `POINTER(c_longlong)` + `c_longlong` | 整数数组指针 + 长度 |
| `list[float]` | `UnsafePointer[Float64]` + `n: Int64` | `POINTER(c_double)` + `c_longlong` | 浮点数数组指针 + 长度 |
| `dict` / `tuple` | `OpaquePointer` | `c_void_p` | 不透明指针 |
| `None` | `None` | `restype = None` | 无返回值 |

> **注意**：`list` 类型的参数会自动展开为 `(指针, 长度)` 两个参数。例如 `arr: list` 在 Mojo 端会变成 `arr: UnsafePointer[Int64], n: Int64`。

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.mojo import mojo

@mojo
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "return a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@mojo
def fib(n: int) -> int:
    return """
    if n <= 1:
        return 1
    return fib(n-1) + fib(n-2)
    """

result = fib(10)
print(result)  # 输出: 55
```

### 数组求和（免序列化）

```python
@mojo
def sum_arr(arr: list) -> int:
    """
    数组求和（零拷贝）
    
    list 参数自动展开为 (ptr, n) 两个参数：
    - arr: UnsafePointer[Int64]（数组指针）
    - n: Int64（数组长度，由参数名 + '_n' 后缀自动生成）
    """
    return """
    var total = 0
    for i in range(n):
        total += arr[i]
    return total
    """

print(sum_arr([1, 2, 3, 4, 5]))  # 输出: 15
```

### 字符串处理

```python
@mojo
def greet(name: str) -> str:
    return """
    // 字符串处理示例
    // name 是 UnsafePointer[c_char] 类型
    // 实际使用时需要转换为 Mojo String
    return name
    """

message = greet("World")
print(message)
```

### 异步模式

```python
import asyncio
from vools.bridge.mojo import mojo

@mojo(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    var total = 0
    for i in range(n):
        total += i
    return total
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

### 并发调用

```python
import asyncio
from vools.bridge.mojo import mojo

@mojo(async_mode=True)
async def compute(x: int) -> int:
    return "return x * x"

async def parallel():
    # 并发调用 10 次
    tasks = [compute(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    print(results)

asyncio.run(parallel())
```

## 7. only_code 模式示例

仅生成 Mojo 代码，不编译执行：

```python
@mojo(mode='ONLY_CODE')
def generate_code(a: int, b: int) -> int:
    return "return a + b"

code = generate_code(1, 2)
print(code)
# 输出完整的 Mojo 源码，包括 @export 装饰器和 C ABI 声明
```

### 使用 LangBridge 的 only_code 模式

```python
from vools.bridge.mojo import MojoBridge

mojo_bridge = MojoBridge()

@mojo_bridge.decorator(only_code=True)
def add(a: int, b: int) -> int:
    return "return a + b"

code = add(1, 2)
print(code)
```

### 输出到文件

```python
@mojo_bridge.decorator(only_code=True, output_file='./output/add.mojo')
def add(a: int, b: int) -> int:
    return "return a + b"

file_path = add(1, 2)
print(f"代码已写入: {file_path}")
```

### 查看生成的函数签名

```python
from vools.bridge.mojo import generate_function_signature

sig = generate_function_signature(
    name='add',
    params=[('a', 'Int64'), ('b', 'Int64')],
    ret_type='Int64'
)
print(sig)
```

## 8. project 模式示例

### 预编译 .so 库加载

如果已用 `mojo build` 自行编译了 .so：

```bash
# WSL/Linux 内
mojo build -o libmy_mojo.so my_mojo.mojo
```

Python 端加载：

```python
from vools.bridge.mojo import get_mojo_lib
import ctypes

lib = get_mojo_lib('my_mojo')   # 实际查找 libmy_mojo.so
if lib is not None:
    fn = lib.my_function
    fn.argtypes = [ctypes.c_longlong, ctypes.c_longlong]
    fn.restype = ctypes.c_longlong
    result = fn(10, 20)
    print(result)
```

### 手动编译项目

```python
import subprocess
import os

# 手动调用 mojo build
project_dir = './my_mojo_project'
output_path = './output/libmy_project.so'

result = subprocess.run(
    ['mojo', 'build', '-o', output_path, 'main.mojo'],
    cwd=project_dir,
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print(f"编译成功: {output_path}")
else:
    print(f"编译失败: {result.stderr}")
```

### 加载预编译库并调用

```python
from vools.bridge.mojo import get_mojo_lib
from vools.bridge.core.types import CTypeMapper

# 加载库
lib = get_mojo_lib('my_math_lib')

if lib:
    # 设置函数签名
    add_func = lib.add
    add_func.argtypes = [CTypeMapper.get_ctype(int), CTypeMapper.get_ctype(int)]
    add_func.restype = CTypeMapper.get_ctype(int)
    
    # 调用函数
    result = add_func(10, 20)
    print(f"结果: {result}")
```

## 9. 注意事项

### 运行环境
- **WSL Linux 是主测平台**，原生 Linux 和 macOS 理论支持
- Windows 原生不支持 Mojo，请勿在 Windows Python 中尝试编译和调用
- WSL 与 Windows 主机混用不支持（需要 WSL 路径映射 + Linux Python ABI）

### @export 装饰器
- 所有导出函数自动使用 `@export("函数名")` 装饰器标记
- 函数签名中使用 `abi("C")` 指定 C 调用约定
- 使用 `UnsafePointer[T]` 类型处理数组和字符串指针

### 数组传递（免序列化）
- `list` 类型的参数会自动展开为 `(指针, 长度)` 两个参数
- 例如 `arr: list` → `arr: UnsafePointer[Int64], n: Int64`
- 长度参数名规则：原参数名 + `_n` 后缀
- 这种方式是零拷贝的，性能远高于序列化/反序列化

### 字符串处理
- `str` 类型以 UTF-8 编码传递为 `UnsafePointer[c_char]`
- Mojo 端可以通过 `String` 构造函数转换为 Mojo 字符串
- 返回字符串时注意内存管理，避免返回局部变量指针

### 编译缓存
- 缓存目录：`$TMPDIR/vools_mojo_cache/`（Linux 下通常是 `/tmp/vools_mojo_cache/`）
- 命名：`<func_name>_<md5[:12]>.mojo` 与 `lib<func_name>_<md5[:12]>.so`
- 命中规则：相同 Mojo 源码 → 相同 md5 → 复用 .so，不重新编译
- 强制重编：`mode='DEBUG'`

### Transport 扩展点
默认 `CtypesTransport` 是纯 ctypes 零依赖实现。如需注入自定义策略：

```python
from vools.bridge.mojo import set_transport, Transport

class MyTransport(Transport):
    def prepare_arg(self, arg, mojo_type): ...
    def prepare_ret(self, mojo_type): ...
    def decode_result(self, value, mojo_type): ...

set_transport(MyTransport())
```

未来可基于 `zinc`（Rust 编译的 zero-copy Python 库）或 Modular 官方的 "Mojo from Python" 路径实现 `ZincTransport` / `MojoFromPythonTransport` 注入。

### 运行模式

| mode | 行为 |
|------|------|
| `DEBUG` | 强制重编译 + 执行 |
| `FORCE` | 只强制重编译，不执行（返回 .so 路径） |
| `NORMAL` | 命中缓存跳过编译；未命中则编译（默认） |
| `ONLY_RUN` | 缓存未命中抛 `FileNotFoundError` |
| `ONLY_CODE` | 只返回生成的 Mojo 源码字符串，不编译 |

### 已知限制
- **Mojo 1.0b1 字符串 ABI**：某些 beta 小版本对 `String` 跨 cdecl 边界的行为可能调整。`str` 类型测试标记为 `xfail`，待正式版稳定后移除。
- **Mojo 1.0b1 编译 .so 命令**：`docs.modular.com` 未明确列出 `--emit shared` 等选项；本桥接通过候选命令探测（`build` / `build --emit shared` / `build -shared` / `build --shared`）按优先级自动尝试。请在 WSL 内执行一次 `@mojo` 函数以确认实际可用的命令。
- **Windows 原生不支持**：见"运行环境"。

### 性能提示
- 首次调用需要编译 Mojo 代码，后续调用使用缓存性能接近原生
- 数组使用免序列化传递，性能远高于 JSON/CSV 等序列化方式
- Mojo 具有类似 C/C++ 的性能，适合计算密集型任务
- 小函数调用开销主要来自 ctypes 边界

### 相关资源
- [Mojo 官方文档](https://docs.modular.com/mojo/)
- [@export 装饰器](https://docs.modular.com/mojo/manual/decorators/export)
- [Modular 官网](https://www.modular.com/)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
