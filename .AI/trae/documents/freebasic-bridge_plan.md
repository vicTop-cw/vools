# vools.bridge.fbc — FreeBASIC 动态编译桥接（免序列化交互）

## Summary
在现有 `vools.bridge` 框架下新增 FreeBASIC 子包 `vools.bridge.fbc`，把 `E:\IDEProjects\py\study\Pys\cross_lang\fbc.py` 中的能力（`@fbc` 动态编译装饰器、`register_dll` 编译注册、`run_dll` / `run_dll_auto` 调用）迁移并规范化，**关键设计目标：免序列化（serialization-free）交互**——所有入参/出参直接走 ctypes 原生类型（`POINTER(c_int)` / `c_char_p` / `Structure`），不经过 CSV/JSON 字符串中转，对齐 zinc 风格的 zero-copy 思路。

复用 `vools/bridge/core`（loader / types / decorators），公开 API 形态对齐 `vools.bridge.nim`（`@fbc` / `compile_and_run` / `fbc_compiler_available` / `is_fbc_available` / `FbcFuture`）。zinc 本身是 Rust 编译的 Python 库（用户提及"可以用 zinc"），本次**不**硬依赖 zinc（环境未安装），而是把"免序列化"作为架构目标：当 zinc 可用时可在 `compiler.py` 注入 `zinc.Transport`，当前实现以纯 ctypes 实现等价能力。

不重写 `fbc.py`；不破坏 `vools.bridge.c/nim`；不实现 `cpp/csharp/rust/mojo`；不引入第三方依赖（仅用 `subprocess` + `ctypes`，编译器 `fbc64` 需用户自行安装到 PATH）。

## Current State Analysis

### 现有桥接架构
- `vools/bridge/core/loader.py`：跨平台共享库加载（Windows `.dll` / Linux `.so`），`LibraryLoader` 缓存 + 线程锁。
- `vools/bridge/core/types.py`：`CTypeMapper` 提供 `infer_arg_types / infer_ret_type / convert_args / get_ctype / register_type`。
- `vools/bridge/core/decorators.py`：`@bridge_function` / `@bridge_module`（当前仅做 `getattr` 调用，类型推断弱）。
- `vools/bridge/core/serialization.py`：CSV / JSON 序列化。
- `vools/bridge/nim/compiler.py`：`@nim` 装饰器 + 动态编译 + `_call_nim_func`（复用 `CTypeMapper`） + `compile_and_run` + `nim_compiler_available`。
- `vools/bridge/nim/_loader.py`：`get_nim_lib(name)` / `is_nim_available()`，按 `name -> setup_func` 注册 `argtypes/restype`。**注意：nim 业务模块的 `seq_*.dll` 接收的是 CSV 编码的 `c_char_p`**（见 `_loader.py` 中大量 `lib.seq_*.argtypes = [ctypes.c_char_p]`），需要序列化往返。
- `vools/bridge/c/__init__.py`：`load_dll / call_func / c_dll / CDLLWrapper`（纯 ctypes 路径）。
- `vools/bridge/{cpp,csharp,rust,mojo}/__init__.py`：占位空模块。
- `vools/lib/`：预编译 nim 库。

### 参考实现 `E:\IDEProjects\py\study\Pys\cross_lang\fbc.py` 关键点
- 编译器：`fbc64`（需在 PATH），编译命令 `fbc64 -s gui -dll -export <basfile>`。
- 工作目录：`__fbc__/dlls/{name}.dll` + `lib{name}.dll.a`。
- Python ↔ FreeBASIC 类型映射：`int→Long / float→Double / bool→Boolean / str→String / bytes→Byte Ptr / list/dict/tuple→Any Ptr / None→Void`。
- ctypes 映射：`int→c_long / float→c_double / bool→c_bool / str→c_wchar_p / bytes→c_char_p / None→None`。
- `infer_argtypes(args)`：按运行时值推断 ctypes 列表（`-2**31..2**31-1` → `c_int`，否则 `c_longlong`；list → `POINTER(c_int)` 或 `c_void_p`）。
- 装饰器：`@fbc(mode='DEBUG|FORCE|NORMAL|ONLY_RUN|ONLY_CODE', dll_abs_path, auto_signature=True)`。
- `register_dll`：写盘 → `os.chdir` → `subprocess.run` → `shutil.move`；`PermissionError` 重试 3 次 + 重命名 `.bak{n}`。
- 限制：依赖 `os.chdir` 全局副作用；无代码缓存；无 MinGW 运行时路径；`is_file(fbc_code)` 误判；`c_longlong` 边界缺失。

