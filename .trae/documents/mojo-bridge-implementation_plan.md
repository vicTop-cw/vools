# vools.bridge.mojo — Mojo 动态编译桥接

## Summary
在 `vools.bridge` 框架下新增 Mojo 子包 `vools.bridge.mojo`，提供：
1. **`@mojo` 动态编译装饰器**（参考 `E:\IDEProjects\py\study\Pys\cross_lang\fbc.py` 的 `@fbc` 思路）：被装饰函数返回 Mojo 源码字符串，装饰器自动编译为 `.so` 并通过 ctypes 调用；
2. **预编译 `.so` 加载器**（参考 `vools/bridge/freebasic/loader.py`）：支持从 `vools/lib/mojo/` 加载用户已编译好的 Mojo 库。

运行环境为 **WSL 内 Linux**（Mojo 1.0b1 安装在 WSL），Python 也在 WSL 内运行，编译产物为 Linux 下的 `.so` 文件，复用 `ctypes.CDLL`。

**核心设计目标：免序列化（serialization-free）交互**
- 基本类型 `int/float/bool/bytes` 直接走 ctypes 原生类型；
- `str` 走 `c_char_p`（utf-8 编码/解码）+ Mojo 端 `UnsafePointer[c_char]`；
- `list[int]/list[float]` 直接 `POINTER(c_long/c_double) + 长度 c_long`，**不**经 CSV/JSON；
- 复用 `vools/bridge/core/loader.py` 的 `LibraryLoader` 缓存与跨平台机制。

复用 `vools/bridge/core`（loader / types / decorators / serialization），API 形态对齐 `vools.bridge.freebasic`（`@fbc / @mojo` 装饰器 + 预编译库加载 + Transport 抽象 + 类型映射表 + `is_*_available` 探测）。

不重写 `fbc.py`；不破坏 `vools.bridge.{nim,rust,freebasic,c,cpp,csharp}`；不引入第三方依赖（仅用 `subprocess` + `ctypes` + `hashlib` + `tempfile`，编译器 `mojo` 由用户在 WSL 自行安装）。

## Current State Analysis

### 现有桥接架构（已探索）
- `vools/bridge/core/loader.py`：跨平台共享库加载（Windows `.dll` / Linux `.so`），`LibraryLoader` 缓存 + 线程锁，`_LIB_DIR = vools/lib[/linux]`。
- `vools/bridge/core/types.py`：`CTypeMapper` 提供 `infer_arg_types / infer_ret_type / convert_args / get_ctype / register_type`。
- `vools/bridge/core/decorators.py`：`@bridge_function / @bridge_module`（仅 `getattr` 弱类型）。
- `vools/bridge/core/serialization.py`：CSV/JSON 序列化（本次免序列化路径**不**使用）。
- `vools/bridge/nim/{compiler,_loader}.py`：装饰器 + 编译 + 加载（CSV 序列化路径）。
- `vools/bridge/rust/{decorator,compiler,templates,types,_loader}.py`：完整 rust 装饰器栈（参考 fbc.py 模式）。
- `vools/bridge/freebasic/{compiler,loader,transport,types}.py`：完整 freebasic 装饰器栈（免序列化），是**最直接参考**。
- `vools/bridge/__init__.py`：延迟导入子模块。
- `vools/bridge/{c,cpp,csharp,rust,mojo}/__init__.py`：占位空模块。
- 目标 `vools/bridge/mojo/` 当前仅有一个 `__init__.py` 占位文件。

### 参考实现 `E:\IDEProjects\py\study\Pys\cross_lang\fbc.py` 关键点（已阅读）
- 装饰器 `@fbc(mode='DEBUG|FORCE|NORMAL|ONLY_RUN|ONLY_CODE', dll_abs_path, auto_signature=True)`；
- 函数体返回目标语言代码字符串，被装饰函数 `func(*[None] * len(sig.parameters))` 提取源码；
- `register_dll`：写盘 → `os.chdir` → `subprocess.run` → `shutil.move`；`PermissionError` 重试 3 次 + `.bak{n}` 重命名；
- 类型映射：`int→Long / float→Double / bool→Boolean / str→String / bytes→Byte Ptr / list→Any Ptr`；
- ctypes 映射：`int→c_long / float→c_double / bool→c_bool / str→c_wchar_p / bytes→c_char_p`；
- `infer_argtypes(args)`：运行时值推断 ctypes 列表；
- `auto_signature=True`：从函数体字符串里分离 `#` / `'` 注释行，拼接 `Function … As Long Export` 签名。

