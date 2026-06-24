# vools Bridge - 跨语言桥接子包 PRD

## Overview
- **Summary**: 新增 `vools.bridge` 子包，提供统一的 Python 到其他语言的桥接框架，支持自动检测、加载和回退机制
- **Purpose**: 为用户提供简洁的装饰器 API，轻松利用其他语言（如 Nim、Mojo、Rust）的高性能实现，同时保持 Python 的易用性和兼容性
- **Target Users**: vools 库开发者、需要高性能计算的 Python 用户、希望复用其他语言代码的开发者

## Goals
- 设计统一的桥接架构，支持多种语言扩展
- 实现 Nim 桥接模块（利用现有实现）
- 提供简洁的装饰器 API：`@bridge_function`、`@bridge_module`
- 支持自动检测和透明回退到 Python 实现
- 提供统一的数据序列化层

## Non-Goals (Out of Scope)
- 实现 Mojo、Rust、C、C++、C# 等桥接模块（仅规划架构）
- 实现 Cangjie、Freebaic 等特定语言桥接
- 提供编译工具链（仅提供运行时加载）

## Background & Context
- 当前已有 Nim 桥接实现，但分散在多个文件中：`_nim_loader.py`、`_nim_crypto.py`、`_nim_seq.py` 等
- 每个模块有重复的加载逻辑和 CSV 序列化代码
- 需要统一架构以便未来扩展其他语言

## Functional Requirements
- **FR-1**: 提供 `@bridge_function` 装饰器，自动选择底层实现
- **FR-2**: 提供 `@bridge_module` 装饰器，批量管理一组桥接函数
- **FR-3**: 提供统一的共享库加载器，支持跨平台（Windows/Linux）
- **FR-4**: 提供统一的数据序列化层（CSV、JSON 等格式）
- **FR-5**: 实现 Nim 桥接子模块，包含 crypto、seq、datetime、curried、encoding
- **FR-6**: 提供 `is_available(language)` API 查询语言桥接可用性

## Non-Functional Requirements
- **NFR-1**: 性能开销最小化，装饰器不应显著影响调用性能
- **NFR-2**: 线程安全，支持多线程环境下的库加载
- **NFR-3**: 异常处理友好，桥接失败时提供清晰的错误信息
- **NFR-4**: 与现有 vools 模块完全兼容

## Constraints
- **Technical**: Python 3.6+，ctypes 标准库
- **Dependencies**: 依赖系统上安装的共享库（.dll/.so）
- **Platform**: Windows (x64), Linux (x64/WSL)

## Assumptions
- 用户已安装对应语言的工具链并编译了共享库
- 共享库遵循 vools 的命名约定和导出规范

## Acceptance Criteria

### AC-1: @bridge_function 装饰器
- **Given**: 用户定义了带 `@bridge_function("nim", fallback=_py_impl)` 的函数
- **When**: 调用该函数时
- **Then**: 如果 Nim 库可用，自动调用 Nim 实现；否则调用 Python fallback
- **Verification**: `programmatic`

### AC-2: @bridge_module 装饰器
- **Given**: 用户定义了带 `@bridge_module("nim")` 的类
- **When**: 访问类的方法时
- **Then**: 类的所有方法自动使用对应语言的实现（如果可用）
- **Verification**: `programmatic`

### AC-3: 统一加载器
- **Given**: 调用 `load_library("nim", "vools_crypto")`
- **When**: 在 Windows 或 Linux 环境下
- **Then**: 正确加载对应的 .dll 或 .so 文件
- **Verification**: `programmatic`

### AC-4: Nim 桥接模块
- **Given**: Nim 库已编译并放置在正确位置
- **When**: 导入 `vools.bridge.nim`
- **Then**: 所有功能（crypto、seq、datetime、curried、encoding）正常工作
- **Verification**: `programmatic`

### AC-5: 回退机制
- **Given**: 删除或移动 Nim 共享库
- **When**: 调用桥接函数
- **Then**: 自动回退到 Python 实现，不抛出异常
- **Verification**: `programmatic`

### AC-6: is_available API
- **Given**: 调用 `is_available("nim")`
- **When**: Nim 库存在或不存在
- **Then**: 返回正确的布尔值
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要支持异步桥接调用？
- [ ] 是否需要提供编译工具（如 `vools bridge build` CLI）？
- [ ] 是否需要支持自定义序列化格式？
