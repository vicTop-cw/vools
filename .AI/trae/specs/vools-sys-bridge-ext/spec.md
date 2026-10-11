# vools.sys 与 LangBridge 扩展 - Product Requirement Document

## Overview
- **Summary**: 扩展 vools 框架的系统集成能力，新增 @exe 和 @dll 两个装饰器用于外部程序和库调用，并扩展 LangBridge 支持 only_code 模式（代码生成但不编译）和 project 模式（编译整个项目）。
- **Purpose**: 提供更灵活的外部系统集成方式，覆盖"调用外部程序"、"调用外部 DLL"、"仅生成代码"、"编译整个项目"四种场景，与现有的编译调用模式形成完整的工具链。
- **Target Users**: 使用 vools 框架进行跨语言开发和系统集成的开发者。

## Goals
- 新增 @exe 装饰器：通过函数签名参数映射调用外部可执行文件
- 新增 @dll 装饰器：通过函数签名参数映射调用外部 DLL/共享库
- 扩展 LangBridge 支持 only_code 模式：生成目标语言代码写入文件，不编译
- 扩展 LangBridge 支持 project 模式：编译整个项目目录，生成 exe 或 dll
- 所有新功能均支持同步/异步双模式
- 代码组织：@exe 和 @dll 放在 vools.sys 子包

## Non-Goals (Out of Scope)
- 不修改现有 LangBridge 的编译调用模式（保持向后兼容）
- 不实现跨语言类型的复杂序列化（仅支持基础类型自动映射）
- 不实现 GUI 程序交互（仅支持命令行程序）
- 不实现 DLL 函数的自动发现（需显式指定函数名）

## Background & Context
当前 vools.bridge 模块提供了 7 种编译型语言的统一桥接接口，核心流程是 "Python 函数体→生成目标代码→编译→调用"。但缺少以下场景的支持：

1. **调用已有外部程序**：有时只需要调用现成的 .exe 文件，不需要编译
2. **调用已有外部 DLL**：有时只需要调用现成的 DLL，不需要编译
3. **仅生成代码**：有时只需要生成目标语言代码文件，不需要 vools 来编译
4. **编译整个项目**：当项目有多个源文件、复杂构建配置时，单文件编译不够用

本次扩展就是为了补齐这四块能力。

## Functional Requirements

### FR-1: @exe 装饰器
- 装饰器接收可执行文件路径作为参数
- 函数参数映射为命令行参数
  - 单下划线前缀 `_f` → 短选项 `-f value`
  - 双下划线前缀 `__path` → 长选项 `--path value`
  - 值为 None 的参数 → 仅选项无值（如 `_m=None` → `-m`）
  - 无特殊前缀的位置参数 → 按顺序追加到命令末尾
- 支持异步模式 `async_mode=True`
- 返回值为 `(returncode: int, stdout: str, stderr: str)` 元组
- 函数体可以为 pass，装饰器自动构建命令并执行
- 无参命令支持无参函数签名

### FR-2: @dll 装饰器
- 装饰器接收 DLL 路径和函数名，格式 `"path/to/dll::{func_name}"`
- 函数参数自动映射为 DLL 函数参数
- 根据 Python 类型注解自动映射 ctypes 类型
  - `int` → `c_int`
  - `float` → `c_double`
  - `str` → `c_char_p`（自动编码）
  - `bytes` → `c_char_p`
  - `bool` → `c_bool`
- 返回值类型根据返回注解自动映射
- 函数体可以为 pass，装饰器自动加载 DLL 并调用
- 无参函数支持无参签名

### FR-3: LangBridge only_code 模式
- 装饰器参数 `only_code=True` 启用此模式
- 装饰器参数 `output_file` 指定输出文件路径（含扩展名）
- 函数必须返回目标语言代码字符串
- 支持多种写入模式（`write_mode` 参数）：
  - `'overwrite'`: 覆盖整个文件
  - `'append'`: 追加到文件末尾
  - `'insert:NN'`: 插入到第 NN 行之后
  - `'replace:MM-NN'`: 替换第 MM 到 NN 行
- 支持 `prefix` 和 `suffix` 关键字参数，为生成的代码添加前缀和后缀
- 不调用编译器，仅处理代码写入
- 支持 deps 和 module_code（与现有模式一致）

### FR-4: LangBridge project 模式
- 装饰器参数 `project_dir` 指定项目目录路径
- 装饰器参数 `entry` 指定入口函数名
- 自动判断产物类型：
  - 入口为 `main` 且输出 exe → 可执行文件
  - 其他入口 → 共享库（dll/so）
