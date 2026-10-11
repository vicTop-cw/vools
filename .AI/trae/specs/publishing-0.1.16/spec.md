# vools 0.1.16 发布计划 - 产品需求文档 (PRD)

## Overview
- **Summary**: 执行 vools 包版本 0.1.16 的完整发布流程，包括代码同步、构建验证和 PyPI 发布
- **Purpose**: 确保 vools 0.1.16 版本能够顺利发布到 PyPI，让用户可以通过 pip 安装使用最新功能
- **Target Users**: vools 库的开发者和最终用户

## Goals
- 完成代码仓库的全面同步（GitHub 和 GitCode）
- 成功将 vools 0.1.16 发布到 PyPI
- 确保发布前所有测试通过
- 文档化完整的执行计划和验证步骤

## Non-Goals (Out of Scope)
- 不进行新功能开发或代码重构
- 不修改版本号（当前已为 0.1.16）
- 不创建 GitHub Release（仅 PyPI 发布）

## Background & Context
- 当前版本已在 `vools/__init__.py` 中设置为 `0.1.16`
- 代码已完成重构和优化，包含 reactive 子包性能优化、rself 装饰器增强等功能
- 本地代码有未提交的更改和未推送的提交
- 项目使用 pyproject.toml 进行构建配置

## Functional Requirements
- **FR-1**: 同步本地代码到远程仓库（GitHub 和 GitCode）
- **FR-2**: 执行完整测试套件确保所有测试通过
- **FR-3**: 构建并发布 vools 0.1.16 到 PyPI

## Non-Functional Requirements
- **NFR-1**: 发布过程必须可重复、可验证
- **NFR-2**: 发布前必须通过所有测试
- **NFR-3**: 必须保留发布记录和验证结果

## Constraints
- **Technical**: Python 3.6+，setuptools >= 42，wheel
- **Business**: 需要有效的 PyPI 凭据
- **Dependencies**: wrapt >= 2.1.2，attrs >= 17.4.0

## Assumptions
- PyPI 凭据已配置（~/.pypirc 或环境变量）
- 网络连接正常，可访问 GitHub、GitCode 和 PyPI
- 本地环境已安装必要的构建工具

## Acceptance Criteria

### AC-1: 代码同步完成
- **Given**: 本地有未提交的更改和未推送的提交
- **When**: 执行 git add、git commit 和 git push 操作
- **Then**: 本地代码完全同步到 GitHub 和 GitCode 远程仓库
- **Verification**: `programmatic`
- **Notes**: 需要同时同步 GitHub (origin) 和 GitCode (gitcode)

### AC-2: 测试套件通过
- **Given**: 代码已同步完成
- **When**: 运行 pytest 测试套件
- **Then**: 所有测试用例通过（777+ 个测试）
- **Verification**: `programmatic`
- **Notes**: 排除编码损坏的集成测试文件

### AC-3: 包构建成功
- **Given**: 测试通过，代码已同步
- **When**: 执行构建命令（python -m build）
- **Then**: 成功生成 .whl 和 .tar.gz 文件
- **Verification**: `programmatic`

### AC-4: PyPI 发布成功
- **Given**: 构建成功，生成了发布包
- **When**: 执行 twine upload 命令
- **Then**: 包成功上传到 PyPI，可通过 pip install vools==0.1.16 安装
- **Verification**: `programmatic`

## Open Questions
- [ ] PyPI 凭据是否已正确配置？
- [ ] 是否需要创建 GitHub Release？
- [ ] 是否需要更新 CHANGELOG 文件？