### Mojo 1.0b1 关键事实（已通过网络搜索 `docs.modular.com` 验证）
- 函数声明：`def name(arg: Type) -> RetType:`，使用 `def`（非 `fn`）；
- C FFI 导出：
  ```mojo
  @export("func_name")
  def func_name(a: Int64, b: Float64) -> Int64 abi("C"):
      ...
  ```
  - 必须使用 `@export` 装饰器；
  - 必须显式声明 `abi("C")`；
  - 形参支持 `Int8/16/32/64`、`UInt8/16/32/64`、`Float32/64`、`Bool`、`UnsafePointer[T]`、`String`（视版本）；
- 编译命令（待 WSL 实际验证，1.0b1 文档未明确 `--emit shared`）：
  - **推荐**：`mojo build -o libname.so source.mojo`（生成可执行文件，但 `-o` 路径可控；实测是否产出 `.so` 需在 WSL 验证）；
  - **备选 1**：`mojo build --emit shared -o libname.so source.mojo`；
  - **备选 2**：`mojo build -shared -o libname.so source.mojo`；
  - **Plan 中**封装为 `_try_compile_mojo(src, out_so)`，按优先级尝试命令直到成功；
- 文件名 Linux 下以 `.so` 结尾；`ctypes.CDLL(libname.so)` 可加载；
- Python 端集成官方推荐走 `Mojo from Python`（生成 Python 模块），但本次目标是**通用 ctypes FFI**，与官方 Python 集成路径**正交**。

### 与 freebasic 桥接的差异（需要适配）
- Mojo 强类型 + 显式 `Int64/Float64/Bool/UnsafePointer`；FB 用 `Long/Double/Boolean/Any Ptr`；
- Mojo 编译产物扩展名为 `.so`（Linux）；FB 编译产物为 `.dll`（Windows）+ `lib*.dll.a`；
- Mojo 字符串在 cdecl 边界用 `UnsafePointer[c_char]`（utf-8 C 字符串），**不是** `String`（Mojo `String` 类型 ABI 不稳定）；
- Mojo 数组参数用 `UnsafePointer[T]` + 长度 `Int64` 两个形参，FB 用 `Long Ptr + Long`；
- Mojo `Bool` 在 ctypes 边界等价于 `c_int`（0/1），FB `Boolean` 等价于 `c_bool`；
- Mojo 1.0b1 是预发布版，部分 ABI 行为可能变动，桥接代码需要在 `_try_compile_mojo` 处加探测/回退。

### "免序列化"对设计的影响
参考 nim `_loader.py`：所有 `seq_*.dll` 入参出参都先 `csv_serialize(list)` → `c_char_p` → C 端 `Split(...)` 解析。
本次 `mojo` 子包设计原则（与 freebasic 一致）：
- **基本类型（int / float / bool / bytes）** → 直接 `c_long` / `c_double` / `c_int`（Bool 走 c_int）/ `c_char_p`；
- **字符串（str）** → 直接 `c_char_p`（utf-8 编码 / 解码），Mojo 端 `UnsafePointer[c_char]`；
- **数组（list[int] / list[float]）** → 直接 `POINTER(c_int/c_double)` + 长度 `c_long`，Mojo 端 `UnsafePointer[Int64] + Int64`；**不**用 CSV；
- **None / 无返回值** → `restype = None`；
- **缓存层**：用 `tempfile + MD5`（与 freebasic 对齐）。

## Proposed Changes

### 文件结构（新增/修改）
```
vools/bridge/
├── mojo/                              # 已有目录（仅占位 __init__.py）
│   ├── __init__.py                    # 公开 API（重写）
│   ├── compiler.py                    # @mojo 装饰器 + 编译/缓存/调用（免序列化）
│   ├── loader.py                      # 预编译 .so 加载（vools/lib/mojo/）
│   ├── types.py                       # PY ↔ Mojo 类型映射表
│   ├── transport.py                   # 免序列化 Transport 抽象
│   ├── templates.py                   # Mojo 代码模板生成（@export 包装 + 签名拼接）
│   └── README.md                      # 使用说明（WSL 环境特别说明）
```

