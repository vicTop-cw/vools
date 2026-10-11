# VB6 文件集成计划 - Product Requirement Document

## Overview
- **Summary**: 将 E:\vb\FileRecv 目录下的 VB6 代码资产整合到 vools 架构中，包括正则验证模式库、JSON 解析器、剪贴板管理和 Windows 消息钩子功能。
- **Purpose**: 复用 VB6 代码中的实用功能，增强 vools 的数据验证、序列化、系统监控能力。
- **Target Users**: vools 库用户，需要数据验证、JSON 处理、系统监控功能的开发者。

## Goals
- 将 Vfx.cls 中的正则验证模式整合到 vools.data 模块，提供邮箱、手机、身份证、车牌等常用验证
- 将 JSON.cls 的 JSON 解析逻辑整合到 vools.serialize 模块，增强序列化能力
- 将 cClip.cls 的剪贴板管理功能整合到 vools.reactive.monitoring 模块
- 将 cSubclass.cls 的 Windows 消息钩子功能整合到 vools.reactive.monitoring 模块
- 所有集成功能需通过单元测试，支持 Python 3.6+

## Non-Goals (Out of Scope)
- 不整合 Vdt.cls 的数据库操作功能（依赖 ADODB，平台限制大）
- 不整合 Cnr.cls 的控件构造器（依赖 VB6 运行时）
- 不整合 Vfx.cls 中的颜色常量（已有 Python 标准库支持）
- 不整合 Vfx.cls 中的 DLL 调用功能（依赖 VB6Plus.dll）

## Background & Context
- vools 已有完整的数据模块（vools.data）、序列化模块（vools.serialize）和监控模块（vools.reactive.monitoring）
- E:\vb\FileRecv\杂项\vb6Dll+\Vfx.cls 包含丰富的正则验证模式和字符串工具函数
- E:\vb\FileRecv\VB6谷歌翻译\JSON.cls 包含完整的 JSON 解析器实现
- E:\vb\FileRecv\杂项\cClip.cls 包含剪贴板管理功能
- E:\vb\FileRecv\杂项\cSubclass.cls 包含 Windows 消息钩子实现

## Functional Requirements
- **FR-1**: 提供常用数据验证函数（邮箱、手机、身份证、车牌、URL、用户名、密码等）
- **FR-2**: 提供字符串工具函数（全中文判断、包含中文判断、是否以...开头/结尾等）
- **FR-3**: 提供 JSON 解析和序列化功能（兼容现有 serialize 模块）
- **FR-4**: 提供剪贴板监控和内容保存功能
- **FR-5**: 提供 Windows 窗口消息钩子功能（监控窗口消息）

## Non-Functional Requirements
- **NFR-1**: 支持 Python 3.6+（含 Python 3.13）
- **NFR-2**: 所有功能需有单元测试覆盖
- **NFR-3**: 遵循 vools 现有代码风格和架构约定
- **NFR-4**: 使用相对导入，避免循环依赖

## Constraints
- **Technical**: Python 3.6 兼容性（无 dataclasses、无 f-string 等）
- **Platform**: cClip 和 cSubclass 功能仅支持 Windows
- **Dependencies**: 不引入新的第三方依赖

## Assumptions
- 正则验证模式已在 VB6 中经过验证，可直接移植到 Python
- JSON 解析器逻辑可直接转换为 Python 实现
- Windows 消息钩子功能需要使用 ctypes 调用 Win32 API

## Acceptance Criteria

### AC-1: 正则验证模式库整合完成
- **Given**: vools.data 模块已存在
- **When**: 用户调用验证函数如 is_email(), is_mobile(), is_id_card()
- **Then**: 返回正确的布尔值，验证规则符合预期
- **Verification**: `programmatic`

### AC-2: 字符串工具函数整合完成
- **Given**: vools.data.VText 类已存在
- **When**: 用户调用 is_all_chinese(), contains_chinese(), starts_with(), ends_with() 等方法
- **Then**: 返回正确的结果
- **Verification**: `programmatic`

### AC-3: JSON 解析器整合完成
- **Given**: vools.serialize 模块已存在
- **When**: 用户调用 JSON 解析和序列化功能
- **Then**: 正确处理 JSON 数据，与标准库结果一致
- **Verification**: `programmatic`

### AC-4: 剪贴板管理功能整合完成
- **Given**: vools.reactive.monitoring 模块已存在
- **When**: 用户监控剪贴板并保存内容
- **Then**: 正确捕获剪贴板变化并保存到文件
- **Verification**: `programmatic`（Windows 平台）

### AC-5: Windows 消息钩子功能整合完成
- **Given**: vools.reactive.monitoring 模块已存在
- **When**: 用户设置窗口消息钩子
- **Then**: 正确捕获指定窗口的消息
- **Verification**: `programmatic`（Windows 平台）

## Open Questions
- [ ] 是否需要为验证模式库创建独立的 vools.validation 子包？
- [ ] JSON 解析器是否需要替换现有实现还是作为补充？
- [ ] Windows 消息钩子是否需要支持全局钩子还是仅窗口级钩子？
