# Julia 桥接实现计划

## 摘要
在 vools 项目中实现 Julia 语言桥接模块，参考 `fbc.py` (FreeBASIC) 和 `go.py` 的装饰器模式，使 Python 能动态调用 Julia 代码。

## 当前状态分析

### 1. Julia 安装情况
- **本地 (Windows)**: 未安装
- **WSL**: 未安装
- **决定**: 使用 WSL 安装 Julia（Linux 环境下 Julia 对共享库支持更好）

### 2. 现有框架结构
```
vools/bridge/
├── __init__.py          # 统一导出入口，延迟加载各语言模块
├── manager.py           # BridgeManager 统一管理器
├── go.py                # Go 桥接（单文件，参考实现）
├── rust/                # Rust 桥接（多文件模块）
├── c/, nim/, cangjie/   # 其他语言桥接
└── core/                # 核心类型和工具
```

### 3. 参考实现分析 (go.py)
- 单文件装饰器模式 `@go`
- 支持模式: DEBUG, FORCE, NORMAL, ONLY_RUN, ONLY_CODE
- Python → Go 类型映射 (int → C.longlong, str → *C.char 等)
- 通过 `go build -buildmode=c-shared` 编译为共享库
- ctypes 加载和调用

## Julia 桥接设计方案

### 目录结构
```
vools/bridge/julia/
├── __init__.py         # 模块入口，导出公开 API
├── decorator.py        # @julia 装饰器
├── compiler.py         # Julia 代码编译
├── types.py            # Python ↔ Julia 类型映射
├── templates.py        # Julia 代码生成模板
└── _loader.py          # 共享库加载和函数调用
```

### 核心设计

#### 1. Julia 编译模式
Julia 使用 `ccall` 调用 C 共享库。桥接方案：
- 将 Python 函数体转换为 Julia 代码
- 生成包装函数使用 `ccall` 导出
- 编译为 `.so` (Linux/WSL) 或 `.dll` (Windows)
- ctypes 加载调用

#### 2. 类型映射 (Python ↔ Julia ↔ ctypes)
| Python | Julia (C ABI) | ctypes |
|--------|---------------|--------|
| int    | Int64         | c_int64 |
| float  | Float64       | c_double |
| bool   | Bool          | c_bool |
| str    | Cstring       | c_char_p |
| list   | Ptr{Cvoid}    | c_void_p |

#### 3. 装饰器 API (与 go.py 对齐)
```python
from vools.bridge.julia import julia, compile_and_run, julia_compiler_available

@julia
def add(a: int, b: int) -> int:
    return "return a + b"

@julia(mode='DEBUG')
def fib(n: int) -> int:
    return """
    if n <= 1
        return 1
    end
    return fib(n-1) + fib(n-2)
    """
```

#### 4. 编译命令 (Linux/WSL)
```bash
julia -e 'using PackageCompiler; create_shared_library("func", "libfunc.so")'
# 或使用 gcc 编译 Julia 生成的头文件
```

## 实现步骤

### Step 1: WSL 安装 Julia
```bash
wsl -e sh -c "curl -fsSL https://julialang.org/install.sh | sh"
# 或下载预编译版本到 WSL
```

### Step 2: 创建 julia/ 目录和基础文件

**julia/__init__.py**:
```python
"""vools.bridge.julia - Julia 语言桥接模块"""
from .decorator import julia, julia_compiler_available
from .compiler import JuliaCompiler, compile_julia_code
from .types import JuliaTypeMapper, get_julia_type, get_ctypes_type
from .templates import generate_julia_function
from ._loader import load_julia_dll, call_julia_function

__all__ = [
    'julia',
    'julia_compiler_available',
    'JuliaCompiler',
    'compile_julia_code',
    'JuliaTypeMapper',
    'get_julia_type',
    'get_ctypes_type',
    'generate_julia_function',
    'load_julia_dll',
    'call_julia_function',
]
```

### Step 3: 实现类型映射 (julia/types.py)
- Python 类型到 Julia C ABI 类型映射
- Julia C ABI 类型到 ctypes 类型映射
- 参数类型推断函数

### Step 4: 实现代码生成 (julia/templates.py)
- 生成 Julia 包装函数代码
- 处理字符串、数组等复杂类型
- 生成编译脚本

### Step 5: 实现编译逻辑 (julia/compiler.py)
- 检测 Julia 编译器
- 编译 Julia 代码为共享库
- 缓存管理

### Step 6: 实现装饰器 (julia/decorator.py)
- `@julia` 装饰器（与 go.py API 对齐）
- 支持模式: DEBUG, FORCE, NORMAL, ONLY_RUN, ONLY_CODE
- 异步模式支持

### Step 7: 实现加载器 (julia/_loader.py)
- 使用 ctypes 加载共享库
- 函数调用封装
- 错误处理

### Step 8: 更新 bridge/__init__.py
添加 Julia 模块的延迟加载支持

### Step 9: 更新 bridge/manager.py
注册 Julia 语言配置（Julia 编译器路径等）

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `vools/bridge/julia/__init__.py` | 新建 | 模块入口 |
| `vools/bridge/julia/types.py` | 新建 | 类型映射 |
| `vools/bridge/julia/templates.py` | 新建 | 代码生成模板 |
| `vools/bridge/julia/compiler.py` | 新建 | 编译逻辑 |
| `vools/bridge/julia/decorator.py` | 新建 | 装饰器 |
| `vools/bridge/julia/_loader.py` | 新建 | 共享库加载器 |
| `vools/bridge/__init__.py` | 修改 | 添加 Julia 延迟加载 |
| `vools/bridge/manager.py` | 修改 | 注册 Julia 语言配置 |

## 验证步骤
1. 确认 WSL Julia 安装成功: `wsl julia --version`
2. 测试基本整数运算: `@julia def add(a: int, b: int) -> int: return "a + b"`
3. 测试字符串参数传递
4. 测试递归函数 (fibonacci)
5. 测试 ONLY_CODE 模式生成 Julia 代码
