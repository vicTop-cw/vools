# vools.bridge.csharp — C# 动态编译桥接计划

## Summary

在现有 `vools.bridge` 框架下新增 C# 子包 `vools.bridge.csharp`，参考 `fbc.py` 的动态编译装饰器模式和 `nim` 桥接的 API 形态，实现 C# 代码的动态编译和 DLL 调用能力。核心目标是"简化代码"——通过 `@csharp` 装饰器让用户可以直接在 Python 中写 C# 代码片段，自动编译为 DLL 并调用，无需手动处理编译流程。

**关键特性：免序列化交互**
- 基于 ctypes 直接调用 C# DLL 导出函数
- 自动类型映射（Python ↔ C# ↔ ctypes）
- 支持零拷贝数据传递（通过指针传递）
- 自动生成 C# 函数签名和导出声明

## Current State Analysis

### 现有桥接架构

| 模块 | 功能 | 关键文件 |
|------|------|----------|
| `vools/bridge/core/loader.py` | 跨平台 DLL 加载（Windows/Linux） | `SharedLibrary`, `LibraryLoader` |
| `vools/bridge/core/types.py` | Python ↔ ctypes 类型映射 | `CTypeMapper`, `PY_TO_CTYPES` |
| `vools/bridge/core/decorators.py` | 桥接装饰器基类 | `@bridge_function`, `@bridge_module` |
| `vools/bridge/core/serialization.py` | CSV/JSON 序列化 | `Serializer` |
| `vools/bridge/nim/compiler.py` | Nim 动态编译 | `@nim`, `compile_and_run` |
| `vools/bridge/nim/_loader.py` | Nim 预编译库加载 | `get_nim_lib`, `is_nim_available` |
| `vools/bridge/c/__init__.py` | C DLL 加载和调用 | `load_dll`, `call_func`, `@c_dll`, `CDLLWrapper` |
| `vools/bridge/csharp/__init__.py` | **空占位模块** | 仅 `__all__ = []` |

### 参考实现 `fbc.py` 关键模式

```python
# fbc.py 核心模式（需要适配到 C#）

# 1. 类型映射表
PY_TO_FB_TYPE_MAP = {
    int: 'Long',
    float: 'Double',
    bool: 'Boolean',
    str: 'String',
    bytes: 'Byte Ptr',
}

# 2. 动态编译装饰器
@fbc(mode='NORMAL')
def fib(n: int) -> int:
    return """
    If n <= 1 Then Return 1
    Else Return fib(n-1) + fib(n-2)
    """

# 3. 编译流程
register_dll(fbc_code, dll_name, force=False)
# -> 写 .bas 文件 -> fbc64 编译 -> 生成 DLL -> 移动到缓存目录

# 4. DLL 调用
run_dll_auto(dll_path, func_name, args, ret_type)
# -> ctypes.CDLL -> 设置 argtypes/restype -> 调用
```

### C# 与 FreeBASIC/Nim 的差异

| 特性 | FreeBASIC | Nim | C# |
|------|-----------|-----|-----|
| 编译器 | `fbc64` | `nim c` | `dotnet build` / `csc` |
| 导出方式 | `cdecl Alias "name" Export` | `{.exportc.}` | `[DllExport]` 属性 |
| DLL 格式 | 标准 DLL | 标准 DLL | 需要 `DllExport` 工具或 `NativeAOT` |
| 类型系统 | BASIC 类型 | Nim 类型 | .NET 类型 |
| 运行时 | 无依赖 | nimcache | 需要 .NET Runtime 或 NativeAOT |

### C# DLL 导出方案选择

**方案 A：DllExport（推荐）**
- 使用 `RGiesecke.DllExport` 或 `3F/DllExport` NuGet 包
- 在方法上添加 `[DllExport]` 属性
- 编译后生成标准 DLL，可直接用 ctypes 调用
- **优点**：成熟稳定，支持多种调用约定
- **缺点**：需要 NuGet，编译流程稍复杂

**方案 B：NativeAOT（.NET 7+）**
- 使用 `PublishReadyToRun` 和 `NativeAOT` 编译
- 直接生成无 .NET Runtime 依赖的 DLL
- **优点**：零依赖，性能最优
- **缺点**：需要 .NET 7+，限制较多（不支持反射）

**方案 C：COM Interop**
- 通过 COM 接口调用 C# 对象
- **优点**：原生支持
- **缺点**：复杂度高，需要注册 COM