### 1) `vools/bridge/mojo/types.py` — 类型映射
**为什么**：把 fbc.py 中两套散落的类型表抽成模块级常量，并适配 Mojo 1.0b1 的 ABI。
**怎么做**：
- `PY_TO_MOJO_TYPE`：
  - `int → 'Int64'`（cdecl 边界统一 Int64，避免平台 long 长度差异）
  - `float → 'Float64'`
  - `bool → 'Bool'`
  - `str → 'UnsafePointer[c_char]'`（utf-8 C 字符串，**不是** Mojo `String`）
  - `bytes → 'UnsafePointer[c_char]'`
  - `list[int] → 'UnsafePointer[Int64]'`（实际签名追加 Int64 长度）
  - `list[float] → 'UnsafePointer[Float64]'`（实际签名追加 Int64 长度）
  - `dict / tuple / list[其他] → 'OpaquePointer'`（退化）
  - `type(None) → 'None'`
- `_TYPE_ALIASES`（处理 `typing.List[int]` 形式）：`'int'→'Int64' / 'float'→'Float64' / 'bool'→'Bool' / 'str'→'UnsafePointer[c_char]' / 'list[int]'→'UnsafePointer[Int64]' / 'list[float]'→'UnsafePointer[Float64]' / 'none'→'None'`。
- `get_mojo_type(py_type) -> str`：仿 `fbc.py::get_fb_type`，处理 `None`、字符串别名、未知类型默认 `'Int64'`。
- `infer_mojo_argtypes(args) -> list[str]`：
  - 元素全为 `int`（非 bool） → `'UnsafePointer[Int64]'`；
  - 元素全为 `float` → `'UnsafePointer[Float64]'`；
  - 其他 list → `'OpaquePointer'`；
  - 其他类型走与 PY_TO_MOJO_TYPE 相同的逻辑。
- `is_array_type(mojo_type) -> bool`：判断是否需要追加长度参数。
- `MOJO_TO_CTYPES`（Mojo → ctypes 端）：
  - `'Int64' → ctypes.c_longlong`
  - `'Float64' → ctypes.c_double`
  - `'Bool' → ctypes.c_int`（Mojo Bool 在 cdecl 边界是 0/1 int）
  - `'Int32' → ctypes.c_int32`
  - `'Float32' → ctypes.c_float`
  - `'UnsafePointer[c_char]' → ctypes.c_char_p`
  - `'UnsafePointer[Int64]' → ctypes.POINTER(ctypes.c_longlong)`
  - `'UnsafePointer[Float64]' → ctypes.POINTER(ctypes.c_double)`
  - `'OpaquePointer' → ctypes.c_void_p`
  - `'None' → None`（restype）
  - 默认 fallback `ctypes.c_longlong`。
- `get_ctype_for(mojo_type)`：便捷函数。

### 2) `vools/bridge/mojo/transport.py` — 免序列化 Transport 抽象
**为什么**：与 `freebasic/transport.py` 思路一致；可注入未来 `MojoTransport`（基于 `Mojo from Python` 官方路径）。
**怎么做**：
- `class Transport(Protocol)`：
  - `prepare_arg(arg, mojo_type) -> Tuple[ctypes-ready, ctypes-type]`
  - `prepare_ret(mojo_type) -> ctypes-type`
  - `decode_result(value, mojo_type) -> Python obj`
- `class CtypesTransport(Transport)`：纯 ctypes 实现：
  - `int`（边界检查：`2**31-1` 内走 `c_int`，否则 `c_longlong`）→ `(c_longlong(v), c_longlong)`；
  - `float → (c_double(v), c_double)`；
  - `bool → (c_int(1 if v else 0), c_int)`；
  - `str → (v.encode('utf-8'), c_char_p)`；
  - `bytes → (v, c_char_p)`；
  - `list[int] → ((c_longlong * n)(*v), POINTER(c_longlong))` + 长度另算；
  - `list[float] → ((c_double * n)(*v), POINTER(c_double))` + 长度另算；
  - 其他 → `(c_void_p, c_void_p)`。
  - `decode_result`：`c_char_p → bytes.decode('utf-8')`；`c_int (Bool) → bool(v)`。