### 与 nim 桥接的差异（需要适配）
- FB 显式 `Export` + `cdecl`；Nim 用 `{.exportc.}`。
- FB 单文件直接出 DLL；Nim 需要 `nim c --app:lib --passL:-Wl,--export-all`。
- FB 编译产物是 `*.dll` + `lib*.dll.a`（MinGW 链接用 import lib），运行时只需 DLL。
- 字符串返回：FB `String` 在 cdecl 边界需要 `Function … As ZString Ptr`（utf-8 bytes）；**不用** `As String`（避免 BSTR 编码歧义）。

### "免序列化"对设计的影响
参考 nim `_loader.py`：所有 `seq_*.dll` 入参出参都先 `csv_serialize(list)` → `c_char_p` 字节串，FB 端再 `Split(...)` 解析。每次调用要走 `str → bytes → C → str` 三段式往返，对大数据/高频调用场景成本明显。

本次 `fbc` 子包的设计原则：
- **基本类型（int / float / bool / bytes）** → 直接 `c_long` / `c_double` / `c_bool` / `c_char_p`（已经是 native）。
- **字符串（str）** → 直接 `c_char_p`（utf-8 编码 / 解码），FB 端用 `ZString Ptr`。
- **数组（list[int] / list[float]）** → 直接 `POINTER(c_int)` + 长度 `c_long`，FB 端用 `Long Ptr` + `Long` 长度参数；**不**用 CSV。
- **结构体（tuple/list of tuples）** → 用 `ctypes.Structure`，FB 端用 `Type … End Type`。
- **None / 无返回值** → `restype = None` / 生成 `Sub … End Sub`。
- **缓存层**：`fbc.py` 每次都重编；本次用 `tempfile + MD5 缓存`（与 nim 对齐）。

## Proposed Changes

### 文件结构（新增）
```
vools/bridge/
├── freebasic/                       # 新建
│   ├── __init__.py                  # 公开 API
│   ├── compiler.py                  # @fbc 装饰器 + 编译/缓存/调用（免序列化）
│   ├── loader.py                    # 预编译 FB 库加载（vools/lib/fbc_*.dll）
│   ├── types.py                     # PY ↔ FreeBASIC 类型映射表
│   ├── transport.py                 # 免序列化 Transport 抽象（可注入 zinc 适配）
│   └── README.md                    # 使用说明
```

### 1) `vools/bridge/freebasic/types.py` — 类型映射
**为什么**：把 `fbc.py` 中两套散落的类型表抽成模块级常量。
**怎么做**：
- `PY_TO_FB_TYPE`：`int→'Long' / float→'Double' / bool→'Boolean' / str→'ZString Ptr' / bytes→'ZString Ptr' / list[int]→'Long Ptr' / list[float]→'Double Ptr' / dict/tuple→'Any Ptr' / None.__class__→'Void'`，字符串别名回退（`int→'Long'` 等），处理 `typing.List[int]` 形式。
- `FB_TO_CTYPES`：`'Long'→ctypes.c_long / 'Double'→ctypes.c_double / 'Boolean'→ctypes.c_bool / 'ZString Ptr'→ctypes.c_char_p / 'Byte Ptr'→ctypes.c_char_p / 'Long Ptr'→ctypes.POINTER(ctypes.c_long) / 'Double Ptr'→ctypes.POINTER(ctypes.c_double) / 'Any Ptr'→ctypes.c_void_p / 'Void'→None`。
- `get_fb_type(py_type) -> str`：仿 `fbc.py::get_fb_type`，处理 `None`、字符串别名、未知类型默认 `'Long'`。
- `infer_fb_argtypes(args) -> list[str]`：**与 `fbc.py::infer_argtypes` 不同**——list 不再用 `POINTER(c_int)` + CSV，而是分两类：
  - 元素全为 `int` → `'Long Ptr'`；
  - 元素全为 `float` → `'Double Ptr'`；
  - 其他 → `'Any Ptr'`。
- `infer_fb_argtypes_with_length(args) -> (list[str], list[any])`：额外把 list 拆成 `(ptr, length)` 两个入参，FB 函数签名需显式接收 `ByVal arr As Long Ptr, ByVal n As Long`。

