# R 语言桥接实现计划

## 1. 仓库研究结论

### 现有桥接框架架构

vools.bridge 采用统一的模块化架构，每种语言桥接遵循相似的目录结构：

```
vools/bridge/
├── core/           # 核心基础设施
│   ├── loader.py       # 共享库加载器（ctypes CDLL）
│   ├── types.py        # Python ↔ ctypes 类型映射
│   ├── decorators.py   # @bridge_function / @bridge_module 装饰器
│   └── serialization.py # 序列化层
├── freebasic/      # FreeBASIC 桥接（编译型，参考 fbc.py）
│   ├── __init__.py
│   ├── compiler.py     # 动态编译 + 装饰器
│   ├── loader.py       # 预编译库加载
│   ├── transport.py    # 数据传输层
│   └── types.py        # 类型映射
├── rust/           # Rust 桥接（编译型，完整实现）
│   ├── __init__.py
│   ├── compiler.py     # Cargo 编译封装
│   ├── decorator.py    # @rust 装饰器
│   ├── templates.py    # 代码生成模板
│   ├── types.py        # 类型映射
│   └── _loader.py      # DLL 加载
└── ...             # 其他语言（nim, csharp, mojo, scala, cangjie 等）
```

### 参考实现特点

1. **fbc.py 参考文件** (`E:\IDEProjects\py\study\Pys\cross_lang\fbc.py`)：
   - 装饰器模式：`@fbc` 装饰器，函数体返回 FreeBASIC 代码字符串
   - 编译型：将 BASIC 代码编译为 DLL，通过 ctypes 调用
   - 支持多种模式：DEBUG / FORCE / NORMAL / ONLY_RUN / ONLY_CODE
   - 自动签名生成：根据 Python 类型注解生成 FB 函数签名

2. **vools.bridge.freebasic**（已集成到框架）：
   - 对齐 fbc.py 的 API 形态
   - 增加 transport 层（支持 zero-copy）
   - 免序列化交互（list 参数走 POINTER + 长度）

3. **vools.bridge.rust**（最完整实现）：
   - `@rust` 装饰器 + `rust_module` 类装饰器
   - 同步/异步双模式
   - Cargo 项目管理 + 编译缓存
   - 完整的类型映射系统

### R 语言特殊性

R 与已有的编译型语言（Rust/FreeBasic/Nim）有本质区别：

| 特性 | 编译型语言 (Rust/FB) | R (解释型) |
|------|----------------------|------------|
| 执行方式 | 编译为 DLL，ctypes 调用 | 通过 Rscript 解释执行 |
| 运行位置 | 本地进程内 | WSL 子进程 |
| 数据交互 | 内存直接交互（ctypes） | 进程间通信（stdin/stdout/文件） |
| 启动开销 | 低（DLL 加载一次） | 较高（每次启动 R 进程） |
| 类型系统 | C ABI 类型 | R 语言类型 |

---

## 2. 需要编辑的文件和模块

### 新增文件

| 文件路径 | 职责 |
|---------|------|
| `vools/bridge/r/__init__.py` | R 桥接模块入口，导出公共 API |
| `vools/bridge/r/types.py` | Python ↔ R 类型映射（JSON 序列化层） |
| `vools/bridge/r/compiler.py` | R 执行引擎（WSL + Rscript）+ @r 装饰器 |
| `vools/bridge/r/loader.py` | R 环境检测与可用性检查 |
| `vools/bridge/r/templates.py` | R 代码模板生成器 |
| `tests/test_r_bridge.py` | R 桥接测试 |

### 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `vools/bridge/__init__.py` | 添加 R 模块的延迟导入支持 |

---

## 3. 修改/新增步骤

### 步骤 1：类型映射模块 (types.py)

**目标**：建立 Python ↔ R 类型的双向映射，基于 JSON 作为中间格式。