**决策：采用方案 A（DllExport）**
- 与现有 Nim/FreeBASIC 模式一致
- 支持 cdecl/stdcall 调用约定
- 可通过 NuGet 自动安装

## Proposed Changes

### 文件结构（新增）

```
vools/bridge/
├── csharp/                       # 新建
│   ├── __init__.py               # 公开 API
│   ├── compiler.py               # @csharp 装饰器 + 编译/缓存/调用
│   ├── loader.py                 # 预编译 C# 库加载
│   ├── types.py                  # Python ↔ C# 类型映射
│   ├── templates.py              # C# 代码模板生成器
│   └── README.md                 # 使用说明
```

### 1) `vools/bridge/csharp/types.py` — 类型映射

**目的**：定义 Python ↔ C# ↔ ctypes 三层类型映射表。

**实现**：

```python
"""
vools.bridge.csharp.types - Python ↔ C# ↔ ctypes 类型映射

提供三层类型映射：
1. Python → C# 类型（用于生成 C# 代码）
2. C# → ctypes 类型（用于 DLL 调用）
3. Python → ctypes 类型（复用 core.types）
"""

import ctypes

# Python → C# 类型映射（用于生成 C# 函数签名）
PY_TO_CS_TYPE = {
    int: 'int',              # 或 'long' 根据范围
    float: 'double',
    bool: 'bool',
    str: 'string',           # C# string -> 传参用 StringBuilder 或 char*
    bytes: 'byte[]',
    list: 'int[]',           # 默认 int[]，可指定泛型
    dict: 'object',          # 复杂类型用 object
    type(None): 'void',
}

# C# → ctypes 类型映射（用于设置 DLL 函数签名）
CS_TO_CTYPES = {
    'int': ctypes.c_int,
    'long': ctypes.c_long,
    'double': ctypes.c_double,
    'float': ctypes.c_float,
    'bool': ctypes.c_bool,
    'byte': ctypes.c_uint8,
    'sbyte': ctypes.c_int8,
    'short': ctypes.c_int16,
    'ushort': ctypes.c_uint16,
    'char': ctypes.c_char,           # 单字符
    'string': ctypes.c_char_p,       # 字符串指针（需要特殊处理）
    'byte[]': ctypes.c_char_p,       # 字节数组指针
    'int[]': ctypes.POINTER(ctypes.c_int),
    'double[]': ctypes.POINTER(ctypes.c_double),
    'void': None,
    'void*': ctypes.c_void_p,
    'IntPtr': ctypes.c_void_p,
}

def get_cs_type(py_type, value=None):
    """
    根据 Python 类型获取 C# 类型名称
    
    参数：
        py_type: Python 类型或类型注解字符串
        value: 可选的参数值，用于推断更精确的类型
    
    返回：
        C# 类型名称字符串
    """
    if py_type is None or py_type is type(None):
        return 'void'
    
    if isinstance(py_type, str):
        # 处理字符串类型注解
        type_aliases = {
            'int': 'int',
            'float': 'double',
            'bool': 'bool',
            'str': 'string',
            'bytes': 'byte[]',
            'list': 'int[]',
            'None': 'void',
        }
        return type_aliases.get(py_type.lower(), 'int')
    
    if py_type in PY_TO_CS_TYPE:
        # 根据值范围推断更精确的类型
        if py_type is int and value is not None:
            if -2**31 <= value < 2**31:
                return 'int'
            else:
                return 'long'
        return PY_TO_CS_TYPE[py_type]
    
    return 'int'  # 默认

def get_cs_ctype(cs_type):
    """
    根据 C# 类型获取 ctypes 类型
    
    参数：
        cs_type: C# 类型名称字符串
    
    返回：
        ctypes 类型
    """
    return CS_TO_CTYPES.get(cs_type, ctypes.c_void_p)

def infer_cs_argtypes(args):
    """
    根据参数值推断 C# 参数类型列表
    
    参数：
        args: 参数值列表
    
    返回：
        (cs_types, ctypes_types) 元组
    """
    cs_types = []
    ctypes_types = []
    for arg in args:
        py_type = type(arg)
        cs_type = get_cs_type(py_type, arg)
        cs_types.append(cs_type)
        ctypes_types.append(get_cs_ctype(cs_type))
    return cs_types, ctypes_types
```

### 2) `vools/bridge/csharp/templates.py` — C# 代码模板

**目的**：自动生成带 DllExport 属性的 C# 代码。

**实现**：