### 2) `vools/bridge/freebasic/transport.py` — 免序列化 Transport 抽象
**为什么**：把"如何把 Python 对象变成 ctypes 参数"封装为可替换的 Transport；当前实现是 `_CtypesTransport`（纯 ctypes），未来可注入 `ZincTransport`（当用户安装 `zinc` PyPI 包时）。
**怎么做**：
- `class Transport(Protocol)`：
  - `prepare_arg(arg: Any, fb_type: str) -> Tuple[ctypes.Any, ctypes.Any]`：把 Python 值转成 `(ctypes 值, ctypes 类型)`，例如 list[int] → `(c_long * len(arr))(*arr), POINTER(c_long)`。
  - `prepare_ret(fb_type: str) -> ctypes.Any`：返回 ctypes restype。
  - `decode_result(value: Any, fb_type: str) -> Any`：把 ctypes 返回值解码回 Python（c_char_p → str；POINTER → list）。
- `class CtypesTransport(Transport)`：纯 ctypes 实现，零外部依赖。规则：
  - `int → (c_long(value), c_long)`（边界 `2**31-1` 走 `c_longlong`）；
  - `float → (c_double(value), c_double)`；
  - `bool → (c_bool(value), c_bool)`；
  - `str → (value.encode('utf-8'), c_char_p)`；
  - `bytes → (value, c_char_p)`；
  - `list[int] → ((c_long * len(v))(*v), POINTER(c_long))` + 长度另算；
  - `list[float] → ((c_double * len(v))(*v), POINTER(c_double))` + 长度另算；
  - 其他 → `(c_void_p(value), c_void_p)`。
  - `decode_result`：若 `c_char_p` → `bytes.decode('utf-8')`；若 `POINTER(c_long)` + 长度上下文 → `list(ptr[i] for i in range(n))`。
- `class ZincTransport(Transport)`：**仅占位 stub**（`raise NotImplementedError("zinc not installed; install with `pip install zinc`")`），保留入口以备未来集成；本次不实现。
- 模块级默认 `_default_transport = CtypesTransport()`，`set_transport(t)` / `get_transport()` 全局可替换。

### 3) `vools/bridge/freebasic/compiler.py` — 核心
**为什么**：`fbc.py::register_dll + run_dll + @fbc` 三件套迁移地；用 nim 的 `compiler.py` 模板保证 API 形态一致。
**怎么做**：
- 平台常量 `_IS_WINDOWS = platform.system() == 'Windows'`。
- `_FBC_COMPILER = 'fbc64'`；`_FBC_RUNTIME_PATHS` 在 Windows 上与 `core/loader._RUNTIME_PATHS` 同源；`_setup_fbc_env()` 调用 `os.add_dll_directory` 并 prepend PATH。
- `_get_fbc_path()`：先查 `_FBC_RUNTIME_PATHS`，再 `shutil.which('fbc64')`。
- `fbc_compiler_available() -> bool`：跑 `fbc64 --version`。
- `_BAS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_fbc_cache')`。
- `_compile_fbc_code(code, func_name, cache_dir=None) -> str`：
  1. `code_hash = hashlib.md5(code.encode('utf-8')).hexdigest()[:12]`；
  2. `dll_name = f'fbc_{func_name}_{code_hash}'`；`bas_path = cache_dir/{dll_name}.bas`；`dll_path = cache_dir/{dll_name}.dll`；
  3. 命中缓存（`os.path.exists(dll_path)`）直接返回；
  4. 写 `.bas` → `subprocess.run(['fbc64', '-s', 'gui', '-dll', '-export', bas_path], cwd=cache_dir)`；
  5. 失败抛 `RuntimeError(f'FreeBASIC 编译失败:\n{result.stderr}\n{result.stdout}')`；
  6. 返回 `dll_path`。
- **修正** `fbc.py` 的 `os.chdir` 全局副作用：本次**不调用** `os.chdir`，统一用 `cwd=cache_dir`。
- **修正** `fbc.py` 静态库 `shutil.move`：本次只关心 `*.dll`，不归档 `lib*.dll.a`。
- **修正** `fbc.py::is_file(fbc_code)` 误判：路径分支用 `os.path.isfile` 严格判断。
- `_load_fbc_dll(dll_path) / _call_fbc_func(dll_path, func_name, args, ret_type)`：复用 `transport.get_transport()`：
  - 用 `infer_fb_argtypes_with_length` 得到 FB 入参类型；
  - 对每个入参调 `transport.prepare_arg(arg, fb_type)`；
  - 数组额外追加 `c_long(len(arg))` 作为长度参数；
  - 设置 `func.argtypes / func.restype`；
  - 调用并 `transport.decode_result`。
