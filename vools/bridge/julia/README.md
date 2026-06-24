# vools.bridge.julia — Julia 语言桥接

> 高性能动态科学计算语言桥接，支持 subprocess 调用和 ctypes 共享库加载

## 语言简介

Julia 是一种高性能动态编程语言，专为科学计算和数值分析设计。它结合了 C 的速度和 Python 的易用性，支持多重分派、元编程和并行计算。

本模块提供 Julia 动态编译和跨语言桥接能力，采用装饰器模式，函数返回 Julia 代码字符串，装饰器自动调用 Julia 执行并返回结果。支持通过 subprocess 直接执行，以及通过 StaticCompiler 编译为共享库后使用 ctypes 加载。

## Bridge 类名

**`JuliaBridge`** — 继承自 `LangBridge` 抽象基类的 Julia 桥接实现

## 支持的功能

| 功能模式 | 支持情况 | 说明 |
|---------|---------|------|
| 装饰器模式 | ✅ | `@julia` 装饰器，函数体返回 Julia 代码字符串 |
| only_code 模式 | ✅ | 只生成 Julia 源码，不编译/执行 |
| project 模式 | ✅ | 支持项目级编译和执行 |
| 缓存机制 | ✅ | 基于代码 MD5 哈希的缓存 |
| 异步模式 | ✅ | `async_mode=True` 支持异步执行 |
| 回退机制 | ❌ | 暂不支持 |

## 运行环境要求