- 调用各语言自己的项目编译流程完成构建
- 构建产物路径可通过装饰器返回的函数属性获取
- 支持缓存机制（基于项目文件哈希）
- 支持异步模式

### FR-5: vools.sys 子包组织
- `vools/sys/exe.py`: @exe 装饰器实现
- `vools/sys/dll.py`: @dll 装饰器实现
- `vools/sys/__init__.py`: 统一导出
- 不破坏现有 sys 子包的 CLI 功能

## Non-Functional Requirements
- **NFR-1**: 向后兼容 - 现有 LangBridge 使用方式不受任何影响
- **NFR-2**: 接口一致性 - @exe 和 @dll 的装饰器风格与 LangBridge 保持一致（支持 async_mode、fallback 等）
- **NFR-3**: 错误处理 - 外部程序/DLL 调用失败时有清晰的错误信息
- **NFR-4**: 类型安全 - DLL 调用时类型不匹配有明确报错

## Constraints
- **Technical**: 基于 Python 3.8+，使用 ctypes 进行 DLL 调用，使用 subprocess 进行外部程序调用
- **Platform**: Windows / Linux / macOS 跨平台支持（路径分隔符、可执行文件扩展名差异）
- **Dependencies**: 仅依赖标准库，不引入新的第三方依赖

## Assumptions
- 用户提供的 DLL 导出函数使用 C 调用约定（cdecl/stdcall 视平台而定）
- 外部可执行文件为命令行程序，通过标准输入输出交互
- only_code 模式下用户保证输出文件路径的可写性
- project 模式下项目目录结构符合对应语言的标准项目结构

## Acceptance Criteria

### AC-1: @exe 基本调用
- **Given**: 一个可执行文件 `echo.exe` 存在
- **When**: 使用 `@exe("echo.exe")` 装饰函数，调用时传参
- **Then**: 进程被正确调用，返回 (returncode, stdout, stderr) 元组
- **Verification**: `programmatic`

### AC-2: @exe 参数映射
- **Given**: @exe 装饰的函数有 `_f`, `__path`, `_m=None` 等参数
- **When**: 调用函数并传入对应值
- **Then**: 命令行参数正确映射为 `-f value --path value -m`
- **Verification**: `programmatic`

### AC-3: @exe 异步模式
- **Given**: @exe 装饰器设置 `async_mode=True`
- **When**: await 调用被装饰函数
- **Then**: 异步执行，不阻塞主线程
- **Verification**: `programmatic`

### AC-4: @dll 基本调用
- **Given**: 一个包含导出函数的 DLL 文件存在
- **When**: 使用 `@dll("mydll.dll::add")` 装饰带类型注解的函数并调用
- **Then**: DLL 函数被正确调用，返回值正确
- **Verification**: `programmatic`

### AC-5: @dll 类型自动映射
- **Given**: 函数参数有 int/float/str/bytes/bool 类型注解
- **When**: 调用 @dll 装饰的函数
- **Then**: 参数自动转换为对应 ctypes 类型传入 DLL
- **Verification**: `programmatic`

### AC-6: only_code 覆盖写入
- **Given**: LangBridge 装饰器设置 `only_code=True, output_file="out.bas"`
- **When**: 调用被装饰函数，函数返回代码字符串
- **Then**: 代码被写入指定文件，覆盖原有内容
- **Verification**: `programmatic`

### AC-7: only_code 多种写入模式
- **Given**: 设置 `write_mode='append'` 或 `'insert:10'` 或 `'replace:5-10'`
- **When**: 调用被装饰函数
- **Then**: 代码按对应模式写入文件
- **Verification**: `programmatic`

### AC-8: only_code prefix/suffix
- **Given**: 设置 `prefix="..."` 和 `suffix="..."` 参数
- **When**: 生成代码并写入
- **Then**: 写入的代码包含前缀和后缀
- **Verification**: `programmatic`

### AC-9: project 模式编译
- **Given**: 一个符合语言规范的项目目录，设置 `project_dir="./proj", entry="main"`
- **When**: 调用被装饰函数
- **Then**: 项目被编译，生成对应产物（exe 或 dll）
- **Verification**: `programmatic`

### AC-10: 向后兼容
- **Given**: 现有使用 LangBridge 的代码
- **When**: 不修改任何代码直接运行
- **Then**: 所有现有功能正常工作，行为不变
- **Verification**: `programmatic`

## Open Questions
- [ ] project 模式下，被装饰函数的调用语义是什么？（调用=触发编译？还是调用=运行 exe/调用 dll 函数？）
- [ ] @exe 装饰器是否需要支持 stdin 输入？
- [ ] @dll 装饰器是否需要支持结构体/指针等复杂类型？