- `class ZincTransport(Protocol stub)`：**保留入口**（与 freebasic 对齐；本次不实现，raise NotImplementedError）。
- 模块级 `_default_transport = CtypesTransport()`；`get_transport() / set_transport(t)`。

### 3) `vools/bridge/mojo/compiler.py` — 核心（`@mojo` 装饰器）
**为什么**：迁移 fbc.py 的 `register_dll + run_dll + @fbc` 三件套到 Mojo；用 `vools.bridge.freebasic.compiler` 的模板保证 API 形态一致。
**怎么做**：
- 平台常量：`_IS_LINUX = platform.system() == 'Linux'`（**WSL 下为 Linux**），`_LIB_EXT = '.so'`。
- `_MOJO_COMPILER = 'mojo'`；`_get_mojo_path() -> str`：先 `shutil.which('mojo')`，找不到则尝试 `/usr/local/bin/mojo`、`~/mojo/bin/mojo`、`~/.modular/bin/mojo`（Modular 默认安装路径）。
- `_setup_mojo_env()`：将找到的 mojo 目录 prepend `PATH`（必要时 `os.environ['MODULAR_HOME']`）。
- `mojo_compiler_available() -> bool`：跑 `[mojo_path, '--version']`，捕获 `FileNotFoundError`。
- `_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vools_mojo_cache')`。
- `_compile_mojo_source(src_path, out_so_path, force=False) -> str`：
  1. 命中缓存（`out_so_path` 存在且 `not force`）直接返回；
  2. 候选命令按优先级尝试（探测逻辑）：
     - `[mojo_path, 'build', '-o', out_so_path, src_path]`
     - `[mojo_path, 'build', '--emit', 'shared', '-o', out_so_path, src_path]`
     - `[mojo_path, 'build', '-shared', '-o', out_so_path, src_path]`
     - `[mojo_path, 'build', '--shared', '-o', out_so_path, src_path]`
  3. 每次失败打印 stderr 摘要，尝试下一个；
  4. 全部失败抛 `RuntimeError(f'Mojo 编译失败: {last_stderr}')`；
  5. 不使用 `os.chdir`，统一用 `cwd` 或写绝对路径（避免 fbc.py 那种全局副作用）。
- `_executor = ThreadPoolExecutor(max_workers=4)`；`class MojoFuture` 仿 `FbcFuture / NimFuture`。
- `_generate_mojo_wrapper(func_name, args, mojo_body, ret_type, arg_names) -> str`：
  1. `actual_ret_type` 默认 `'Int64'`；`'None' / NoneType` 时生成无 `-> RetType` 的 `@export` 函数；
  2. **数组签名**：`name: UnsafePointer[Int64], n: Int64`（FB 端写 `For i in range(n): ...`），Mojo 端用 `for i in range(n):` 循环；
  3. 函数体按 4 空格缩进；
  4. 包装为：
     ```mojo
     @export("func_name")
     def func_name(a: Int64, b: UnsafePointer[Int64], n: Int64) -> Int64 abi("C"):
         {body}
     ```
  5. 若 `auto_signature=True` 启用：函数体首行 `#` 注释保留在签名外部。
- `def mojo(func=None, *, mode='NORMAL', cache_dir=None, async_mode=False, auto_signature=True, ret_type=None)`：
  - 用法：`@mojo` / `@mojo(mode='DEBUG', ret_type='Int64')`；
  - `mode`：`DEBUG/FORCE → 强制重编译；NORMAL → 命中缓存跳过；ONLY_RUN → 缓存未命中抛 `FileNotFoundError`；ONLY_CODE → 返回生成代码不编译不调用`；
  - `auto_signature=True`：从函数体字符串里区分 `#` 注释与函数体，拼接签名（与 fbc.py 行为兼容）；
  - `async_mode=True` 时返回 `async_wrapper`，`loop.run_in_executor(_executor, …)`；
  - **入参处理**：当某个形参是 `list[int]` 类型注解时，编译时即在签名里追加 `arr: UnsafePointer[Int64], n: Int64` 两个 Mojo 形参；运行时把 Python list 拆成 `(c_longlong_array, length)` 传入。