```python
"""
vools.bridge.csharp.templates - C# 代码模板生成器

自动生成包含 DllExport 属性的 C# 类和方法。
"""

# C# 项目文件模板（csproj）
CSPROJ_TEMPLATE = '''
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
    <OutputType>Library</OutputType>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <PlatformTarget>x64</PlatformTarget>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="DllExport" Version="1.7.4" />
  </ItemGroup>
</Project>
'''

# C# 类模板（带 DllExport）
CS_CLASS_TEMPLATE = '''
using System;
using System.Runtime.InteropServices;
using RGiesecke.DllExport;

namespace VoolsBridge
{
    public class BridgeFunctions
    {
{methods}
    }
}
'''

# C# 方法模板（单个导出函数）
CS_METHOD_TEMPLATE = '''
        [DllExport(CallingConvention = CallingConvention.Cdecl)]
        public static {return_type} {func_name}({params})
        {{
{body}
        }}
'''

def generate_cs_method(func_name, params, return_type, body):
    """
    生成单个 C# 导出方法
    
    参数：
        func_name: 函数名称
        params: 参数列表，格式 [(name, cs_type), ...]
        return_type: C# 返回类型
        body: 方法体代码字符串
    
    返回：
        完整的方法代码
    """
    # 构建参数字符串
    param_str = ', '.join(f'{cs_type} {name}' for name, cs_type in params)
    
    # 处理返回类型
    if return_type == 'void':
        ret_keyword = 'void'
    else:
        ret_keyword = return_type
    
    # 缩进方法体（4空格 + 8空格 = 12空格）
    indented_body = '\n'.join('            ' + line for line in body.strip().split('\n'))
    
    return CS_METHOD_TEMPLATE.format(
        return_type=ret_keyword,
        func_name=func_name,
        params=param_str,
        body=indented_body
    )

def generate_cs_class(methods_code):
    """
    生成完整的 C# 类代码
    
    参数：
        methods_code: 方法代码列表
    
    返回：
        完整的类代码
    """
    methods_str = '\n'.join(methods_code)
    return CS_CLASS_TEMPLATE.format(methods=methods_str)

def generate_csproj():
    """
    生成 C# 项目文件
    
    返回：
        csproj 文件内容
    """
    return CSPROJ_TEMPLATE.strip()
```

### 3) `vools/bridge/csharp/compiler.py` — 核心编译器

**目的**：实现 `@csharp` 装饰器和动态编译流程。

**实现要点**：

