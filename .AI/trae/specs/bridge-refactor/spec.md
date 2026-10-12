# 桥接子包核心重构 Spec

## Why
当前桥接子包存在以下问题：1) 编译模式用字符串常量，各语言实现不一致（有的用 `mode`，有的用 `only_code=True`）；2) 缓存仅靠文件系统判断是否存在，无法感知代码变更；3) 核心抽象未覆盖解释性语言；4) 继承 `LangBridge` 与独立实现装饰器混用。需要统一重构核心抽象，新增代码变更感知的编译模式，并确保所有语言统一。

## What Changes
- 新增 `CompileMode` 枚举，替代字符串常量（**BREAKING**）
- 新增 `WHEN_CHANGE_JUST` 和 `WHEN_CHANGE_AND_RUN` 编译模式，基于 SQLite + MD5 追踪代码变更
- 新增 `CompileTracker` 类，管理编译记录 SQLite 数据库
- 重新设计 `LangBridge` 核心抽象，确保编译型与解释型语言均适用
- 所有语言装饰器统一使用 `mode` 参数，移除独立的 `only_code` 参数（**BREAKING**）
- 各语言原有实现的方法改为私有，通过核心抽象公开暴露
- 更新所有测试代码，确保通过
- 更新各语言文档和注解

## Impact
- Affected specs: bridge-subpackage
- Affected code: `vools/bridge/_base.py`, `vools/bridge/manager.py`, 所有语言桥接的 `compiler.py` 和 `__init__.py`，所有 `tests/bridge/` 测试

## ADDED Requirements

### Requirement: CompileMode 枚举
系统 SHALL 提供 `CompileMode` 枚举，定义所有编译执行模式。

#### Scenario: 使用枚举指定模式
- **WHEN** 用户调用 `@nim(mode=CompileMode.DEBUG)` 
- **THEN** 装饰器强制重新编译并执行

#### Scenario: 枚举成员
- **WHEN** 查看 `CompileMode` 枚举
- **THEN** 包含以下成员：`NORMAL`、`DEBUG`、`FORCE`、`ONLY_RUN`、`ONLY_CODE`、`WHEN_CHANGE_JUST`、`WHEN_CHANGE_AND_RUN`

### Requirement: CompileTracker SQLite 编译记录
系统 SHALL 提供 `CompileTracker` 类，使用专用 SQLite 数据库（位于 vools 桥接数据目录）管理编译记录。数据库设计为可扩展，未来可增加语言注册表、编译错误日志等表。

#### Scenario: 数据库位置
- **WHEN** 初始化 `CompileTracker`
- **THEN** 数据库文件创建在 `{vools_data_dir}/bridge_records.db`（跨平台统一路径，Windows 为 `%LOCALAPPDATA%/vools/`，Linux/macOS 为 `~/.local/share/vools/`）

#### Scenario: 首次编译记录
- **WHEN** 首次编译某段代码
- **THEN** 在 `compile_records` 表中插入记录，包含：`record_key`、`language`、`lang_type`、`func_name`、`source_md5`、`lib_path`、`source_path`、`compile_mode`、`compiled_at`、`python_module`、`python_file`

#### Scenario: record_key 生成规则
- **WHEN** 装饰器包装函数时
- **THEN** `record_key` 由 `{调用方Python模块路径}:{被装饰函数限定名}` 组成
- **示例**：`mypackage.utils.math:add_numbers` 或 `mypackage.service:MathHelper.compute`

#### Scenario: 代码变更检测
- **WHEN** 使用 `WHEN_CHANGE_JUST` 或 `WHEN_CHANGE_AND_RUN` 模式
- **THEN** 通过 `record_key` 查询数据库，对比当前代码 MD5 与记录中的 `source_md5`，MD5 不同或不存在记录时触发编译

#### Scenario: 主表结构 (`compile_records`)
- **WHEN** 初始化 `CompileTracker`
- **THEN** 创建 `compile_records` 表，字段如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `record_key` | TEXT UNIQUE | 唯一标识：`{module}:{qualname}` |
| `language` | TEXT | 语言名称（nim/rust/lua/...） |
| `lang_type` | TEXT | 语言类型（compiled/interpreted/jvm/dotnet/beam） |
| `func_name` | TEXT | 被装饰函数名 |
| `source_md5` | TEXT | 源码 MD5 哈希 |
| `source_path` | TEXT | 生成的源文件路径 |
| `lib_path` | TEXT | 编译产物路径（dll/jar/zip） |
| `compile_mode` | TEXT | 编译模式 |
| `compiled_at` | TEXT | ISO 时间戳 |
| `compile_duration_ms` | INTEGER | 编译耗时（毫秒） |
| `python_module` | TEXT | 调用方 Python 模块名 |
| `python_file` | TEXT | 调用方 Python 文件路径 |
| `extra` | TEXT | JSON 扩展字段 |

#### Scenario: 预留扩展表 (`language_registry`)
- **WHEN** 初始化 `CompileTracker`
- **THEN** 预留创建 `language_registry` 表（记录各语言编译器路径、版本、可用状态），当前为空表

#### Scenario: 预留扩展表 (`compile_errors`)
- **WHEN** 初始化 `CompileTracker`
- **THEN** 预留创建 `compile_errors` 表（记录编译失败的错误信息），通过 `record_key` 关联 `compile_records`

### Requirement: 核心抽象覆盖解释性语言
系统 SHALL 确保 `LangBridge` 核心抽象适用于编译型语言和解释型语言。

#### Scenario: 解释性语言 "编译" 为包
- **WHEN** 解释性语言（如 Python/Shell）使用 `compile_code()` 方法
- **THEN** 将源代码打包为平台相关的压缩格式（如 `.zip`、`.tar.gz`），作为"编译产物"

#### Scenario: 解释性语言 "调用" 函数
- **WHEN** 解释性语言调用 `call_func()` 方法
- **THEN** 解包编译产物，通过解释器执行目标代码

### Requirement: 统一装饰器参数
所有语言装饰器 SHALL 统一使用 `mode` 参数，移除独立的 `only_code` 参数。

#### Scenario: 仅代码模式
- **WHEN** 用户指定 `mode=CompileMode.ONLY_CODE`
- **THEN** 仅生成目标语言代码，不编译不执行

### Requirement: 原有实现包装
各语言桥接的原有公开方法 SHALL 改为私有，通过核心抽象公开类和方法暴露。

#### Scenario: Nim 桥接
- **WHEN** 查看 Nim 桥接的公开 API
- **THEN** 公开类继承自 `LangBridge`，内部委托给原 `NimCompiler` 私有方法

## MODIFIED Requirements

### Requirement: `LangBridge` 核心抽象增强
原 `LangBridge` 抽象基类 SHALL 增强以下能力：
- 新增 `CompileMode` 枚举支持，`decorator` 方法接受枚举或字符串
- 新增 `_compile_tracker` 属性，管理编译记录
- 新增 `_should_compile(mode, code, func_name)` 方法，根据模式和代码变更决定是否编译
- 新增 `is_compiled` 属性，标识语言是否需要编译（编译型 True / 解释型 False）
- `compile_code` 返回 `CompileResult` 数据类而非裸字符串

## REMOVED Requirements
### Requirement: `only_code` 参数
**Reason**: 与 `mode` 参数重复，由 `CompileMode.ONLY_CODE` 替代
**Migration**: 将 `only_code=True` 改为 `mode=CompileMode.ONLY_CODE`

## 兼容性
- 破坏性 API 变更：是（v0.6.0 大版本）
- Python 3.6+
- 不影响非桥接模块