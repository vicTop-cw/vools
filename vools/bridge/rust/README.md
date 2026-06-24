# Rust 语言桥接模块

## 1. 语言简介

Rust 是一种注重安全、并发和性能的系统编程语言，具有内存安全保证和零成本抽象。`vools.bridge.rust` 模块提供了 Rust 语言的动态编译与跨语言桥接能力，支持：

- 动态编译 Rust 代码为共享库（DLL/SO/DYLIB）
- 通过 ctypes 加载并调用编译后的 Rust 函数
- 使用 `#[no_mangle]` 和 `extern "C"` 确保 C ABI 兼容
- 自动类型映射与参数转换
- 编译缓存机制，避免重复编译
- 装饰器模式快速定义 Rust 加速函数
- 支持多函数模块（`@rust_module`）
- Cargo 依赖管理支持

## 2. Bridge 类名

- **类名**: `RustBridge`
- **编译器类**: `RustCompiler`
- **装饰器**: `@rust` 或 `@rust_module`
- **类型映射器**: `RustTypeMapper`

## 3. 支持的功能

| 功能模式 | 支持状态 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ 支持 | 使用 `@rust` 装饰器快速定义 Rust 加速函数 |
| only_code 模式 | ✅ 支持 | `mode='ONLY_CODE'`，仅生成 Rust 代码，不编译 |
| project 模式 | ⚠️ 部分 | 可通过 `compile_rust_code` 手动编译，需自行管理项目 |
| 异步模式 | ✅ 支持 | `async_mode=True`，后台线程编译执行 |
| 回退机制 | ✅ 支持 | `fallback` 参数，编译失败时回退到 Python 实现 |
| 编译缓存 | ✅ 支持 | 基于代码内容哈希 + 函数签名哈希的缓存机制 |
| 多函数模块 | ✅ 支持 | `@rust_module` 装饰器创建包含多个函数的模块 |
| Cargo 依赖 | ✅ 支持 | `dependencies` 参数指定 Cargo 依赖包 |

## 4. 编译器要求

使用 Rust 语言桥接需要安装 Rust 工具链：

### Windows / Linux / macOS

使用 rustup 安装（官方推荐）：

```bash
# Unix-like 系统
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Windows
# 访问 https://rustup.rs/ 下载 rustup-init.exe 运行
```

### 验证安装
```bash
rustc --version
cargo --version
```

### Python 端验证
```python
from vools.bridge.rust import is_rust_available, get_compiler

if is_rust_available():
    compiler = get_compiler()
    print("Rust 编译器可用")
else:
    print("Rust 编译器不可用，请安装 Rust 工具链")
```

## 5. 类型映射表

| Python 类型 | Rust C ABI 类型 | ctypes 类型 | 说明 |
|------------|---------------|------------|------|
| `int` | `c_long` | `c_long` | C 长整数 |
| `float` | `c_double` | `c_double` | 双精度浮点数 |
| `bool` | `c_int` | `c_int` | 布尔值（0/1） |
| `str` | `*const c_char` | `c_char_p` | C 字符串指针（UTF-8） |
| `bytes` | `*const c_uchar` | `c_char_p` | 字节数组指针 |
| `None` | `void` | `None` | 无返回值 |

支持的其他 Rust C ABI 类型：
- 整数：`c_char`, `c_short`, `c_int`, `c_long`, `c_longlong`, 以及对应的无符号版本
- 浮点数：`c_float`, `c_double`
- 其他：`c_size_t`, `c_ssize_t`, 各种固定宽度整数（`c_int8` ~ `c_int64`）

## 6. 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.rust import rust

@rust
def add(a: int, b: int) -> int:
    """简单加法函数"""
    return "a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@rust
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return """
    if n <= 1 {
        1
    } else {
        fib(n - 1) + fib(n - 2)
    }
    """

result = fib(10)
print(result)  # 输出: 89
```

### 带回退机制

```python
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * x

@rust(fallback=python_fallback)
def square(x: int) -> int:
    return "x * x"

result = square(5)
print(result)  # 输出: 25
```

### 字符串处理

```python
@rust
def greet(name: str) -> str:
    return """
    use std::ffi::CString;
    use std::os::raw::c_char;
    
    let name_str = unsafe {
        std::ffi::CStr::from_ptr(name).to_string_lossy().into_owned()
    };
    let result = format!("Hello, {}!", name_str);
    CString::new(result).unwrap().into_raw()
    """

message = greet("World")
print(message)  # 输出: Hello, World!
```

### 异步模式

```python
import asyncio
from vools.bridge.rust import rust

@rust(async_mode=True)
async def heavy_compute(n: int) -> int:
    return """
    let mut result = 0;
    for i in 0..n {
        result += i;
    }
    result
    """

async def main():
    result = await heavy_compute(1000000)
    print(f"结果: {result}")

asyncio.run(main())
```

### 多函数模块

```python
from vools.bridge.rust import rust_module

