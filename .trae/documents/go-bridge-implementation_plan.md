# Go 桥接实现计划

## Overview

- **Summary**: 在 `vools.bridge` 下实现 Go 语言动态编译桥接，**单文件 `vools/bridge/go.py`**，对齐 fbc.py 的装饰器风格；函数体返回 Go 代码字符串，运行时通过 `go build -buildmode=c-shared` 编译为 `.dll`/`.so`，再由 ctypes 加载执行。
- **Purpose**: 为 vools 增加 Go 高性能/并发桥接能力；用户用 `@go` 装饰器把任意 Go 函数体（字符串）即时编译为可被 Python ctypes 调用的共享库。
- **关键约束**:
  - 参考文件：`E:\IDEProjects\py\study\Pys\cross_lang\fbc.py`
  - 复用：`vools.bridge.core.types`（`CTypeMapper` / `PY_TO_CTYPES` / `infer_arg_types` / `infer_ret_type` / `convert_args`）
  - 沿用：`vools.bridge.freebasic.transport` 的 `CtypesTransport` 设计（list → `*C.long` + len）
  - 异步/并行/并发：用 `concurrent.futures.ThreadPoolExecutor` + `GoFuture`（与 Nim/Mojo/FbcFuture 同形）
- **Target Users**: vools 库开发者、需要 Go 并发与 Python 互操作的用户

## Current State Analysis

### 现有桥接基础设施
- `vools/bridge/core/loader.py`: `SharedLibrary` / `load_from_path` / `LibraryLoader` / `is_available`
- `vools/bridge/core/types.py`: `CTypeMapper` 静态类，提供 `infer_arg_types` / `infer_ret_type` / `convert_args`
- `vools/bridge/core/serialization.py`: `Serializer`（本方案不依赖，保留作为 future 用）
- 装饰器参考：
  - **fbc.py (用户参考)**: `register_dll` + `fbc` 装饰器（DEBUG/FORCE/NORMAL/ONLY_RUN/ONLY_CODE 5 种模式）
  - `vools/bridge/freebasic/compiler.py`: 完整实现，含 `async_mode=True`、`FbcFuture`
  - `vools/bridge/mojo/compiler.py`: 含 `MojoFuture`、`compile_and_run`
  - `vools/bridge/nim/compiler.py`: 含 `NimFuture`、`compile_and_run`
- 异步约定（已成熟）：`_executor = ThreadPoolExecutor(max_workers=4)`，wrapper 中 `loop.run_in_executor(_executor, _do_call)`，`async_mode=True` 时返回 `XXXFuture`（薄包装 `concurrent.futures.Future`）或 `async def wrapper`。

### 参考实现 fbc.py 的关键设计
- `PY_TO_CTYPES_MAP` + `infer_argtypes(args)`: 自动 ctypes 类型推断
- `register_dll(fbc_code, dll_name, force)`: 写 `.bas` → `fbc64 -s gui -dll -export` → 移到 `__fbc__/dlls/`
- `@fbc(mode=...)` 装饰器：5 种 mode + `auto_signature` 开关
- 强制/缓存策略：dll_abs_path + force 删除

### Go 桥接的差异点
- **Go ABI**：必须用 `//export FuncName` + `import "C"` 暴露 C 调用入口；普通 Go 函数不导出
- **字符串 ABI**：Go `string` 头部是 `(ptr, len)`，不是 NUL 结尾；通过 cgo 包装函数 + 返回 `*C.char` 显式做 `C.GoString` / `C.CString` 转换
- **列表/切片**：用 `unsafe.Pointer(data)` + `C.long(len)` 传入（与 freebasic transport 一致）
- **编译命令**：
  - Windows: `go build -buildmode=c-shared -o xxx.dll xxx.go`
  - Linux:   `go build -buildmode=c-shared -o libxxx.so xxx.go`
  - macOS:   `go build -buildmode=c-shared -o libxxx.dylib xxx.go`
- **运行时依赖**：纯 Go stdlib 一般免依赖；若用户 `import` 第三方包则需要 `go.mod` / `GOPATH` 内可用
- **pygo 选择**：用户回复确认"可以使用 pygo"——本方案采用 **pygo 风格的 cgo + ctypes 模式**（即编译为 c-shared 后用 ctypes 加载，导出函数通过 `//export`+`import "C"` 暴露）。

### 项目约定
- 文件位置：`vools/bridge/go.py`（用户明确要求单文件 fbc.py 风格）
- `vools/bridge/__init__.py` 中已存在 `_go_loaded = False` 占位 + `_load_go()` + `__getattr__` 分支入口，**需要补齐**
- `vools/bridge/__init__.py` 的 `__all__` 列表中**需要新增** `go` 条目

## Proposed Changes

