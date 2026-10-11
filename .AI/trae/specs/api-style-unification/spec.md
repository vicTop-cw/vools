# API 风格统一与文档完善 Spec

## Why
vools 库功能丰富但 API 风格不一致，函数签名命名混乱，学习门槛较高，文档和错误提示不够完善，影响开发者体验和库的可维护性。

## What Changes
- 统一装饰器命名规范（清理重复命名如 `curry` vs `curried`, `overload` vs `overloads`）
- 统一函数签名参数命名和调用方式
- 简化学习门槛，提供渐进式入门路径
- 完善文档结构，添加使用示例和最佳实践
- 增强错误提示，提供清晰的错误信息和修复建议

## Impact
- Affected specs: 装饰器模块、函数式工具模块、响应式模块
- Affected code: `vools/decorators/`, `vools/functional/`, `vools/reactive/`

## ADDED Requirements

### Requirement: 统一命名规范
系统 SHALL 提供一致的 API 命名规范：
- 装饰器命名统一使用动词形式（如 `curry`, `overload`, `retry`）
- 清理重复命名的装饰器，保留主要版本并标记次要版本为弃用
- 函数签名参数命名统一使用 snake_case

#### Scenario: 装饰器命名统一
- **WHEN** 用户使用装饰器
- **THEN** 所有装饰器命名遵循统一规范，无重复命名

### Requirement: 统一调用方式
系统 SHALL 提供一致的装饰器调用方式：
- 所有装饰器支持 `@decorator` 和 `@decorator()` 两种调用方式
- 参数设计遵循一致的模式（可选参数使用关键字参数）

#### Scenario: 装饰器调用一致性
- **WHEN** 用户使用装饰器
- **THEN** 可以选择 `@decorator` 或 `@decorator(params)` 调用方式

### Requirement: 渐进式学习路径
系统 SHALL 提供渐进式学习路径：
- 提供快速入门文档，展示最常用功能
- 提供进阶文档，展示高级功能和最佳实践
- 提供完整 API 参考文档

#### Scenario: 新用户入门
- **WHEN** 新用户访问文档
- **THEN** 可以通过快速入门文档在 10 分钟内掌握基本用法

### Requirement: 完善文档结构
系统 SHALL 提供完善的文档结构：
- 每个模块提供独立的文档文件
- 每个函数/装饰器提供使用示例
- 提供常见问题和解决方案

#### Scenario: 文档完整性
- **WHEN** 用户查阅文档
- **THEN** 可以找到所需功能的详细说明和示例

### Requirement: 增强错误提示
系统 SHALL 提供清晰的错误提示：
- 错误信息包含具体的问题描述
- 错误信息包含修复建议
- 错误信息包含相关文档链接

#### Scenario: 错误提示友好性
- **WHEN** 用户遇到错误
- **THEN** 错误信息清晰描述问题并提供修复建议

## MODIFIED Requirements

### Requirement: 保持功能多样性
系统 SHALL 保持现有功能多样性：
- 不删除现有功能
- 不改变现有功能的行为
- 仅优化命名和文档

## REMOVED Requirements
无删除的功能要求。