**核心内容**：
- `PY_TO_R_TYPE` 字典：Python 类型 → R 类型字符串
- `RTypeMapper` 类：
  - `get_r_type(py_type)` - 获取对应 R 类型
  - `infer_r_types(args)` - 根据值推断 R 类型
  - `serialize_args(args, r_types)` - 将 Python 参数序列化为 JSON（用于传给 R）
  - `deserialize_result(result_json, ret_type)` - 将 R 返回的 JSON 反序列化为 Python 对象
- 支持的类型：`int`, `float`, `bool`, `str`, `list`, `dict`, `None`
- 列表/向量特殊处理：R 的向量是同类型的，Python list 转为 R vector

### 步骤 2：代码模板生成器 (templates.py)

**目标**：根据 Python 函数签名自动生成完整的 R 脚本代码。

**核心内容**：
- `RCodeGenerator` 类：
  - `generate_function_signature(func_name, params, return_type, code_body)` - 生成 R 函数
  - `generate_script_code(functions, input_data)` - 生成完整 R 脚本（含 JSON 读写）
  - `generate_from_python_func(func_name, sig, return_annotation, code_body, auto_signature)` - 从 Python 函数生成 R 代码
- R 脚本结构：
  ```r
  # 读取 JSON 输入
  input_data <- jsonlite::fromJSON(readLines("stdin", warn=FALSE))
  
  # 用户函数定义
  fib <- function(n) {
    # 用户提供的代码体
  }
  
  # 调用函数并输出 JSON 结果
  result <- do.call(fib, input_data$args)
  cat(jsonlite::toJSON(result, auto_unbox=TRUE))
  ```

### 步骤 3：R 执行引擎与装饰器 (compiler.py)

**目标**：实现通过 WSL 调用 Rscript 执行 R 代码，并提供 `@r` 装饰器。

**核心内容**：

1. **WSL 环境检测**：
   - `_check_wsl_available()` - 检查 WSL 是否可用
   - `_check_r_available()` - 检查 WSL 中 Rscript 是否可用
   - `_get_wsl_path(windows_path)` - Windows 路径 → WSL 路径转换

2. **R 执行器**：
   - `_run_r_script(r_code, args_dict, ret_type)` - 执行 R 脚本并返回结果
   - 实现方式：将 R 代码写入临时文件 → 通过 `wsl Rscript <script>` 执行 → 从 stdout 读取 JSON 结果
   - stdin 传参：将参数 JSON 通过 stdin 传给 R 脚本

3. **`@r` 装饰器**：
   - 支持 `@r` 和 `@r(mode='DEBUG')` 两种用法
   - 模式：
     - `NORMAL` - 缓存脚本，直接执行
     - `DEBUG` - 强制重新生成脚本并执行
     - `FORCE` - 只生成脚本不执行
     - `ONLY_RUN` - 只在有缓存时执行
     - `ONLY_CODE` - 只生成 R 代码，不执行
   - 支持 `auto_signature=True` 自动生成函数签名
   - 支持 `fallback` 回退函数
   - 支持 `async_mode` 异步执行

4. **便捷函数**：
   - `r_compiler_available()` - 检查 R 环境是否可用
   - `compile_and_run(r_code, func_name, args, ret_type)` - 直接编译运行
   - `compile_and_run_async(...)` - 异步版本

### 步骤 4：加载器模块 (loader.py)

**目标**：提供 R 环境可用性检查，对齐其他桥接的 loader API。

**核心内容**：
- `is_r_available()` - 检查 R 环境是否可用（WSL + Rscript）
- `get_r_version()` - 获取 R 版本信息

### 步骤 5：模块入口 (__init__.py)

**目标**：统一导出所有公共 API，对齐其他桥接模块的导出风格。

**导出内容**：
- 装饰器：`r`, `r_module`
- 类型映射：`RTypeMapper`, `get_r_type`, `infer_r_types`
- 执行器：`compile_and_run`, `compile_and_run_async`, `r_compiler_available`
- 加载器：`is_r_available`
- 代码生成：`RCodeGenerator`, `generate_from_python_func`

### 步骤 6：集成到桥接总入口 (__init__.py)

**目标**：在 `vools/bridge/__init__.py` 中添加 R 模块支持。