- `def compile_and_run(mojo_code, func_name='main', args=(), ret_type='Int64', cache_dir=None) -> Any`：便捷入口。
- `is_mojo_available() -> bool`：探测 `vools.lib.mojo` 预编译库可用性（与 freebasic 对齐）。

### 4) `vools/bridge/mojo/loader.py` — 预编译 .so 加载
**为什么**：保留 nim `_loader.py` 与 freebasic `loader.py` 的能力，让 `vools.bridge.mojo` 也能加载 `vools/lib/mojo/` 下的预编译 .so 库（用户可用 `mojo build` 自行编译后放置）。
**怎么做**：
- `_MOJO_LIBS = {}` 模块级缓存。
- `get_mojo_lib(name, setup_func=None)`：调 `core.loader.load_library('mojo', name, setup_func)`。
- `is_mojo_available() -> bool`：探测 `vools/lib/mojo/libvools_mojo_demo.so`。
- 不实现具体 Mojo 业务模块（如 `crypto.mojo`），本次只做桥接基础设施。

### 5) `vools/bridge/mojo/templates.py` — Mojo 代码模板生成
**为什么**：抽出代码生成逻辑，便于后续扩展（多函数模块、PyO3 风格等）。
**怎么做**：
- `generate_function_signature(func_name, params, ret_type, export_name=None) -> str`：生成 `@export("...")` + `def name(...) -> RetType abi("C"):` 头。
- `generate_mojo_wrapper(func_name, body, params, ret_type) -> str`：组合签名 + 4 空格缩进 body + 闭合。
- `preprocess_mojo_body(body: str) -> str`：处理 `#` 注释剥离（与 fbc.py `auto_signature` 行为一致）。

### 6) `vools/bridge/mojo/__init__.py` — 公开 API
**导出**：
- 装饰器：`mojo / MojoFuture`
- 编译器：`mojo_compiler_available / compile_and_run / is_mojo_available`
- 类型映射：`PY_TO_MOJO_TYPE / MOJO_TO_CTYPES / get_mojo_type / get_ctype_for / infer_mojo_argtypes / is_array_type`
- Transport：`Transport / CtypesTransport / ZincTransport / get_transport / set_transport`
- 加载器：`get_mojo_lib / is_mojo_available`
- 模板：`generate_function_signature / generate_mojo_wrapper`
- `__all__` 与 freebasic 顺序一致；docstring 中文说明 WSL 依赖 `mojo` 在 PATH。

### 7) `vools/bridge/mojo/README.md` — 使用文档
- 前置：WSL 内安装 Modular Mojo 1.0b1（`curl https://get.modular.com | sh -` 或 `modular install mojo`），`mojo --version` 验证。
- 快速开始：`@mojo` 示例（递归 fib + 数组求和 + 字符串回显）。
- 免序列化说明：list 参数如何走 `UnsafePointer[Int64] + Int64`；与 nim CSV 路径的对比。
- 缓存路径：`%TEMP%/vools_mojo_cache/`。
- 预编译加载：把 `mojo build -o libname.so source.mojo` 的产物放入 `vools/lib/mojo/`，然后 `get_mojo_lib('libname')`。
- Transport 扩展点：如何实现自定义 `Transport` 并 `set_transport`。
- 平台说明：WSL Linux 主测；理论上 macOS / 原生 Linux 也可（只要有 `mojo` 工具链）；Windows 原生不支持（Mojo 1.0b1 仅 Linux/macOS）。
- WSL 与 Windows 主机混用的注意事项：Mojo 1.0b1 编译产物 `.so` 仅在 Linux ABI 下可加载；如在 Windows 主机 Python 中加载 WSL 文件系统的 `.so` 需要 WSL 路径映射 + Linux Python ABI，**本次不**支持。

