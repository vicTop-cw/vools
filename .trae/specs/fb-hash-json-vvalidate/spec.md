# vools 集成计划 - 哈希算法、JSON解析器、验证模式库

## Overview
- **Summary**: 将 E:\vb\FileRecv 中的高价值 VB6/ASM 代码集成到 vools 架构中，包括 15 个汇编哈希算法、JSON 解析器、字符串构建器和验证模式库。
- **Purpose**: 提升 vools 的性能和功能完整性，通过 FreeBASIC 桥接实现原生级别的哈希计算和 JSON 处理能力。
- **Target Users**: vools 库用户，特别是需要高性能哈希计算、JSON 解析和数据验证的开发者。

## Goals
- 集成 15 个汇编哈希算法（MD2/4/5, SHA0/1/256/384/512, RIPEMD128/160/256/320, Tiger, Haval, Whirlpool）到 vools.crypto 模块
- 实现 FreeBASIC JSON 解析器封装，提供高性能 JSON 处理能力
- 提取验证模式库（邮箱、手机、身份证、车牌等）到 vools.data 模块
- 所有模块支持 @fbc 装饰器调用方式，与现有架构无缝集成

## Non-Goals (Out of Scope)
- 不集成 GDI+ 绘图模块（与现有 Cairo 模块重叠）
- 不集成 VLC 媒体库（非核心功能）
- 不集成 QQ 控件集（UI 控件，非核心功能）
- 不集成按键精灵、Hook 等系统级功能

## Background & Context
- vools 已有 `bridge/freebasic` 桥接框架，支持通过 @fbc 装饰器调用 FreeBASIC 代码
- E:\vb\FileRecv\hashes 包含 15 个高性能汇编哈希算法实现
- E:\vb\FileRecv\杂项\JSON.cls 是一个纯 VB6 JSON 解析器，逻辑清晰
- E:\vb\FileRecv\杂项\Vfx.cls 包含丰富的正则验证模式
- FreeBASIC 编译器已内置 md5.bi 头文件（compiler/expand/inc/inc/）

## Functional Requirements
- **FR-1**: 提供 15 个哈希算法的 Python 接口，通过 FreeBASIC 调用汇编实现
- **FR-2**: 提供 JSON 解析和序列化的 Python 接口，通过 FreeBASIC 实现
- **FR-3**: 提供常用数据验证模式（邮箱、手机、身份证等）的 Python 接口
- **FR-4**: 所有模块支持 @fbc 装饰器直接调用
- **FR-5**: 提供完整的单元测试和文档

## Non-Functional Requirements
- **NFR-1**: 哈希算法性能应优于 Python 标准库（hashlib）
- **NFR-2**: JSON 解析器支持常见的 JSON 数据类型（字符串、数字、数组、对象、布尔、null）
- **NFR-3**: 验证模式库支持自定义正则表达式扩展
- **NFR-4**: 支持 Windows x64 平台

## Constraints
- **Technical**: 基于现有 vools.bridge.freebasic 架构
- **Technical**: 汇编代码需通过 FreeBASIC 的 inline ASM 或编译为静态库
- **Dependencies**: FreeBASIC 编译器（fbc64.exe）

## Assumptions
- 用户已安装 vools 及其依赖
- FreeBASIC 编译器可正确编译汇编代码
- 汇编代码为 32 位，需适配 64 位或使用 32 位编译器

## Acceptance Criteria

### AC-1: 哈希算法模块可用
- **Given**: 用户导入 vools.crypto.hash 模块
- **When**: 调用 md5("test"), sha256("test") 等函数
- **Then**: 返回正确的哈希值（与 Python hashlib 结果一致）
- **Verification**: `programmatic`

### AC-2: JSON 解析器可用
- **Given**: 用户导入 vools.data.json 模块
- **When**: 调用 json.parse('{"key": "value"}') 和 json.stringify({"key": "value"})
- **Then**: 返回正确的解析结果和序列化字符串
- **Verification**: `programmatic`

### AC-3: 验证模式库可用
- **Given**: 用户导入 vools.data.vvalidate 模块
- **When**: 调用 vvalidate.is_email("test@example.com"), vvalidate.is_mobile("13800138000")
- **Then**: 返回正确的布尔值
- **Verification**: `programmatic`

### AC-4: @fbc 装饰器支持
- **Given**: 用户使用 @fbc 装饰器并引入 hash_wrapper.bas
- **When**: 在 FreeBASIC 代码中调用 fb_hash_md5()
- **Then**: 代码编译成功并返回正确结果
- **Verification**: `programmatic`

### AC-5: 性能测试通过
- **Given**: 测试环境已准备
- **When**: 对比 vools.crypto.hash 与 Python hashlib 的性能
- **Then**: vools 实现应达到 hashlib 性能的 80% 以上
- **Verification**: `programmatic`

## Open Questions
- [ ] 汇编代码是否需要适配 64 位？目前 hashes/ 目录下的代码是 32 位 ASM
- [ ] 是否需要支持 JSON 嵌套对象和数组的深度解析？
