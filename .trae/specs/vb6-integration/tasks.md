# VB6 代码资产集成计划 - Implementation Plan

## [x] Task 1: 创建验证模式库模块
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 从 VB6 Vfx.cls 提取正则验证模式
  - 实现邮箱、手机、身份证、车牌等常用数据验证函数
  - 实现字符串工具函数
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: 所有验证函数返回正确布尔值
  - `programmatic` TR-1.2: 边界条件测试通过
- **Notes**: 确保正则表达式兼容 Python，修复 VB6 正则中的语法差异

## [x] Task 2: 更新 vools/data/__init__.py 导出验证模块
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 添加验证模块导入
  - 更新 __all__ 列表
  - 确保可通过 `from vools.data import *` 导入
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-2.1: 验证模块函数可正确导入
- **Notes**: 保持与现有导出风格一致

## [x] Task 3: 为验证模块编写单元测试
- **Priority**: high
- **Depends On**: Task 2
- **Description**: 
  - 覆盖所有验证函数的有效、无效、边界场景
  - 确保测试用例全面
- **Acceptance Criteria Addressed**: AC-1, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 所有测试用例通过
- **Notes**: 使用 pytest 框架

## [x] Task 4: 将 JSON 解析器整合到 serialize 模块
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 基于 VB6 JSON.cls 移植到 Python
  - 实现 VBJsonBackend 类
  - 支持注释忽略、单引号字符串等 VB6 特性
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-4.1: 解析标准 JSON 字符串正确
  - `programmatic` TR-4.2: 序列化对象正确
  - `programmatic` TR-4.3: 与标准库 json 模块结果一致
- **Notes**: 遵循 vools.serialize 模块的后端抽象基类

## [x] Task 5: 更新 serialize 模块注册新后端
- **Priority**: high
- **Depends On**: Task 4
- **Description**: 
  - 注册 VBJsonBackend 到后端注册表
  - 更新 __all__ 列表
  - 确保可通过 get_backend('vb_json') 获取
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-5.1: get_backend('vb_json') 返回正确实例
- **Notes**: 保持与现有后端注册风格一致

## [x] Task 6: 为 VB JSON 后端编写单元测试
- **Priority**: high
- **Depends On**: Task 5
- **Description**: 
  - 测试解析、序列化、兼容性等功能
  - 覆盖特殊特性（注释、单引号）
- **Acceptance Criteria Addressed**: AC-2, AC-5
- **Test Requirements**:
  - `programmatic` TR-6.1: 所有测试用例通过
- **Notes**: 使用 pytest 框架

## [x] Task 7: 为 ClipSubject 添加剪贴板保存功能
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 实现 save_clips_text_to_file: 保存文本到文件，支持正则过滤
  - 实现 save_clips_picture_to_file: 保存图片到文件
  - 实现 save_all_to_file: 保存所有类型剪贴板内容
- **Acceptance Criteria Addressed**: AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-7.1: 文本保存功能正常
  - `programmatic` TR-7.2: 图片保存功能正常
  - `programmatic` TR-7.3: 正则过滤功能有效
- **Notes**: 基于 VB6 cClip.cls 和 gModule.bas 的功能

## [x] Task 8: 为剪贴板保存功能编写单元测试
- **Priority**: high
- **Depends On**: Task 7
- **Description**: 
  - 测试文本保存、图片保存、正则过滤等场景
  - 覆盖边界条件
- **Acceptance Criteria Addressed**: AC-3, AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-8.1: 所有测试用例通过
- **Notes**: 使用 pytest 框架

## [ ] Task 9: 实现 Windows 消息钩子功能
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 实现热键注册功能
  - 实现系统消息监听
  - 提供跨平台兼容方案
- **Acceptance Criteria Addressed**: FR-4
- **Test Requirements**:
  - `programmatic` TR-9.1: 热键注册和回调正常工作
  - `human-judgement` TR-9.2: 跨平台兼容性方案合理
- **Notes**: 基于 VB6 Vfx.cls 中的热键相关功能

## [ ] Task 10: 为消息钩子功能编写单元测试
- **Priority**: medium
- **Depends On**: Task 9
- **Description**: 
  - 测试热键注册、消息监听等功能
- **Acceptance Criteria Addressed**: FR-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-10.1: 所有测试用例通过
- **Notes**: 使用 pytest 框架

## [ ] Task 11: 运行完整测试套件
- **Priority**: high
- **Depends On**: Tasks 3, 6, 8, 10
- **Description**: 
  - 运行所有相关测试
  - 确保无回归问题
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-11.1: 所有测试通过
- **Notes**: 使用 pytest 运行完整测试套件