### 8) `vools/bridge/__init__.py` 同步延迟导入
**修改**：
- 在 `try: from . import rust` 后追加 `try: from . import mojo` 块；
- `__all__` 中追加 `'mojo'`；
- 模块 docstring 顶部的子模块列表追加 `mojo: Mojo 语言桥接`（同时把"预留"改为"实现"）。

### 9) 测试文件 `tests/test_mojo_bridge.py`（新建）
**为什么**：与 `tests/test_fbc_bridge.py` / `tests/test_rust_decorator.py` 同结构，独立可执行。
**怎么做**：
- `test_mojo_compiler_available()`：断言返回 bool。
- 当 `mojo_compiler_available()` 为 False 时只跑这个并打印警告后退出（参考 fbc 桥接测试）。
- 后续 case（仅在编译器可用时跑）：
  - `test_simple_int_function`：`@mojo` 装饰 `def add(a: int, b: int) -> int`，Mojo 端 `return a + b`，验证 `add(2, 3) == 5`。
  - `test_string_function`（**Mojo 1.0b1 字符串 ABI 可能变动，标记 xfail**）：装饰 `def greet(name: str) -> str`，Mojo 端读取 c_char 指针 + 构造返回，验证 utf-8 往返。
  - `test_array_int_sum`（**新**，验证免序列化）：`def sum_arr(arr: list[int]) -> int`，Mojo 端 `def sum_arr(arr: UnsafePointer[Int64], n: Int64) -> Int64 abi("C"): var total = 0; for i in range(n): total += arr[i]; return total`，验证 `sum_arr([1,2,3,4,5]) == 15`。
  - `test_array_float_mean`（**新**）：`list[float]`，Mojo 端 `UnsafePointer[Float64]`。
  - `test_recursive_fibonacci`：`fib(10) == 55`。
  - `test_bool_arg`：`@mojo def bnot(flag: bool) -> bool`，Mojo 端 `return not flag`，验证 `bnot(True) is False`。
  - `test_cache`：同一函数二次调用应命中缓存（`compile_count` 计数 mock 验证）。
  - `test_async_mode`：`async def` + `await mojo_func()`。
  - `test_compile_and_run`：直接调 `compile_and_run("return a + b", args=(3, 4)) == 7`。
  - `test_mode_only_code`：`@mojo(mode='ONLY_CODE')` 返回字符串且不生成 `.so`。
  - `test_transport_replaceable`（**新**）：mock 一个假 Transport，验证 `set_transport/get_transport` 替换生效。
  - `test_precompiled_loader`：构造一个临时 .so（用 ctypes 写一个最简单的 c 函数或用 `gcc -shared`），放入 `vools/lib/mojo/`，验证 `get_mojo_lib` 加载成功（**Linux 专用**）。

### 10) `pyproject.toml` 同步（最小改动）
- `[project.optional-dependencies]` 追加 `mojo = []`，注释"需用户在 WSL 内安装 Mojo 1.0b1（Modular）"。
- 未来可注入 zinc 时追加 `zinc = ["zinc>=0.1"]`（**本次不**添加）。

### 11) `pyproject.toml` `[tool.pytest]` 与现有测试矩阵
- 不引入新依赖；测试仅在 Linux 下完整跑（CI 现有 matrix 是否含 Linux 暂不修改）。