@rust_module(name='math_ops')
class MathOps:
    """数学运算模块"""

    def add(a: int, b: int) -> int:
        return "a + b"

    def mul(a: int, b: int) -> int:
        return "a * b"

    def sub(a: int, b: int) -> int:
        return "a - b"

# 使用模块
ops = MathOps()
print(ops.add(10, 5))  # 输出: 15
print(ops.mul(10, 5))  # 输出: 50
print(ops.sub(10, 5))  # 输出: 5
```

## 7. only_code 模式示例

仅生成 Rust 代码，不编译执行：

```python
@rust(mode='ONLY_CODE')
def generate_code(a: int, b: int) -> int:
    return "a + b"

code = generate_code(1, 2)
print(code)
# 输出完整的 Rust 代码，包括 lib.rs 和 Cargo.toml
```

### 查看生成的代码

```python
from vools.bridge.rust import generate_from_python_func

# 从 Python 函数生成 Rust 代码
code = generate_from_python_func(add, auto_signature=True)
print(code)
```

### 使用 RustCodeGenerator

```python
from vools.bridge.rust import RustCodeGenerator

generator = RustCodeGenerator()
# 生成函数签名
sig = generator.generate_function_signature(
    name='add',
    params=[('a', 'c_long'), ('b', 'c_long')],
    ret_type='c_long'
)
print(sig)
```

## 8. project 模式示例

### 手动编译 Rust 代码

```python
from vools.bridge.rust import compile_rust_code, load_rust_dll, call_rust_function

# 手动编译 Rust 代码
dll_path = compile_rust_code(
    code='''
    #[no_mangle]
    pub extern "C" fn add(a: c_long, b: c_long) -> c_long {
        a + b
    }
    ''',
    func_name='add',
    package_name='my_math',
    force=False
)

# 加载并执行
result = call_rust_function(dll_path, 'add', [5, 3], ret_type=int)
print(result)  # 输出: 8
```

### 使用 CDLL 直接调用

```python
from vools.bridge.rust import load_rust_dll
import ctypes

dll = load_rust_dll(dll_path)
func = dll.add
func.argtypes = [ctypes.c_long, ctypes.c_long]
func.restype = ctypes.c_long

result = func(10, 20)
print(result)  # 输出: 30
```

### Cargo 项目依赖

```python
@rust(dependencies={'serde': '1.0', 'serde_json': '1.0'})
def parse_json(json_str: str) -> int:
    return """
    // 需要 serde 和 serde_json 依赖
    // ... 复杂的 JSON 解析逻辑
    42
    """
```

## 9. 注意事项

### 函数签名
- Rust 导出函数必须使用 `#[no_mangle]` 和 `pub extern "C"` 标记
- 使用 C ABI 类型（`c_long`、`c_double`、`c_char` 等）确保跨语言兼容
- 自动签名生成模式下会自动处理这些细节

### 字符串处理
- 字符串通过 `*const c_char` 传递（UTF-8 编码）
- Rust 端使用 `CStr::from_ptr()` 将 C 字符串转换为 Rust 字符串
- 返回字符串时使用 `CString::new().unwrap().into_raw()` 分配内存
- ⚠️ 注意：返回的 CString 需要手动释放，否则会内存泄漏

### Cargo 项目结构
- 每次编译会创建临时 Cargo 项目
- 项目包含 `Cargo.toml` 和 `src/lib.rs`
- 可通过 `dependencies` 参数添加 Cargo 依赖
- 编译缓存基于代码内容哈希

### 编译缓存
- 缓存目录默认为 `__rust__/cache/`
- 缓存键由代码内容哈希 + 函数签名哈希组成
- 超过 100 个缓存文件时自动清理最旧的
- 首次编译约需 1-5 秒，后续调用使用缓存性能接近原生

### 异步模式
- `async_mode=True` 时在后台线程编译和执行
- 使用 `ThreadPoolExecutor`（默认 4 个工作线程）
- 适合 UI 应用或需要保持响应的场景
- 支持与 asyncio 其他异步操作配合使用

### 内存安全
- Rust 本身具有内存安全保证，但跨 C ABI 边界时需注意
- 不要在 Python 侧释放 Rust 分配的内存
- 传递数组时需确保长度参数正确
- 建议在 Python 侧做好参数校验

### 性能提示
- 首次调用需要编译（约 1-5 秒），后续调用使用缓存
- 小函数调用开销主要来自 ctypes 边界
- 计算密集型任务使用 Rust 收益显著
- 简单计算建议直接使用 Python，避免调用开销

### 平台支持
- Windows、Linux、macOS 全平台支持
- 使用 rustup 安装的工具链均可正常工作
- 自动检测平台并生成对应格式的共享库

### 相关资源
- [Rust 官方文档](https://doc.rust-lang.org/)
- [Rust 标准库](https://doc.rust-lang.org/std/)
- [The Rustonomicon - 不安全代码指南](https://doc.rust-lang.org/nomicon/)
- [PyO3 - Rust Python 绑定](https://pyo3.rs/)
- [Python ctypes 文档](https://docs.python.org/3/library/ctypes.html)
