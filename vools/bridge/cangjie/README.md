# 仓颉语言桥接模块

## 1. 语言简介

仓颉是华为发布的一款面向全场景的自研编程语言，融合了多种现代语言特性，注重安全性、性能和开发效率。`vools.bridge.cangjie` 模块提供了仓颉语言的动态编译与跨语言桥接能力，支持：

- 动态编译仓颉代码为共享库（DLL/SO/DYLIB）
- 通过 ctypes 直接调用 C ABI 兼容的仓颉函数
- 免序列化（serialization-free）跨语言交互
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义仓颉加速函数
- 异步执行支持
- 批量编译与执行

## 2. Bridge 类名

- **编译器主装饰器**: `@cangjie`
- **代码生成器**: `CangjieCodeGenerator`
- **异步 Future**: `CjFuture`
- **类型映射**: `PY_TO_CJ_TYPE` / `CJ_TO_CTYPES`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@cangjie` 装饰器快速定义仓颉加速函数 |
| only_code 模式 | ✅ 支持 | 可通过 `CangjieCodeGenerator` 生成代码 |
| project 模式 | ⚠️ 部分 | 可通过 cjc 手动编译整个项目 |
| 异步模式 | ✅ 支持 | `async_mode=True`，返回 `CjFuture`，可 await |
| 回退机制 | ✅ 支持 | fallback 参数，编译失败时回退 |
| 编译缓存 | ✅ 支持 | 基于代码 MD5 哈希的缓存机制 |
| 批量编译 | ✅ 支持 | `batch_compile_and_run_async` 批量执行 |
| 预编译库加载 | ✅ 支持 | `get_cj_lib()` 加载预编译库 |

## 4. 编译器要求

使用仓颉语言桥接需要安装仓颉 SDK：

### 安装仓颉 SDK

从 [仓颉语言官网](https://cangjie-lang.cn/) 下载并安装仓颉 SDK：

```bash
# 下载仓颉 SDK 并安装
# https://cangjie-lang.cn/
# 将 cjc 编译器添加到系统 PATH
```

### 验证安装
```bash
cjc --version
```

### Python 端验证
```python
from vools.bridge.cangjie import cjc_compiler_available, is_cj_available

if cjc_compiler_available():
    print("仓颉编译器可用")
else:
    print("仓颉编译器不可用，请安装仓颉 SDK 并将 cjc 添加到 PATH")

if is_cj_available():
    print("仓颉桥接可用（编译器或预编译库）")
```

## 5. 类型映射表

| Python 类型 | 仓颉类型 | ctypes 类型 | 说明 |
|------------|---------|------------|------|
| `int` | `Int64` | `c_longlong` | 64 位有符号整数 |
| `float` | `Float64` | `c_double` | 双精度浮点数 |
| `bool` | `Bool` | `c_bool` | 布尔值 |
| `str` | `String` | `c_char_p` | 字符串（UTF-8） |
| `bytes` | `Array<Byte>` | `c_char_p` | 字节数组 |
| `list` | `Array<T>` | 指针 + 长度 | 泛型数组 |
| `dict` | `Map<K, V>` | - | 字典（需特殊处理） |
| `tuple` | `Tuple` | - | 元组（需特殊处理） |
| `None` | `Unit` | `None` | 无返回值 |

支持的其他仓颉整数类型：
- 有符号：`Int8`, `Int16`, `Int32`, `Int64`
- 无符号：`UInt8`, `UInt16`, `UInt32`, `UInt64`
- 浮点数：`Float32`, `Float64`

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.cangjie import cangjie

@cangjie
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "return a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@cangjie
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return """
    if n <= 1 {
        return 1
    } else {
        return fib(n - 1) + fib(n - 2)
    }
    """

result = fib(10)
print(result)  # 输出: 89
```

### 字符串处理

```python
@cangjie
def greet(name: str) -> str:
    return """
    // 字符串处理示例
    return "Hello, " + name + "!"
    """

message = greet("World")
print(message)  # 输出: Hello, World!
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * x

@cangjie(fallback=python_fallback)
def square(x: int) -> int:
    return "return x * x"

result = square(5)
print(result)  # 输出: 25
```

### 异步模式

```python
import asyncio
from vools.bridge.cangjie import cangjie

@cangjie(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    var total: Int64 = 0
    for i in 0..n {
        total += i
    }
    return total
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

### 批量异步执行

```python
import asyncio
from vools.bridge.cangjie import batch_compile_and_run_async

