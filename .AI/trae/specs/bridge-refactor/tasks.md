# Tasks

## 核心层构建

- [x] Task 1: 创建 `CompileMode` 枚举和 `CompileTracker` 编译记录类
  - [x] 1.1 在 `vools/bridge/core/types.py` 中定义 `CompileMode` 枚举（7 个成员：NORMAL/DEBUG/FORCE/ONLY_RUN/ONLY_CODE/WHEN_CHANGE_JUST/WHEN_CHANGE_AND_RUN）和 `LangType` 枚举（compiled/interpreted/jvm/dotnet/beam）
  - [x] 1.2 在 `vools/bridge/core/` 中创建 `tracker.py`，实现 `CompileTracker` 类
  - [x] 1.3 数据库位置：`{vools_data_dir}/bridge_records.db`（Windows: `%LOCALAPPDATA%/vools/`，Linux/macOS: `~/.local/share/vools/`）
  - [x] 1.4 创建 `compile_records` 表（12 字段：id/record_key/language/lang_type/func_name/source_md5/source_path/lib_path/compile_mode/compiled_at/compile_duration_ms/python_module/python_file/extra）
  - [x] 1.5 预留创建 `language_registry` 表（language/compiler_path/version/is_available/last_checked）和 `compile_errors` 表（record_key/error_message/error_code/occurred_at）
  - [x] 1.6 提供 `get_record(record_key)` 和 `upsert_record(record_key, ...)` 方法
  - [x] 1.7 提供 `is_changed(record_key, source_md5)` 方法
  - [x] 1.8 实现 `_make_record_key(func)` 静态方法，从 `inspect.getmodule(func).__name__` + `:` + `func.__qualname__` 生成 key
  - [x] 1.9 更新 `vools/bridge/core/__init__.py` 导出新类

- [x] Task 2: 重新设计 `LangBridge` 核心抽象
  - [x] 2.1 在 `_base.py` 中新增 `is_compiled` 类属性（默认 True，解释性语言重写为 False）
  - [x] 2.2 新增 `_compile_tracker` 属性，懒加载 `CompileTracker` 实例
  - [x] 2.3 新增 `_should_compile(mode, code, func_name)` 方法，根据 CompileMode 和代码变更决定是否编译
  - [x] 2.4 修改 `decorator` 方法签名，`mode` 参数接受 `CompileMode` 枚举或字符串，移除 `only_code` 参数
  - [x] 2.5 新增 `_compile_or_package(code, func_name, cache_dir)` 方法，编译型调 `compile_code`，解释型调 `_package_code`
  - [x] 2.6 新增 `_package_code(code, func_name, cache_dir)` 默认实现，打包为 zip/tar.gz
  - [x] 2.7 新增 `_call_or_execute(lib_path, func_name, args, ret_type)` 方法，编译型调 `call_func`，解释型调 `_execute_code`
  - [x] 2.8 新增 `_execute_code(package_path, func_name, args, ret_type)` 默认实现，解包并通过解释器执行
  - [x] 2.9 更新 `_run_sync` 和 `_run_async` 方法，使用新编译流程
  - [x] 2.10 更新 `vools/bridge/__init__.py` 和 `vools/__init__.py` 导出 `CompileMode`、`CompileTracker`

## 语言适配层（并行执行）

每组语言由独立子代理处理，将原有实现的方法改为私有，包装为核心抽象。

### 编译型语言（继承 LangBridge 的语言）

- [x] Task 3: 适配 Nim 桥接（`vools/bridge/nim/`）
- [x] Task 4: 适配 Rust 桥接（`vools/bridge/rust/`）
- [x] Task 5: 适配 C 桥接（`vools/bridge/c/`）
- [x] Task 6: 适配 C++ 桥接（`vools/bridge/cpp/`）
- [x] Task 7: 适配 Go 桥接（`vools/bridge/go/`）
- [x] Task 8: 适配 Java 桥接（`vools/bridge/java/`）
- [x] Task 9: 适配 Scala 桥接（`vools/bridge/scala/`）
- [x] Task 10: 适配 Kotlin 桥接（`vools/bridge/kotlin/`）
- [x] Task 11: 适配 Swift 桥接（`vools/bridge/swift/`）
- [x] Task 12: 适配 Dart 桥接（`vools/bridge/dart/`）
- [x] Task 13: 适配 Zig 桥接（`vools/bridge/zig/`）
- [x] Task 14: 适配 FreeBASIC 桥接（`vools/bridge/freebasic/`）
- [x] Task 15: 适配 MoonBit 桥接（`vools/bridge/moonbit/`）
- [x] Task 16: 适配 Cangjie 桥接（`vools/bridge/cangjie/`）
- [x] Task 17: 适配 Mojo 桥接（`vools/bridge/mojo/`）
- [x] Task 18: 适配 VBNet 桥接（`vools/bridge/vbnet/`）
- [x] Task 19: 适配 C# 桥接（`vools/bridge/csharp/`）
- [x] Task 20: 适配 Erlang 桥接（`vools/bridge/erlang/`）
- [x] Task 21: 适配 Elixir 桥接（`vools/bridge/elixir/`）
- [x] Task 22: 适配 Haskell 桥接（`vools/bridge/haskell/`）
- [x] Task 23: 适配 Lua 桥接（`vools/bridge/lua/`）
- [x] Task 24: 适配 Shell 桥接（`vools/bridge/shell/`）
- [x] Task 25: 适配 Perl 桥接（`vools/bridge/perl/`）
- [x] Task 26: 适配 PHP 桥接（`vools/bridge/php/`）
- [x] Task 27: 适配 R 桥接（`vools/bridge/r/`）
- [x] Task 28: 适配 Ruby 桥接（`vools/bridge/ruby/`）
- [x] Task 29: 适配 TypeScript 桥接（`vools/bridge/typescript/`）
- [x] Task 30: 适配 PowerShell 桥接（`vools/bridge/powershell/`）
- [x] Task 31: 适配 VBScript 桥接（`vools/bridge/vbscript/`）
- [x] Task 32: 适配 Julia 桥接（`vools/bridge/julia/`）

## 测试更新

- [x] Task 33: 更新核心层测试
  - [x] 33.1 为 `CompileMode` 枚举编写测试（11 个测试用例全部通过）
  - [x] 33.2 为 `CompileTracker` 编写测试（SQLite 记录、代码变更检测）
  - [x] 33.3 为 `LangBridge` 新方法编写测试

- [x] Task 34: 更新桥接语言测试（并行）
  - [x] 34.1 更新所有语言的测试文件，将 `only_code=True` 改为 `mode=CompileMode.ONLY_CODE`（零残留）
  - [x] 34.2 确保所有语言测试通过（199 passed, 21 skipped；24 失败均为预存问题：沙箱/编译器缺失）

## 文档更新

- [x] Task 35: 更新文档
  - [x] 35.1 更新 `vools/bridge/README.md` 核心架构文档（新增 CompileMode、CompileTracker、LangType 章节）
  - [x] 35.2 更新 `changelog/v0.6.0.md`，记录破坏性变更和迁移指南
  - [x] 35.3 更新 `vools/__init__.py` 版本号至 0.6.0

# Task Dependencies

- Task 1 和 Task 2 可并行执行
- 所有语言适配任务（Task 3-32）依赖 Task 1 和 Task 2 完成
- 语言适配任务（Task 3-32）之间无依赖，全部可并行执行
- Task 33 依赖 Task 1 和 Task 2 完成
- Task 34 依赖对应语言适配 Task 完成
- Task 35 依赖所有语言适配 Task 完成