### 1. 新增文件 `vools/bridge/go.py`（单文件实现）

#### 1.1 顶部常量与运行时探测
```python
import os, sys, tempfile, hashlib, platform, asyncio, inspect, functools
import ctypes, shutil, threading, subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any

# 平台判断（与 freebasic 同一份判断）
_IS_WINDOWS = platform.system() == 'Windows'
_IS_LINUX   = platform.system() == 'Linux'
_IS_MACOS   = platform.system() == 'Darwin'

# 编译器名
_GO_COMPILER = 'go'
# 常用 PATH 搜索
_GO_SEARCH_PATHS_WINDOWS = [
    r"C:\Program Files\Go\bin",
    r"C:\Go\bin",
    os.path.expanduser("~/go/bin"),
]
_GO_SEARCH_PATHS_UNIX = [
    "/usr/local/go/bin",
    "/opt/homebrew/bin",
    os.path.expanduser("~/go/bin"),
    "/usr/bin",
    "/usr/local/bin",
]
```
依据：Mojo `compiler.py` 已经用 `shutil.which` + fallback 列表的模式，照搬即可。

#### 1.2 编译器检测 (`go_compiler_available`)
- `_get_go_path()`: `shutil.which('go')` → 失败时遍历 `_GO_SEARCH_PATHS_*` → 兜底返回 `'go'`
- `go_compiler_available() -> bool`: `subprocess.run([path, 'version'], capture_output=True, text=True, timeout=5)`，returncode == 0 判为可用
- `is_go_available()`: 编译器可用 OR 命中已编译缓存

#### 1.3 编译逻辑 (`_compile_go_code`)
- 缓存目录：`os.path.join(tempfile.gettempdir(), 'vools_go_cache')`
- 文件名：`<func_name>_<md5[:12]>.go` + 编译产物（Win: `.dll`，Linux: `.so`，macOS: `.dylib`）
- 编译命令（核心 4 行）：
  - Windows: `[go, 'build', '-buildmode=c-shared', '-o', dll_path, src_path]`
  - Linux/macOS: 同上（`-buildmode=c-shared` 跨平台一致）
- 失败处理：把 stderr/stdout/源码塞进 `RuntimeError`（与 fbc/freebasic 行为一致）
- 缓存命中：`os.path.exists(dll_path)` 直接返回

#### 1.4 类型映射 `PY_TO_GO_TYPE` / `GO_TO_CTYPES`
```python
PY_TO_GO_TYPE = {
    int:   'int64',
    float: 'float64',
    bool:  'bool',
    str:   '*C.char',   # 经 cgo 包装为 *C.char
    bytes: 'unsafe.Pointer',  # 配 len
    list:  'unsafe.Pointer',  # 配 len
}

GO_TO_CTYPES = {
    'int64':          ctypes.c_int64,
    'float64':        ctypes.c_double,
    'bool':           ctypes.c_bool,
    '*C.char':        ctypes.c_char_p,
    'unsafe.Pointer': ctypes.c_void_p,
}
```
依据：复用 `vools.bridge.core.types.CTypeMapper.infer_arg_types / infer_ret_type / convert_args`，避免重复造轮子。

#### 1.5 代码生成 (`_generate_go_source`)
- 输入：`func_name`, `param_types` (list of `[(name, go_type, is_array)]`), `ret_type`, `body`
- 输出：完整 Go 源码，含：
  - `package main` (c-shared 必须)
  - `import "C"` + `import "unsafe"`
  - **每个数组参数拆为 `(ptr unsafe.Pointer, n int64)` 两个 C 参数**
  - 函数体用 `//export FuncName` 导出
  - 返回值若是字符串：在 cgo 包装层 `return C.CString(goStr)`；若是数组：`C.GoBytes(unsafe.Pointer(data), C.int(n))` 不在本层暴露（保持指针+长度协议）
  - 缩进规则：body 行 4 空格
- 示例（用户 `body="return int64(a)+int64(b)"` + 签名 `add(a int64, b int64) int64`）：
  ```go
  package main

  import "C"
  import "unsafe"

  //export add
  func add(a C.longlong, b C.longlong) C.longlong {
      return C.longlong(int64(a) + int64(b))
  }

  func main() {}  // c-shared 必须
  ```
- 函数体前可注入的 `import` 用户自定义：扫描 body 中 `^import` 行（与 fbc.py 的 `preprocessor_lines` 同款处理）