async def batch_example():
    # 批量编译和执行多个函数
    tasks = [
        ("return x * x", [i])
        for i in range(10)
    ]
    results = await batch_compile_and_run_async(tasks, ret_type=int)
    print(results)

asyncio.run(batch_example())
```

## 7. only_code 模式示例

仅生成仓颉代码，不编译执行：

```python
from vools.bridge.cangjie import generate_from_python_func

def add(a: int, b: int) -> int:
    return "return a + b"

# 从 Python 函数生成仓颉代码
code = generate_from_python_func(add, auto_signature=True)
print(code)
# 输出完整的仓颉源码，包括函数声明和导出标记
```

### 使用 CangjieCodeGenerator

```python
from vools.bridge.cangjie import CangjieCodeGenerator

generator = CangjieCodeGenerator()

# 生成函数签名
sig = generator.generate_function_signature(
    name='add',
    params=[('a', 'Int64'), ('b', 'Int64')],
    ret_type='Int64'
)
print(sig)
```

### 生成完整代码

```python
from vools.bridge.cangjie import generate_cj_code

code = generate_cj_code(
    func_name='add',
    params=[('a', 'Int64'), ('b', 'Int64')],
    ret_type='Int64',
    body='return a + b'
)
print(code)
```

## 8. project 模式示例

### 手动编译仓颉代码

```python
import subprocess

# 手动调用 cjc 编译
source_file = 'my_program.cj'
output_dll = 'my_program.dll'

result = subprocess.run(
    ['cjc', source_file, '-o', output_dll, '--shared'],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print(f"编译成功: {output_dll}")
else:
    print(f"编译失败: {result.stderr}")
```

### 加载预编译库并调用

```python
from vools.bridge.cangjie import get_cj_lib, call_cj_func

# 加载预编译的仓颉库
lib = get_cj_lib('my_cj_lib')

if lib:
    # 调用函数
    result = call_cj_func(lib, 'add', [5, 3], ret_type=int)
    print(result)  # 输出: 8
```

### 使用 loader 直接调用

```python
from vools.bridge.cangjie import load_cj_dll, setup_cj_func, convert_args, convert_result
import ctypes

# 加载 DLL
dll = load_cj_dll('./my_program.dll')

# 设置函数签名
func = setup_cj_func(dll, 'add', [ctypes.c_longlong, ctypes.c_longlong], ctypes.c_longlong)

# 准备参数
args = convert_args([10, 20], ['Int64', 'Int64'])

# 调用
result = func(*args)

# 转换结果
final_result = convert_result(result, 'Int64')
print(final_result)  # 输出: 30
```

## 9. 注意事项

### 函数签名
- 仓颉导出函数使用 C ABI 兼容格式
- 自动签名生成模式下会自动处理导出标记
- 类型映射基于仓颉官方文档和 FFI 规范

### 字符串处理
- 字符串通过 UTF-8 编码传递
- 仓颉 `String` 类型与 Python `str` 自动转换
- 返回字符串时注意内存管理

### 数组和集合
- 数组使用 `Array<T>` 泛型类型
- 字典使用 `Map<K, V>` 泛型类型
- 复杂集合类型可能需要特殊处理

### 编译缓存
- 缓存目录：`_CJ_CACHE_DIR`
- 基于代码内容哈希的缓存机制
- 避免重复编译相同代码

### 异步模式
- `async_mode=True` 时在后台线程编译和执行
- 返回 `CjFuture` 对象，可 await
- 支持批量异步执行 `batch_compile_and_run_async`
- 使用全局线程池 `_executor`

### 仓颉语法特点
- 使用花括号 `{}` 定义代码块
- 使用 `fn` 或 `func` 定义函数（具体以官方为准）
- 变量声明使用 `var` 或 `let`
- 类型注解使用 `: 类型` 语法
- 具体语法请参考仓颉官方文档

### 性能提示
- 首次调用需要编译仓颉代码，后续调用使用缓存
- 仓颉编译为原生机器码，性能接近 C/C++
- 计算密集型任务使用仓颉收益显著
- 小函数调用开销主要来自 ctypes 边界

### 平台支持
- 支持仓颉 SDK 支持的所有平台
- 具体平台兼容性请参考仓颉官方文档
- 自动检测平台并生成对应格式的共享库

### 相关资源
- [仓颉语言官网](https://cangjie-lang.cn/)
- [仓颉语言文档](https://cangjie-lang.cn/doc/)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