- **Julia 版本**：>= 1.6
- **安装方式**：
  - Windows：从 [Julia 官网](https://julialang.org/downloads/) 下载安装
  - macOS：`brew install julia`
  - Linux：从官网下载或使用包管理器
- **PATH 配置**：确保 `julia` 命令在系统 PATH 中
- **常用安装路径自动搜索**：
  - Windows: `C:\Users\<user>\AppData\Local\Programs\Julia-1.11.0\bin`, `C:\Program Files\Julia-1.11.0\bin`
  - Unix: `/home/julia/bin`, `/root/.juliaup/bin`, `/usr/local/julia/bin`, `/opt/julia/bin`
- **WSL 支持**：Windows 上可通过 WSL 调用 Julia
- **可选依赖**：
  - StaticCompiler.jl（用于编译为共享库）
  - GCC 编译器（用于 C 包装层编译）

验证安装：
```bash
julia --version
```

## 类型映射表

| Python 类型 | Julia 类型 | ctypes 类型 | 说明 |
|------------|-----------|------------|------|
| `int` | `Int64` | `c_int64` | 64 位整数 |
| `float` | `Float64` | `c_double` | 64 位浮点数 |
| `bool` | `Bool` | `c_bool` | 布尔值 |
| `str` | `Cstring` / `String` | `c_char_p` | UTF-8 字符串 |
| `bytes` | `Vector{UInt8}` | `c_void_p` | 字节数组 |
| `list[int]` | `Ptr{Cvoid}` + 长度 | `c_void_p` + `c_int64` | 整型数组指针 |
| `list[float]` | `Ptr{Cvoid}` + 长度 | `c_void_p` + `c_int64` | 浮点数组指针 |
| `list` | `Vector{Any}` | `c_void_p` | 泛型数组 |
| `tuple` | `Tuple` | `c_void_p` | 元组 |
| `dict` | - | - | 需序列化传递 |
| `None` | `Nothing` | `None` | 空值/无返回值 |

### 完整的 Julia 数值类型支持

| Julia 类型 | 说明 | ctypes 类型 |
|-----------|------|------------|
| `Int8` | 8 位有符号整数 | `c_int8` |
| `Int16` | 16 位有符号整数 | `c_int16` |
| `Int32` | 32 位有符号整数 | `c_int32` |
| `Int64` | 64 位有符号整数 | `c_int64` |
| `UInt8` | 8 位无符号整数 | `c_uint8` |
| `UInt16` | 16 位无符号整数 | `c_uint16` |
| `UInt32` | 32 位无符号整数 | `c_uint32` |
| `UInt64` | 64 位无符号整数 | `c_uint64` |
| `Float32` | 32 位浮点数 | `c_float` |
| `Float64` | 64 位浮点数 | `c_double` |
| `Bool` | 布尔值 | `c_bool` |
| `Cstring` | C 风格字符串 | `c_char_p` |
| `Ptr{Cvoid}` | 空指针 | `c_void_p` |

## 快速使用示例（装饰器模式）

### 基本使用

```python
from vools.bridge.julia import julia, julia_compiler_available

if not julia_compiler_available():
    raise RuntimeError('请先安装 Julia 并加入 PATH')

@julia
def add(a: int, b: int) -> int:
    """简单的加法函数"""
    return "return a + b"

result = add(3, 5)
print(result)  # 输出: 8
```

### 斐波那契数列

```python
@julia
def fib(n: int) -> int:
    """斐波那契数列计算"""
    return '''
    if n <= 1
        return 1
    end
    return fib(n - 1) + fib(n - 2)
    '''

result = fib(10)
print(result)  # 输出: 89
```

### 字符串处理

```python
@julia
def greet(name: str) -> str:
    """字符串拼接"""
    return 'return "Hello, " * name * "!"'

result = greet("World")
print(result)  # 输出: Hello, World!
```

### 数组求和

```python
@julia
def sum_array(arr: list) -> int:
    """数组求和（注意：subprocess 模式下数组通过 JSON 传递）"""
    return '''
    return sum(arr)
    '''

result = sum_array([1, 2, 3, 4, 5])
print(result)  # 输出: 15
```

### 异步模式

```python
import asyncio
from vools.bridge.julia import julia

@julia(async_mode=True)
async def heavy_compute(n: int) -> int:
    """异步执行计算密集型任务"""
    return '''
    if n <= 1
        return 1
    end
    return heavy_compute(n - 1) + heavy_compute(n - 2)
    '''

async def main():
    result = await heavy_compute(30)
    print(f"Result: {result}")

asyncio.run(main())
```

## only_code 模式示例

使用 `mode='ONLY_CODE'` 只生成 Julia 源码，不编译或执行：

```python
@julia(mode='ONLY_CODE')
def generate_add(a: int, b: int) -> int:
    return "return a + b"

code = generate_add(1, 2)
print(code)
# 输出:
# function generate_add(a::Int64, b::Int64)::Int64
#     return a + b
# end
```

### 其他运行模式

| 模式 | 说明 |
|-----|------|
| `DEBUG` | 强制重新编译并执行 |
| `FORCE` | 只强制编译，不执行 |
| `NORMAL` | 命中缓存跳过编译；未命中则编译（默认） |
| `ONLY_RUN` | 只在有缓存时执行；没有则报错 |
| `ONLY_CODE` | 只生成 Julia 源码，不编译 |

## project 模式示例

### 项目结构

```
my_julia_project/
├── math_utils.jl
└── main.jl
```

### math_utils.jl

```julia
function add(a::Int64, b::Int64)::Int64
    return a + b
end

function multiply(a::Int64, b::Int64)::Int64
    return a * b
end
```

### main.jl

```julia
include("math_utils.jl")

function main()
    println(add(3, 5))
    println(multiply(3, 5))
end

main()
```

### 使用 project 模式

```python
from vools.bridge.julia import JuliaBridge

bridge = JuliaBridge()

# 编译项目
project_dir = "./my_julia_project"
artifact_path = bridge.compile_project(
    project_dir=project_dir,
    entry='main',
    output_dir="./output"
)

# entry='main' 模式：执行主脚本
returncode, stdout, stderr = bridge._run_executable(artifact_path, args=())
print("退出码:", returncode)
print("输出:", stdout)

# entry!='main' 模式：调用入口函数
result = bridge.call_func(
    lib_path=artifact_path,
    func_name='add',
    args=(3, 5),
    ret_type=int
)
print("结果:", result)  # 输出: 8
```

### 使用 LangBridge 统一接口

```python
from vools.bridge.julia import JuliaBridge

bridge = JuliaBridge()

# 生成代码
from vools.bridge._base import FunctionSpec

spec = FunctionSpec(
    name='add',
    annotations={'a': int, 'b': int, 'return': int},
    args=(),
    defaults={},
    body='return a + b'
)

code = bridge.generate_code(spec)
print(code)

# 编译代码
lib_path = bridge.compile_code(code, 'add')

# 调用函数
result = bridge.call_func(lib_path, 'add', (3, 5), int)
print(result)  # 输出: 8
```

## 注意事项

### 解释型语言的调用方式

1. **subprocess 调用**：默认通过 `subprocess` 调用 `julia` 命令执行脚本
2. **StaticCompiler**：尝试使用 StaticCompiler.jl 编译为共享库，失败则回退到 subprocess
3. **WSL 支持**：Windows 上如未安装本地 Julia，会尝试通过 WSL 调用
4. **性能考虑**：subprocess 模式每次调用都会启动新的 Julia 进程，首次调用 JIT 编译较慢
5. **JIT 编译**：Julia 是 JIT 编译语言，首次执行函数会有编译开销

### 特殊语法

1. **函数定义**：Julia 使用 `function` 关键字或简写形式 `f(x) = x^2`
2. **返回值**：函数默认返回最后一个表达式的值，也可使用 `return`
3. **类型注解**：使用 `::` 语法，如 `x::Int64`，返回类型注解在参数列表后
4. **数组索引**：Julia 数组索引从 1 开始，不是 0
5. **字符串拼接**：使用 `*` 运算符，不是 `+`
6. **多重分派**：Julia 支持基于所有参数类型的函数重载
7. **模块系统**：使用 `module` 和 `using` / `import`

### 数组参数处理

1. **标量模式**：subprocess 调用时，简单类型直接作为命令行参数传递
2. **数组模式**：ctypes 模式下，数组参数被拆分为（指针，长度）两个参数
3. **内存管理**：ctypes 模式下数组内存由 Python 管理，Julia 端只读访问
4. **类型推断**：根据数组第一个元素的类型推断元素类型

### 缓存机制

1. 缓存目录：`$TMPDIR/vools_julia_cache/`
2. 缓存键：基于源码 MD5 哈希的前 12 位
3. 缓存内容：编译后的共享库文件（.so / .dll / .dylib）
4. 强制重编：使用 `mode='DEBUG'` 或 `mode='FORCE'`

### 共享库加载

1. **Windows DLL 搜索路径**：自动将 DLL 所在目录加入 DLL 搜索路径
2. **Julia 运行时依赖**：共享库依赖 Julia 运行时，确保 Julia bin 目录在 PATH 中
3. **平台差异**：
   - Windows: `.dll`
   - Linux: `.so`
   - macOS: `.dylib`

### 错误处理

1. Julia 执行失败时会抛出 `RuntimeError`，包含 stderr 和 stdout 信息
2. 建议使用 `julia_compiler_available()` 先检查 Julia 环境是否可用
3. 仅代码模式（ONLY_CODE）不会检查 Julia 可用性
4. StaticCompiler 编译失败会自动回退到 subprocess 模式

## API 速查

```python
from vools.bridge.julia import (
    # 装饰器
    julia,                      # @julia 装饰器
    JuliaFuture,                # 异步执行 Future
    
    # 编译器
    julia_compiler_available,   # 检查 Julia 编译器是否可用
    is_julia_available,         # 检查 Julia 桥接是否可用
    compile_and_run,            # 直接编译并执行 Julia 源码
    JuliaCompiler,              # Julia 编译器类
    compile_julia_code,         # 编译 Julia 代码为共享库
    get_compiler,               # 获取编译器实例
    
    # 类型映射
    JuliaTypeMapper,            # Julia 类型映射器类
    get_julia_type,             # 获取 Julia 类型字符串
    get_ctypes_type,            # 获取 ctypes 类型
    infer_julia_argtypes,       # 根据值推断 Julia 类型列表
    infer_ctypes_types,         # 根据值推断 ctypes 类型列表
    infer_ret_type,             # 推断返回类型
    convert_args,               # 转换参数为 ctypes 格式
    is_array_type,              # 判断是否为数组类型
    
    # 代码生成
    generate_julia_function,    # 生成 Julia 函数
    generate_julia_c_wrapper,   # 生成 C 包装函数
    generate_compile_script,    # 生成编译脚本
    
    # 加载器
    load_julia_dll,             # 加载 Julia 共享库
    call_julia_function,        # 调用 Julia 函数
    is_julia_dll_available,     # 检查共享库函数是否可用
    
    # LangBridge 实现
    JuliaBridge,                # Julia 桥接实现类
    julia_bridge,               # 全局 JuliaBridge 实例
)
```