#### 1.6 函数调用 (`_call_go_function`)
- 用 `cdll.LoadLibrary(dll_path)`（与 `vools.bridge.core.loader.load_from_path` 一致；Windows 上需要 `os.add_dll_directory(dll_path_dir)` 解决 libgo / dll 依赖）
- 构造 ctypes argtypes：标量走 `CTypeMapper.infer_arg_types`；数组走 `(c_void_p, c_long)` 两项
- `argtypes` 注入后 `func.restype` 同样按 ret_type 推断
- 数组参数运行时打包：`(c_long * n)(*values)`，传入 `ctypes.cast(arr, c_void_p)` + `c_long(n)`
- 字符串参数：`CTypeMapper.convert_args` 已处理 `str -> bytes utf-8` → 传入 `c_char_p` 即可
- 返回值解码：标量直返；`c_char_p` → `result.decode('utf-8')`

#### 1.7 异步执行 (`GoFuture` + `_executor`)
```python
_executor = ThreadPoolExecutor(max_workers=4)
class GoFuture:
    def __init__(self, fn, *a, **kw):
        self._f = _executor.submit(fn, *a, **kw)
    def result(self, timeout=None): return self._f.result(timeout)
    def done(self): return self._f.done()
    def add_done_callback(self, fn): self._f.add_done_callback(fn)
    def cancel(self): return self._f.cancel()
    def __await__(self): return self._f.__await__()
```
依据：照搬 `vools/bridge/mojo/compiler.py:241-263 MojoFuture` 的薄包装实现。

#### 1.8 装饰器 `@go` (与 fbc.py @fbc 同形)
签名（关键字-only，与 Mojo 对齐）：
```python
def go(func=None, *, mode='NORMAL', cache_dir=None, ret_type=None,
       async_mode=False, auto_signature=True):
```
- `func is not None` → `@go` 形式
- `func is None` → `@go(...)` 形式
- 内部根据 `mode.upper()` 分支：
  - `ONLY_CODE` → 返回生成的 Go 源码字符串（不编译、不执行）
  - `FORCE` → 强制重编译（删 cache + 重新 _compile_go_code），不执行
  - `DEBUG` → 强制重编译 + 执行
  - `NORMAL` → 命中缓存跳过编译；未命中则编译
  - `ONLY_RUN` → 缓存不存在则抛 `FileNotFoundError`
- `async_mode=False` → 返回 `wrapper` (同步)
- `async_mode=True` → 返回 `async def async_wrapper`（走 `_executor`）；同时支持通过 `@go(...)` 返回 `GoFuture` 模式（与 mojo 一致，即 `async_mode=True` 时直接 `return GoFuture(_do_call)`，让 `await` 拿到结果）

#### 1.9 便捷入口 `compile_and_run`
- 仿 `vools/bridge/freebasic/compiler.py:576 compile_and_run`：
  ```python
  def compile_and_run(go_code, func_name='main', args=(), ret_type='int64', cache_dir=None):
  ```
- 直接调 `_compile_go_code` + `_call_go_function`

#### 1.10 公开 API (`__all__`)
```python
__all__ = [
    'go', 'compile_and_run', 'go_compiler_available', 'is_go_available',
    'GoFuture', 'PY_TO_GO_TYPE', 'GO_TO_CTYPES',
    'get_go_type', 'infer_go_argtypes', 'is_array_type',
    '_compile_go_code', '_call_go_function', '_generate_go_source',
    '_GO_CACHE_DIR',
]
```

### 2. 修改 `vools/bridge/__init__.py`

按现有 nim/mojo/freebasic 的写法补齐 4 处：

1. 顶部 import 段加 `from .core.serialization import Serializer`（已有，无需改）
2. docstring 顶部说明补 `go: Go 语言桥接实现`
3. `__all__` 列表加 `'go'`
4. 模块级加 `_go_loaded = False`
5. 加 `_load_go()` 函数（仿 `_load_freebasic`）
6. `__getattr__` 增加 `if name == 'go': if _load_go(): ...`

### 3. 异步/并行/并发 三种模式的具体落实

| 模式 | 触发方式 | 实现 | 测试用例 |
|------|---------|------|---------|
| **同步** | `@go` 默认 | `wrapper` 直接调 `_do_call` | `add(2, 3) == 5` |
| **异步 (单函数 await)** | `@go(async_mode=True)` | `wrapper` 返回 `GoFuture`，可 `await` | `await add(2, 3) == 5` |
| **并行 (多任务并发)** | `asyncio.gather` + `@go` 普通装饰 | ctypes 调用本身在 GIL 外，多个 ctypes 调用天然并行；外层用 ThreadPoolExecutor 调度编译 | `asyncio.gather(*[fib(i) for i in range(10)])` 全部成功 |
| **并发 (线程池)** | `@go(async_mode=True)` + 同时调用 N 次 | 共享 `_executor (max_workers=4)` | `await asyncio.gather(*[add(i, i) for i in range(20)])` 全部成功 |