**修改内容**：
- 添加 `_r_loaded` 标志
- 添加 `_load_r()` 延迟加载函数
- 在 `__getattr__` 中添加 R 相关属性的处理
- 在 `__all__` 和 `__dir__` 中添加 `'r'`

### 步骤 7：测试文件 (test_r_bridge.py)

**目标**：验证 R 桥接功能的正确性。

**测试用例**：
1. 环境可用性测试：`test_r_available()`
2. 基本类型测试：`int`, `float`, `bool`, `str` 的双向传递
3. 斐波那契数列测试（递归函数）
4. 向量/列表运算测试
5. `@r` 装饰器测试
6. 各运行模式测试（ONLY_CODE, DEBUG 等）
7. 错误处理与 fallback 测试

---

## 4. 潜在依赖和注意事项

### 系统依赖
- **WSL 2**：Windows Subsystem for Linux（用户已确认 R 在 WSL 上安装）
- **R**：WSL 中已安装的 R 环境，包含 `Rscript` 命令
- **jsonlite**：R 包，用于 JSON 序列化/反序列化（R 自带或需安装）

### 技术考虑

1. **进程间通信开销**：
   - 每次调用都要启动 R 进程，有 ~100ms 级别的启动开销
   - 适合计算密集型任务，不适合高频小函数调用
   - 后续可以考虑 Rserve 或 OpenCPU 做长连接优化

2. **路径转换**：
   - Windows 路径与 WSL 路径的转换（`C:\` → `/mnt/c/`）
   - 临时文件需要放在两边都能访问的位置

3. **编码问题**：
   - stdin/stdout 的编码需要统一为 UTF-8
   - R 在 Windows 控制台的编码可能有问题，需要设置 `options(encoding="UTF-8")`

4. **jsonlite 依赖**：
   - 如果 WSL 中的 R 没有安装 jsonlite，需要提供备选方案（基础 R 的 rjson 或手动 JSON 拼接）
   - 可以在检测时检查 jsonlite 是否可用，不可用时提示用户安装

5. **错误处理**：
   - R 脚本的错误信息需要正确捕获并传递到 Python
   - stderr 输出需要收集并用于错误报告

6. **安全性**：
   - 执行任意 R 代码有安全风险，使用时需注意
   - 不对用户输入做沙箱限制（与 fbc.py 一致）

### 与 fbc.py 的对齐点

1. 装饰器使用方式一致：函数体返回目标语言代码字符串
2. 运行模式一致：DEBUG / FORCE / NORMAL / ONLY_RUN / ONLY_CODE
3. 自动签名生成一致：根据类型注解生成函数签名
4. 命名风格一致：`r` 对应 `fbc`，`r_compiler_available` 对应 `fbc_compiler_available`

### 与 vools.bridge 框架的对齐点

1. 目录结构一致：`__init__.py`, `types.py`, `compiler.py`, `loader.py`, `templates.py`
2. 导出风格一致：通过 `__all__` 明确导出
3. 延迟导入一致：在 `vools/bridge/__init__.py` 中通过 `__getattr__` 延迟加载
4. 可用性检查一致：`is_xxx_available()` 模式

---

## 5. 风险处理

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| WSL 路径转换出错 | 中 | 中 | 使用 `wslpath` 命令自动转换，或手动实现 `/mnt/c/` 映射 |
| R 进程启动慢 | 高 | 高 | 文档说明适用场景；可考虑后续实现 Rserve 长连接模式 |
| jsonlite 未安装 | 中 | 中 | 检测时检查 jsonlite，未安装则提示用户 `install.packages("jsonlite")` |
| 中文编码问题 | 中 | 中 | 统一使用 UTF-8，设置 `options(encoding="UTF-8")`，使用 `jsonlite` 处理 |
| 复杂数据类型传递失败 | 中 | 中 | 先支持基本类型，复杂类型通过 JSON 序列化，文档说明限制 |
| WSL 不可用（非 Windows 环境） | 低 | 低 | 检测平台，Linux 下直接调用 Rscript，macOS 同理 |