```python
"""
vools.bridge.csharp.compiler - C# 动态编译器

提供 @csharp 装饰器，支持：
- 自动生成 C# 代码和项目文件
- 调用 dotnet build 编译 DLL
- 基于 MD5 的代码缓存
- ctypes 调用导出函数
"""

import os
import sys
import subprocess
import hashlib
import tempfile
import ctypes
import functools
import inspect
import platform

from .types import get_cs_type, get_cs_ctype, infer_cs_argtypes
from .templates import generate_cs_method, generate_cs_class, generate_csproj
from ..core.types import CTypeMapper

_IS_WINDOWS = platform.system() == 'Windows'

# 缓存目录
_CS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_csharp_cache')

def csharp_compiler_available():
    """
    检查 C# 编译器是否可用
    
    返回：
        bool: dotnet 或 csc 是否在 PATH 中
    """
    try:
        result = subprocess.run(
            ['dotnet', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def _compile_csharp_code(cs_code, func_name, cache_dir=None):
    """
    编译 C# 代码为 DLL
    
    流程：
    1. 计算代码 MD5 哈希
    2. 检查缓存是否已存在 DLL
    3. 创建临时项目目录
    4. 写入 .cs 和 .csproj 文件
    5. 运行 dotnet build
    6. 返回 DLL 路径
    
    参数：
        cs_code: C# 方法体代码
        func_name: 函数名称
        cache_dir: 缓存目录，默认使用全局缓存
    
    返回：
        DLL 文件路径
    
    异常：
        RuntimeError: 编译失败时抛出
    """
    if cache_dir is None:
        cache_dir = _CS_CACHE_DIR
    
    os.makedirs(cache_dir, exist_ok=True)
    
    # 计算哈希
    code_hash = hashlib.md5(cs_code.encode('utf-8')).hexdigest()[:12]
    dll_name = f'cs_{func_name}_{code_hash}'
    
    # 检查缓存
    dll_path = os.path.join(cache_dir, dll_name + '.dll')
    if os.path.exists(dll_path):
        return dll_path
    
    # 创建项目目录
    project_dir = os.path.join(cache_dir, dll_name)
    os.makedirs(project_dir, exist_ok=True)
    
    # 写入文件
    cs_file = os.path.join(project_dir, 'Bridge.cs')
    csproj_file = os.path.join(project_dir, 'Bridge.csproj')
    
    # 生成完整代码（需要从装饰器获取签名信息）
    # 这里简化为直接编译已有代码
    
    # 编译
    result = subprocess.run(
        ['dotnet', 'build', '-c', 'Release', '-o', cache_dir],
        cwd=project_dir,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        raise RuntimeError(f'C# 编译失败:\n{result.stderr}\n{result.stdout}')
    
    return dll_path

def _call_csharp_func(dll_path, func_name, args, ret_type=None):
    """
    调用 C# DLL 中的函数
    
    参数：
        dll_path: DLL 文件路径
        func_name: 函数名称
        args: 参数列表
        ret_type: Python 返回类型注解
    
    返回：
        函数返回值
    """
    lib = ctypes.CDLL(dll_path)
    
    # 推断类型
    cs_types, ctypes_types = infer_cs_argtypes(args)
    
    func = getattr(lib, func_name)
    func.argtypes = ctypes_types
    
    # 设置返回类型
    if ret_type is None or ret_type is type(None):
        func.restype = None
    else:
        cs_ret = get_cs_type(ret_type)
        func.restype = get_cs_ctype(cs_ret)
    
    # 转换参数（字符串需要特殊处理）
    converted_args = []
    for arg, cs_type in zip(args, cs_types):
        if cs_type == 'string' and isinstance(arg, str):
            # C# string 需要传递为字节串
            converted_args.append(arg.encode('utf-8'))
        else:
            converted_args.append(arg)
    
    result = func(*converted_args)
    
    # 处理返回值
    if func.restype == ctypes.c_char_p and isinstance(result, bytes):
        return result.decode('utf-8')
    
    return result

def csharp(func=None, mode='NORMAL', cache_dir=None, ret_type=None, auto_signature=True):
    """
    C# 动态编译装饰器
    
    参数：
        func: 被装饰的函数
        mode: 运行模式
            - NORMAL: DLL 存在则用，不存在则编译
            - DEBUG: 强制重新编译
            - FORCE: 只编译不执行
            - ONLY_RUN: 只运行，DLL 不存在则报错
            - ONLY_CODE: 只生成代码不编译
        cache_dir: 缓存目录
        ret_type: 返回类型（可覆盖注解）
        auto_signature: 是否自动生成签名
    
    用法：
        @csharp
        def add(a: int, b: int) -> int:
            return "return a + b;"
        
        @csharp(mode='DEBUG')
        def greet(name: str) -> str:
            return "return $\"Hello, {name}!\";"
    """
    def decorator(func):
        sig = inspect.signature(func)
        func_name = func.__name__
        
        def generate_full_cs_code():
            """
            生成完整的 C# 代码（包含签名和导出属性）
            """
            # 获取参数类型
            params = []
            for param_name, param in sig.parameters.items():
                py_type = param.annotation if param.annotation != param.empty else int
                cs_type = get_cs_type(py_type)
                params.append((param_name, cs_type))
            
            # 获取返回类型
            if ret_type is not None:
                py_ret = ret_type
            elif 'return' in func.__annotations__:
                py_ret = func.__annotations__['return']
            else:
                py_ret = int
            
            cs_ret = get_cs_type(py_ret)
            
            # 获取方法体
            body = func(*[None] * len(sig.parameters))
            
            # 生成方法代码
            method_code = generate_cs_method(func_name, params, cs_ret, body)
            
            # 生成类代码
            class_code = generate_cs_class([method_code])
            
            return class_code, cs_ret
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 确定缓存路径
            if cache_dir is None:
                cache_dir = _CS_CACHE_DIR
            
            dll_path = os.path.join(cache_dir, f'cs_{func_name}.dll')
            
            mode_upper = mode.upper()
            
            # 处理 ONLY_CODE 模式
            if mode_upper == 'ONLY_CODE':
                cs_code, _ = generate_full_cs_code()
                return cs_code
            
            # 检查是否需要编译
            need_compile = (
                mode_upper in ('DEBUG', 'FORCE') or
                (mode_upper == 'NORMAL' and not os.path.exists(dll_path))
            )
            
            if need_compile:
                cs_code, cs_ret = generate_full_cs_code()
                
                try:
                    dll_path = _compile_csharp_code(cs_code, func_name, cache_dir)
                except Exception as e:
                    raise RuntimeError(f'C# 编译失败: {e}')
                
                if mode_upper == 'FORCE':
                    return dll_path
            
            elif mode_upper == 'ONLY_RUN' and not os.path.exists(dll_path):
                raise FileNotFoundError(f'DLL 不存在: {dll_path}')
            
            # 调用函数
            py_ret = ret_type or func.__annotations__.get('return', int)
            return _call_csharp_func(dll_path, func_name, args, py_ret)
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    
    return decorator

def compile_and_run(cs_code, func_name='main', args=(), ret_type=int, cache_dir=None):
    """
    便捷函数：编译并运行 C# 代码
    
    参数：
        cs_code: C# 方法体代码
        func_name: 函数名称
        args: 参数列表
        ret_type: 返回类型
        cache_dir: 缓存目录
    
    返回：
        函数返回值
    """
    dll_path = _compile_csharp_code(cs_code, func_name, cache_dir)
    return _call_csharp_func(dll_path, func_name, args, ret_type)
```