- `_generate_fbc_wrapper(func_name, args, fbc_body, ret_type, arg_names) -> str`：
  1. `actual_ret_type` 默认 `'Long'`；`Void` / `None` 时生成 `Sub … End Sub`；
  2. **数组签名**：`name As Long Ptr, n As Long`（FB 端写 `For i As Long = 0 To n - 1: arr[i] = ...: Next`）；
  3. 函数体按 4 空格缩进；
  4. 包装为 `Function {name} cdecl Alias "{name}"({params}) As {ret} Export\n  {body}\nEnd Function`。
- `_executor = ThreadPoolExecutor(max_workers=4)`；`class FbcFuture` 仿 `NimFuture`。
- `def fbc(func=None, *, cache_dir=None, ret_type=None, async_mode=False, mode='NORMAL')`：
  - 用法：`@fbc` / `@fbc(mode='DEBUG', ret_type='string')`。
  - `mode`：`DEBUG/FORCE → 强制重编译；NORMAL → 命中缓存跳过；ONLY_RUN → 缓存未命中抛 `FileNotFoundError`；ONLY_CODE → 返回生成代码不编译不调用`。
  - `auto_signature=True` 沿用 `fbc.py`：从函数体字符串里区分 `#` / `'` 注释与函数体，拼接签名。
  - `async_mode=True` 时返回 `async_wrapper`，`loop.run_in_executor(_executor, …)`。
  - **入参处理**：当某个形参是 `list[int]` 类型注解时，编译时即在签名里追加 `arr As Long Ptr, n As Long` 两个 FB 参数；运行时把 Python list 拆成 `(c_long_array, length)` 传入。
- `def compile_and_run(fbc_code, func_name='main', args=(), ret_type='int', cache_dir=None)`：便捷入口。

### 4) `vools/bridge/freebasic/loader.py` — 预编译库加载
**为什么**：保留 nim `_loader.py` 的能力，让 `vools.bridge.fbc` 也能加载 `vools/lib/` 下的预编译 FB 库。
**怎么做**：
- `_FBC_LIBS = {}` 模块级缓存。
- `get_fbc_lib(name, setup_func=None)`：调 `core.loader.load_library('fbc', name, setup_func)`。
- `is_fbc_available()`：探测 `get_fbc_lib('vools_fbc_demo')`；本次约定 demo 库名，缺则返回 False。
- 不实现具体 FB 业务模块（crypto/seq/…）——本次只做桥接基础设施。

### 5) `vools/bridge/freebasic/__init__.py` — 公开 API
**导出**：`fbc / fbc_compiler_available / compile_and_run / FbcFuture / PY_TO_FB_TYPE / FB_TO_CTYPES / get_fb_type / get_fbc_lib / is_fbc_available / Transport / CtypesTransport / ZincTransport / set_transport / get_transport`。
- `__all__` 与 nim 顺序一致；docstring 中文说明依赖 `fbc64` 在 PATH。

### 6) `vools/bridge/freebasic/README.md` — 使用文档
- 前置：安装 FreeBASIC（`fbc64` 在 PATH）。
- 快速开始：`@fbc` 示例（递归 fib + 数组求和 + 字符串回显）。
- 免序列化说明：list 参数如何走 `Long Ptr + n`；与 nim CSV 路径的对比。
- 缓存路径：`%TEMP%/vools_fbc_cache/`。
- Transport 扩展点：如何实现 `ZincTransport` 并 `set_transport`。
- 平台说明：Windows 主测。

### 7) `vools/bridge/__init__.py` 同步延迟导入
**修改**：
- 在 `try: from . import nim` 后追加 `try: from . import fbc` 块。
- `__all__` 中追加 `'fbc'`。
- 模块 docstring 顶部的子模块列表追加 `fbc: FreeBASIC 语言桥接`。

