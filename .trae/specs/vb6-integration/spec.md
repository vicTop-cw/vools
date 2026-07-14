# VB6 代码资产集成计划 - Product Requirement Document

## Overview
- **Summary**: 将 E:\vb\FileRecv 目录下的 VB6 代码资产整合到 vools 架构中，包括正则验证模式库、JSON 解析器、剪贴板管理和 Windows 消息钩子功能。
- **Purpose**: 复用现有的 VB6 代码资产，扩展 vools 库的功能，提升代码复用性和开发效率。
- **Target Users**: vools 库的开发者和使用者。

## Goals
- [x] 完成验证模式库模块 (validator.py)
- [x] 完成 JSON 解析器整合到 serialize 模块
- [x] 完成剪贴板保存功能整合到 ClipSubject
- [ ] 完成 Windows 消息钩子功能整合
- [ ] 所有集成功能通过单元测试
- [ ] 确保 Python 3.6+ 兼容性

## Non-Goals (Out of Scope)
- 不引入新的第三方依赖
- 不修改 vools 现有架构设计
- 不实现 VB6 GUI 控件移植
- 不处理 VB6 COM/DLL 直接调用

## Background & Context
- VB6 代码资产位于 E:\vb\FileRecv 目录，包含多个功能模块
- vools 是一个多语言互操作框架，支持多种编程语言的桥接
- 已有基础：验证模块、JSON 模块、剪贴板监控模块已存在
- 需要从 VB6 cClip.cls 和 gModule.bas 提取剪贴板保存功能

## Functional Requirements
- **FR-1**: 实现验证模式库，包含邮箱、手机、身份证、车牌等常用正则验证
- **FR-2**: 实现 JSON 解析器，支持注释忽略、单引号字符串等特性
- **FR-3**: 实现剪贴板保存功能，支持文本、图片、文件列表的保存
- **FR-4**: 实现 Windows 消息钩子功能，支持热键注册和系统消息监听
- **FR-5**: 所有功能通过单元测试验证

## Non-Functional Requirements
- **NFR-1**: 支持 Python 3.6+
- **NFR-2**: 遵循 vools 现有代码风格和架构约定
- **NFR-3**: 不引入新的第三方依赖
- **NFR-4**: 跨平台兼容性（Windows 特有功能提供兼容方案）

## Constraints
- **Technical**: Python 3.6+，仅使用标准库
- **Business**: 保持与现有 vools 架构的一致性
- **Dependencies**: 无新增第三方依赖

## Assumptions
- VB6 代码资产功能已经过验证
- vools 现有模块结构稳定
- 开发者熟悉 Python 和 vools 架构

## Acceptance Criteria

### AC-1: 验证模块功能完整
- **Given**: 验证模块已实现
- **When**: 调用验证函数（is_email, is_mobile, is_id_card 等）
- **Then**: 返回正确的布尔值
- **Verification**: `programmatic`

### AC-2: JSON 解析器兼容标准库
- **Given**: JSON 解析器已实现
- **When**: 解析标准 JSON 字符串并序列化对象
- **Then**: 结果与标准库 json 模块一致
- **Verification**: `programmatic`

### AC-3: 剪贴板保存功能正常工作
- **Given**: ClipSubject 已添加保存方法
- **When**: 调用 save_clips_text_to_file, save_clips_picture_to_file, save_all_to_file
- **Then**: 剪贴板内容正确保存到指定目录
- **Verification**: `programmatic`

### AC-4: 正则过滤功能有效
- **Given**: save_clips_text_to_file 支持正则过滤
- **When**: 提供正则表达式参数
- **Then**: 只有匹配的内容被保存
- **Verification**: `programmatic`

### AC-5: 单元测试覆盖率
- **Given**: 所有模块都有单元测试
- **When**: 运行测试套件
- **Then**: 所有测试通过
- **Verification**: `programmatic`

## Open Questions
- [ ] Windows 消息钩子功能是否需要跨平台兼容方案？
- [ ] 是否需要支持更多的 VB6 功能模块？