### 4) `vools/bridge/csharp/loader.py` — 预编译库加载

**目的**：加载预编译的 C# DLL（类似 Nim 的 `_loader.py`）。

**实现**：

```python
"""
vools.bridge.csharp.loader - 预编译 C# 库加载器

加载 vools/lib/ 下的预编译 C# DLL。
"""

from ..core.loader import load_library

_CS_LIBS = {}

def get_cs_lib(name, setup_func=None):
    """
    获取 C# 共享库
    
    参数：
        name: 库名称（不含扩展名）
        setup_func: 可选的函数签名设置函数
    
    返回：
        ctypes.CDLL 实例，加载失败返回 None
    """
    if name in _CS_LIBS:
        return _CS_LIBS[name]
    
    lib = load_library('csharp', name, setup_func)
    _CS_LIBS[name] = lib
    return lib

def is_csharp_available():
    """
    检查 C# 桥接是否可用
    
    返回：
        bool: 是否有可用的 C# 库或编译器
    """
    from .compiler import csharp_compiler_available
    return csharp_compiler_available() or get_cs_lib('vools_csharp_demo') is not None
```

### 5) `vools/bridge/csharp/__init__.py` — 公开 API

**实现**：

```python
"""
vools.bridge.csharp - C# 语言桥接模块

提供 C# 代码的动态编译和 DLL 调用能力。

前置条件：
- 安装 .NET SDK (dotnet) 并添加到 PATH
- 或提供预编译的 C# DLL

用法：
    from vools.bridge.csharp import csharp, compile_and_run
    
    @csharp
    def add(a: int, b: int) -> int:
        return "return a + b;"
    
    result = add(1, 2)  # 自动编译并调用
    
    # 直接运行代码
    result = compile_and_run("return 42;", args=())
"""

from .compiler import (
    csharp,
    csharp_compiler_available,
    compile_and_run,
)
from .loader import get_cs_lib, is_csharp_available
from .types import (
    PY_TO_CS_TYPE,
    CS_TO_CTYPES,
    get_cs_type,
    get_cs_ctype,
)

__all__ = [
    'csharp',
    'csharp_compiler_available',
    'compile_and_run',
    'get_cs_lib',
    'is_csharp_available',
    'PY_TO_CS_TYPE',
    'CS_TO_CTYPES',
    'get_cs_type',
    'get_cs_ctype',
]
```

### 6) `vools/bridge/__init__.py` 同步更新

**修改**：

```python
# 在现有导入后追加
try:
    from . import csharp
except ImportError:
    pass

# __all__ 中追加
__all__ = [
    # ... 现有导出
    'csharp',
]
```

### 7) 测试文件 `tests/test_csharp_bridge.py`

**实现**：