### 8) 测试文件 `tests/test_fbc_bridge.py`（新建）
**为什么**：与 `test_nim_bridge.py` 同结构，独立可执行。
**怎么做**：
- `test_fbc_compiler_available()`：断言返回 bool。
- 当 `fbc_compiler_available()` 为 False 时只跑这个并打印警告后退出。
- 后续 case（仅在编译器可用时跑）：
  - `test_simple_int_function`：`@fbc` 装饰 `def add(a:int,b:int)->int: return "Return a + b"` 调 `add(2,3)==5`。
  - `test_string_function`：装饰 `def greet(name:str)->str: return 'Return "Hi " & *name'` 验证 utf-8 往返。
  - `test_array_int_sum`（**新**，验证免序列化）：`def sum_arr(arr: list[int]) -> int`，FB 端 `Function … (arr As Long Ptr, n As Long) As Long` 循环累加；`sum_arr([1,2,3,4,5])==15`。
  - `test_array_float_mean`（**新**）：`list[float]`，FB 端 `Double Ptr`。
  - `test_recursive_fibonacci`：`fib(10)==55`。
  - `test_cache`：同一函数二次调用应命中缓存。
  - `test_async_mode`：`async def` + `await fbc_func()`。
  - `test_compile_and_run`：直接调 `compile_and_run("Return a + b", args=(3,4))==7`。
  - `test_mode_only_code`：`@fbc(mode='ONLY_CODE')` 返回字符串且不生成 `.dll`。
  - `test_transport_replaceable`（**新**）：mock 一个假 Transport，验证 `set_transport/get_transport` 替换生效。

### 9) `pyproject.toml` 同步（最小改动）
- `[project.optional-dependencies]` 追加 `fbc = []`，注释"需用户自行安装 fbc64"。
- 未来 zinc 可用时追加 `zinc = ["zinc>=0.1"]`（**本次不**添加）。

## Assumptions & Decisions
- A1：编译器 `fbc64` 由用户配置，**不**硬编码本机路径。`fbc_compiler_available()` 用 `shutil.which` + `fbc64 --version` 探测。
- A2：字符串入参/出参统一 `ZString Ptr`（utf-8 `c_char_p`），与 ctypes 习惯一致。
- A3：编译缓存目录 `tempfile.gettempdir()/vools_fbc_cache/`，按 `code_md5[:12]` 去重。
- A4：本次不实现具体 FB 业务模块（`fbc/crypto.py` 等），只做桥接基础设施。
- A5：原 `fbc.py` 中 `__fbc__/dlls/` 路径策略弃用，改用 nim 风格的 `tempfile` 缓存。
- A6：`mode` 行为与 `fbc.py` 兼容（`DEBUG/FORCE/NORMAL/ONLY_RUN/ONLY_CODE`）。
- A7：失败回退（编译器缺失 / 编译失败）：装饰器内异常向上抛，与 nim 行为一致。
- A8：**核心设计目标 = 免序列化**。list/array 参数走 `POINTER + 长度` 路径；不引入 CSV/JSON 中转。当 `zinc` 库可用时（用户后续安装），可通过 `set_transport(ZincTransport())` 注入更底层的 zero-copy 实现，**本次仅留 stub**。
- A9：list 元素类型仅支持 `int` / `float`；混合类型 list 走 `Any Ptr` 退化（与 `fbc.py` 一致）。
- A10：`auto_signature=True` 时，函数体首行的 `'` / `#` 注释会被剥离到签名外部；与 `fbc.py` 行为兼容。

## Verification
1. **单元/集成测试**：`python tests/test_fbc_bridge.py`，期望在 `fbc64` 可用时全部通过。
2. **导入烟囱**：`python -c "from vools.bridge.fbc import fbc, fbc_compiler_available, compile_and_run, FbcFuture, is_fbc_available, Transport, CtypesTransport, set_transport, get_transport; print('ok')"`。
3. **顶层延迟导入**：`python -c "import vools; vools.bridge.fbc; print(vools.bridge.fbc.fbc)"`。
4. **桥接可用性**：`python -c "from vools.bridge.fbc import is_fbc_available, fbc_compiler_available; print(is_fbc_available(), fbc_compiler_available())"`。
5. **免序列化验证**：写一个 `sum_arr([1,2,3,4,5])` 测试，确认无 `csv_serialize` 调用（可通过 `grep -r "csv_serialize" vools/bridge/freebasic/` 确认无 CSV 中转）。
6. **缓存命中**：连续两次调用同函数，第二次不进 `_compile_fbc_code`（通过 monkeypatch `subprocess.run` 验证）。
7. **Transport 替换**：`set_transport(MyMockTransport())` 后调用 `@fbc` 函数应走 mock 路径。
8. **回归**：现有 `python test_nim_bridge.py` 与 `python -m pytest tests/test_vools.py` 仍通过。
9. **类型映射表**：`from vools.bridge.fbc.types import PY_TO_FB_TYPE, FB_TO_CTYPES; assert PY_TO_FB_TYPE[int] == 'Long'; assert FB_TO_CTYPES['ZString Ptr'] is ctypes.c_char_p; assert FB_TO_CTYPES['Long Ptr'] is ctypes.POINTER(ctypes.c_long)`。