关键点：Go 函数编译为 c-shared 后，**每次 ctypes 调用都释放 GIL**（因为 ctypes 在 native 调用前后会 `PyEval_SaveThread`），所以 N 个 Python 线程同时调用同一个 Go 共享库函数是**真正并发**的——这是 vools 现有所有语言桥接（c/nim/mojo/fbc）都具备的能力，Go 桥继承即可。

## Assumptions & Decisions

1. **不引入第三方 Go 依赖**：所有生成的 Go 代码只用 stdlib (`unsafe`/`C`)，避免 `go.mod` 管理复杂度。
2. **不预编译固定模块**：与 nim/freebasic 一致，运行时按需编译；后续若需要可仿照 `vools/bridge/nim/crypto.py` 预编译 demo。
3. **跨平台字符串协议统一为 c_char_p**：与 freebasic/mac 的 `ZString Ptr` 同形，避免 Go 端 `*C.char` 的内存管理负担（cgo 包装层 `C.CString` 由 c-shared 库负责释放路径有陷阱，本方案采用 `*C.char` + `ctypes` 端 `c_char_p`，依赖 freebasic transport 经验）。
4. **数组用 `unsafe.Pointer + int64`**：与 freebasic/mojo transport 一致，免序列化。
5. **缓存键用 `func_name + md5(code)`**：与 freebasic/mojo 行为一致。
6. **位置**：用户明确要求 `vools/bridge/go.py`（单文件），不复用 `vools/bridge/go/` 包结构。
7. **Windows MSVC vs MinGW**：Go 自身是 MinGW-friendly 的 c-shared 输出，不需要额外配置；如遇 runtime 缺 `libgo.dll` 等情况，依靠 `os.add_dll_directory` 与现有 nim/freebasic 相同策略。
8. **错误信息**：编译失败时把 `stderr + stdout + 完整 .go 源码` 一起塞进 `RuntimeError`，便于用户排查（沿用 freebasic 模式）。
9. **测试脚本**：不主动创建（用户没要求）。如果之后需要，模式参考 `tests/test_mojo_bridge.py`。

## Verification

执行者（executor）实现完成后，建议按以下顺序验证：

1. **单元层（不依赖编译器）**：
   - `PY_TO_GO_TYPE` / `GO_TO_CTYPES` 内容正确
   - `_generate_go_source` 在 `ONLY_CODE` 模式下生成的字符串包含 `//export <func_name>` 与 `package main`
   - `_call_go_function` 在 dll 缺失时抛 `FileNotFoundError`（不调 go build）

2. **集成层（依赖 go 编译器）**：
   - `go_compiler_available() == True`
   - 同步路径：
     ```python
     from vools.bridge.go import go
     @go
     def add(a: int, b: int) -> int:
         return "return int64(a) + int64(b)"
     assert add(2, 3) == 5
     ```
   - 异步路径：
     ```python
     @go(async_mode=True)
     def fib(n: int) -> int:
         return """
         if int64(n) <= 1 { return 1 }
         return fib(n-1) + fib(n-2)
         """
     import asyncio
     assert asyncio.run(fib(10)) == 89
     ```
   - 并行路径（验证 4 worker 并发）：
     ```python
     async def main():
         results = await asyncio.gather(*[add(i, i) for i in range(20)])
         assert results == [i*2 for i in range(20)]
     asyncio.run(main())
     ```
   - 缓存命中：同一函数第二次调用不进 `_compile_go_code`（目录里只有一个 .dll）
   - 模式分支：
     - `mode='ONLY_CODE'` → 返回源码字符串
     - `mode='FORCE'` → 强制重编译，返回 dll 路径
     - `mode='DEBUG'` → 强制重编译 + 执行
     - `mode='ONLY_RUN'` 缺失 dll 时抛 `FileNotFoundError`

3. **回归层**：
   - `from vools.bridge import go` 可正常导入
   - `vools.bridge.go is not None` 在 `go_compiler_available() == False` 时也成立（模块本身可加载，仅运行时函数调用失败）

4. **跨平台（条件允许时）**：
   - Windows: 输出 `xxx.dll`，可被 `cdll.LoadLibrary` 加载
   - Linux: 输出 `libxxx.so`，同上

## File-level Change Summary

| 文件 | 操作 | 说明 |
|------|------|------|
| `vools/bridge/go.py` | **新增**（单文件） | Go 桥接完整实现：常量、检测、编译、类型、代码生成、调用、Future、装饰器、compile_and_run |
| `vools/bridge/__init__.py` | **修改** | 在 nim/mojo/freebasic 旁补 `_go_loaded` + `_load_go()` + `__getattr__` 分支 + `__all__` 加 `'go'` |

总行数预估：`vools/bridge/go.py` 约 380-450 行（含 docstring），`vools/bridge/__init__.py` 改动 < 20 行。