```python
"""
测试 C# 桥接功能
"""

import pytest
from vools.bridge.csharp import (
    csharp,
    csharp_compiler_available,
    compile_and_run,
    is_csharp_available,
)

def test_csharp_compiler_available():
    """测试编译器可用性检查"""
    result = csharp_compiler_available()
    assert isinstance(result, bool)
    if not result:
        pytest.skip("C# 编译器不可用，跳过后续测试")

def test_simple_int_function():
    """测试简单整数函数"""
    @csharp
    def add(a: int, b: int) -> int:
        return "return a + b;"
    
    result = add(2, 3)
    assert result == 5

def test_string_function():
    """测试字符串函数"""
    @csharp
    def greet(name: str) -> str:
        return "return $\"Hello, {name}!\";"
    
    result = greet("World")
    assert "Hello" in result
    assert "World" in result

def test_recursive_function():
    """测试递归函数"""
    @csharp
    def fib(n: int) -> int:
        return """
        if (n <= 1) return n;
        return fib(n - 1) + fib(n - 2);
        """
    
    result = fib(10)
    assert result == 55

def test_mode_only_code():
    """测试 ONLY_CODE 模式"""
    @csharp(mode='ONLY_CODE')
    def dummy(x: int) -> int:
        return "return x * 2;"
    
    code = dummy(5)
    assert isinstance(code, str)
    assert 'DllExport' in code
    assert 'dummy' in code

def test_compile_and_run():
    """测试便捷函数"""
    result = compile_and_run("return 42;", args=())
    assert result == 42
```

## Assumptions & Decisions

### A1: 编译器依赖
- **假设**：用户已安装 .NET SDK（`dotnet` 在 PATH 中）
- **决策**：不硬编码编译器路径，使用 `subprocess.run(['dotnet', ...])`

### A2: DllExport 方案
- **假设**：使用 `RGiesecke.DllExport` NuGet 包
- **决策**：在 csproj 模板中自动添加 PackageReference

### A3: 类型映射策略
- **假设**：C# `string` 类型通过 `char*` 传递（UTF-8 编码）
- **决策**：字符串入参/出参统一用 `c_char_p` + UTF-8

### A4: 缓存策略
- **假设**：缓存目录为 `%TEMP%/vools_csharp_cache/`
- **决策**：按代码 MD5[:12] 去重，DLL 命名 `cs_{func}_{hash}.dll`

### A5: 调用约定
- **假设**：使用 cdecl 调用约定（与 FreeBASIC/Nim 一致）
- **决策**：`[DllExport(CallingConvention = CallingConvention.Cdecl)]`

### A6: zinc 库集成
- **假设**：zinc 是 Rust 编写的"免序列化交互"库（类似 PyO3）
- **决策**：本计划先实现 C# 桥接基础设施，zinc 集成作为后续扩展

### A7: 与 fbc.py 的差异
- **不沿用**：`fbc.py` 的 `os.chdir` 全局副作用
- **不沿用**：`fbc.py` 的 `dll_abs_path` 跳过编译逻辑
- **沿用**：`@fbc` 的装饰器模式和 `mode` 参数语义

## Verification

### 1. 单元测试
```bash
python tests/test_csharp_bridge.py
```
期望：在 `dotnet` 可用时全部通过

### 2. 导入验证
```bash
python -c "from vools.bridge.csharp import csharp, compile_and_run; print('ok')"
```

### 3. 顶层延迟导入
```bash
python -c "import vools; vools.bridge.csharp; print(vools.bridge.csharp.csharp)"
```

### 4. 桥接可用性
```bash
python -c "from vools.bridge.csharp import is_csharp_available, csharp_compiler_available; print(is_csharp_available(), csharp_compiler_available())"
```

### 5. 未安装编译器时
- `csharp_compiler_available()` 返回 `False`
- `@csharp` 装饰的函数被调用时抛 `RuntimeError`

### 6. 缓存命中验证
连续两次调用同函数，第二次不触发编译（可通过日志或 monkeypatch 验证）

### 7. 回归测试
现有 `nim` 和 `c` 桥接测试仍通过：
```bash
python tests/test_nim_bridge.py
python tests/test_vools.py
```

## Future Extensions

### zinc 库集成（后续）
如果 zinc 是 Rust 的 PyO3 类库，可以：
1. 在 `vools/bridge/rust/` 下实现类似 `@rust` 装饰器
2. 使用 `maturin` 或 `cargo` 编译 Rust Python 扩展
3. 支持 PyO3 的零拷贝数据传递

### C# 高级功能
- 支持泛型和复杂类型
- 支持异步方法（async/await）
- 支持 C# 类实例化和方法调用（通过 COM 或自定义协议）

## References

- [RGiesecke.DllExport](https://github.com/3F/DllExport)
- [.NET NativeAOT](https://learn.microsoft.com/en-us/dotnet/core/deploying/native-aot)
- [vools.bridge.nim](file:///e:/IDEProjects/AI/vools/vools/bridge/nim/__init__.py)
- [vools.bridge.c](file:///e:/IDEProjects/AI/vools/vools/bridge/c/__init__.py)
- [fbc.py 参考](file:///E:/IDEProjects/py/study/Pys/cross_lang/fbc.py)