## Assumptions & Decisions
- A1：编译器 `mojo` 由用户在 WSL 内安装，**不**硬编码本机路径。`mojo_compiler_available()` 用 `shutil.which` + `mojo --version` 探测；找不到时尝试 Modular 默认路径。
- A2：字符串入参/出参统一 `UnsafePointer[c_char]`（utf-8 `c_char_p`），**不**用 Mojo 原生 `String`（ABI 不稳定）。
- A3：编译缓存目录 `tempfile.gettempdir()/vools_mojo_cache/`，按 `code_md5[:12]` 去重。
- A4：本次不实现具体 Mojo 业务模块（如 `crypto.mojo`），只做桥接基础设施。
- A5：Mojo 1.0b1 编译 `.so` 的具体命令在文档中**未明确列出 `--emit shared`**；采用候选命令探测（`build` → `build --emit shared` → `build -shared` → `build --shared`），首个成功者作为后续默认命令。
- A6：`mode` 行为与 `fbc.py` 兼容（`DEBUG/FORCE/NORMAL/ONLY_RUN/ONLY_CODE`）。
- A7：失败回退（编译器缺失 / 编译失败）：装饰器内异常向上抛，与 freebasic / rust 行为一致。
- A8：**核心设计目标 = 免序列化**。list/array 参数走 `POINTER + 长度` 路径；不引入 CSV/JSON 中转。当 zinc / Mojo from Python 等 zero-copy 方案成熟时，可通过 `set_transport(...)` 注入更底层的实现，**本次仅留 stub**。
- A9：list 元素类型仅支持 `int` / `float`；混合类型 list 走 `OpaquePointer` 退化（与 fbc.py 一致）。
- A10：`auto_signature=True` 时，函数体首行的 `#` 注释会被剥离到签名外部；与 fbc.py 行为兼容。
- A11：**目标运行环境 = WSL Linux**。Windows 原生 Python 不在支持范围（Mojo 1.0b1 仅 Linux/macOS）。Plan 文档中明确告知用户。
- A12：Mojo 1.0b1 字符串 ABI 在某些 beta 小版本中可能调整；`test_string_function` 标记为 `xfail(strict=False)`，未来正式版通过时移除标记。

## Verification
1. **导入烟囱**：`python -c "from vools.bridge.mojo import mojo, mojo_compiler_available, compile_and_run, MojoFuture, is_mojo_available, Transport, CtypesTransport, set_transport, get_transport; print('ok')"`。
2. **顶层延迟导入**：`python -c "import vools; vools.bridge.mojo; print(vools.bridge.mojo.mojo)"`。
3. **桥接可用性**：`python -c "from vools.bridge.mojo import is_mojo_available, mojo_compiler_available; print(is_mojo_available(), mojo_compiler_available())"`（应在 WSL 下执行）。
4. **单元/集成测试**：`python tests/test_mojo_bridge.py`，期望在 `mojo` 可用时全部通过；不可用时打印警告后仅 `test_mojo_compiler_available` 通过。
5. **免序列化验证**：写一个 `sum_arr([1,2,3,4,5])` 测试，确认无 `csv_serialize` / `json.dumps` 调用（可通过 `grep -r "csv_serialize\|json.dumps" vools/bridge/mojo/` 确认无序列化中转）。
6. **缓存命中**：连续两次调用同函数，第二次不进 `_compile_mojo_source`（通过 monkeypatch `subprocess.run` 验证）。
7. **Transport 替换**：`set_transport(MyMockTransport())` 后调用 `@mojo` 函数应走 mock 路径。
8. **预编译加载**：临时构造一个简单 .so（`gcc -shared -o libtest.so test.c`），放入 `vools/lib/mojo/`，验证 `get_mojo_lib('test')` 加载成功。
9. **回归**：现有 `python test_nim_bridge.py` 与 `python -m pytest tests/test_vools.py` 仍通过（仅在 Linux 下相关）。
10. **类型映射表**：`from vools.bridge.mojo.types import PY_TO_MOJO_TYPE, MOJO_TO_CTYPES; assert PY_TO_MOJO_TYPE[int] == 'Int64'; assert MOJO_TO_CTYPES['UnsafePointer[Int64]'] is ctypes.POINTER(ctypes.c_longlong); assert MOJO_TO_CTYPES['UnsafePointer[Float64]'] is ctypes.POINTER(ctypes.c_double)`。

## 实现分阶段（建议执行顺序）
1. **types.py** + **templates.py**（无外部依赖，先落地）；
2. **transport.py**（依赖 types）；
3. **compiler.py**（依赖 types/templates/transport，**核心**）；
4. **loader.py**（依赖 core.loader，最简单）；
5. **__init__.py** 公开 API；
6. `vools/bridge/__init__.py` 延迟导入 + 文档；
7. **README.md**（中文，WSL 特别说明）；
8. `tests/test_mojo_bridge.py`（含 `mojo_compiler_available` 探测跳过逻辑）；
9. 在 WSL 内执行 `mojo --version` 验证环境；按探测顺序记录实际可用的编译命令并固化到 `_compile_mojo_source` 中。
