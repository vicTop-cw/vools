# vools 项目全面优化 v1 - Product Requirement Document

## Overview
- **Summary**: 对 vools 项目进行全面的代码质量、测试组织、架构一致性优化，解决重复实现、测试混乱、代码不规范等问题，提升项目可维护性和用户体验。
- **Purpose**: 随着项目功能快速迭代，积累了结构性问题（重复实现、测试组织混乱、代码质量参差不齐），需要系统性优化，为后续版本迭代打下坚实基础。
- **Target Users**: vools 库的开发者和维护者

## Goals
- **测试组织规范化** - 统一测试风格，清理冗余测试文件，确保 pytest 默认能运行核心测试
- **消除重复实现** - 统一缓存装饰器、工具函数等多处重复的实现，建立单一事实来源
- **代码质量提升** - 修复裸露 except、清理生产代码中的测试/调试代码、消除硬编码路径
- **架构一致性** - 明确模块职责边界，统一命名规范，清理遗留代码

## Non-Goals (Out of Scope)
- 不做新功能开发
- 不做破坏性 API 变更（所有优化保持向后兼容）
- 不重写核心模块（reactive、bridge 等大模块仅做必要清理）
- 不做性能优化（除非是清理过程中的附带收益）
- 不补充缺失模块的测试（sql、security 等零覆盖模块留待后续）

## Background & Context

vools 是一个功能丰富的 Python 函数式编程工具集，包含 25+ 个子包、约 13.6 万行代码、1300+ 个测试用例。

**已发现的主要问题**：

### 1. 测试组织问题
- `pyproject.toml` 默认忽略所有核心测试目录，`pytest` 命令几乎跑不到有意义的测试
- `py36_test/` 目录有 23 个重复测试文件（与 tests/ 下内容大量重叠）
- `tests/misc/` 目录混合了调试脚本、文档、数据文件等非测试内容
- `tests/xl/` 下多为脚本式 demo，不是标准 pytest 测试
- 生产代码目录中存在测试文件：`vools/data/test_qax.py`
- 三种测试风格混用：pytest 函数式、unittest 类式、脚本式 print 测试

### 2. 重复实现问题
- **缓存装饰器重复**：`vools/cache/` 包和 `vools/decorators/cache.py` 各有一套 memorize/once/persist 实现
  - `decorators/__init__.py` 从 `vools/cache/` 导出
  - 但 `decorators/curry_delay.py` 仍从 `decorators/cache.py` 导入旧实现
- **工具函数重复**：identity、const、compose、pipe 等基础函数在多处独立实现

### 3. 代码质量问题
- 生产代码中存在测试/调试代码（模块末尾的 `if __name__ == "__main__"` 测试块）
- `vools/__init__.py` 末尾包含演示用的示例函数和 print 语句
- 存在硬编码的用户特定路径（`C:\Users\victo\...`）
- `decorators/rself.py` 末尾有大量测试代码

### 4. 遗留代码问题
- `vools/decorators/cache.py` 可能是遗留文件（已被 `vools/cache/` 替代但未清理）

## Functional Requirements

### FR-1: 测试组织规范化
- 调整 `pyproject.toml` 的 pytest 配置，确保核心测试默认可运行
- 清理 `py36_test/` 目录（归档或删除）
- 清理 `tests/misc/` 目录（移除非测试文件）
- 将 `vools/data/test_qax.py` 迁移到 `tests/data/` 目录
- 将脚本式 xl 测试改写为标准 pytest 测试或移到 examples/

### FR-2: 统一缓存装饰器实现
- 确认 `vools/cache/` 包为唯一官方实现
- 修复 `decorators/curry_delay.py` 中的导入，改用 `vools/cache/`
- 评估并移除 `vools/decorators/cache.py` 遗留文件（确认无其他依赖后）
- 确保所有缓存相关功能向后兼容

### FR-3: 清理生产代码中的测试/调试代码
- 移除或迁移 `vools/__init__.py` 末尾的演示/测试代码
- 移除或迁移 `decorators/rself.py` 末尾的测试代码
- 检查其他模块末尾的 `if __name__ == "__main__"` 测试块，迁移到 tests/

### FR-4: 修复硬编码路径
- 将 `bridge/manager.py` 中的用户特定路径改为使用 `os.path.expanduser('~')`
- 确保所有路径配置可移植，不依赖特定用户名

### FR-5: 统一测试风格
- 移除测试文件中不必要的 `sys.path.insert`
- 减少测试中的 print 语句，使用 pytest 断言机制
- 统一测试文件命名规范

## Non-Functional Requirements

- **NFR-1 向后兼容**: 所有优化不得破坏现有公共 API，用户代码无需修改
- **NFR-2 Python 版本兼容**: 保持 Python 3.6 - 3.13 全版本支持
- **NFR-3 测试通过**: 优化后所有现有测试必须通过
- **NFR-4 渐进式优化**: 每个优化点独立可验证，可分阶段合并

## Constraints

- **技术约束**: 必须保持 Python 3.6 兼容性，不能使用 3.7+ 独有特性
- **业务约束**: 不能破坏向后兼容性，所有变更必须是纯内部重构
- **依赖约束**: 不新增运行时依赖
- **范围约束**: 本次优化集中在"清理和规范"，不做新功能

## Assumptions

- `vools/cache/` 包是缓存装饰器的官方实现，`decorators/cache.py` 是遗留文件
- `py36_test/` 目录是历史遗留，不再需要维护（Python 3.6 测试通过嵌入式解释器进行）
- `tests/misc/` 下的调试脚本可以安全移动到其他目录
- xl 模块的脚本式测试可以改写为标准 pytest 测试

## Acceptance Criteria

### AC-1: pytest 默认能运行核心测试
- **Given**: 项目根目录
- **When**: 执行 `pytest` 命令
- **Then**: 至少能运行 functional、decorators、data 等核心模块的测试，测试通过率 100%
- **Verification**: `programmatic`
- **Notes**: 排除需要外部资源的 integration/windows_only 测试

### AC-2: 缓存装饰器只有一套实现
- **Given**: vools 源码
- **When**: 检查 memorize/once/persist 的导入链
- **Then**: 所有模块都从 `vools.cache` 导入，`decorators/cache.py` 已移除或标记为 deprecated
- **Verification**: `programmatic`

### AC-3: 生产代码中无测试文件
- **Given**: `vools/` 源码目录
- **When**: 搜索 `test_*.py` 文件
- **Then**: 生产代码目录中没有测试文件
- **Verification**: `programmatic`

### AC-4: 无硬编码的用户特定路径
- **Given**: vools 源码
- **When**: 搜索 `C:\Users\` 或 `/home/` 加具体用户名的路径
- **Then**: 生产代码中没有硬编码的用户特定路径
- **Verification**: `programmatic`

### AC-5: py36_test 目录已清理
- **Given**: 项目根目录
- **When**: 检查 `py36_test/` 目录
- **Then**: 目录已删除或归档到合适位置
- **Verification**: `programmatic`

### AC-6: 所有现有测试通过
- **Given**: 优化后的代码
- **When**: 运行完整测试套件
- **Then**: 所有之前通过的测试仍然通过
- **Verification**: `programmatic`

### AC-7: 向后兼容
- **Given**: 现有用户代码
- **When**: 升级到优化后的版本
- **Then**: 无需修改任何代码即可正常运行
- **Verification**: `programmatic`

## Open Questions

- [ ] `py36_test/` 目录是直接删除还是归档到 archive/？
- [ ] `tests/misc/` 下的调试脚本移动到哪里？（建议 `scripts/` 或 `tools/` 目录）
- [ ] xl 模块的脚本式性能测试是改写为 pytest-benchmark 还是移到独立 benchmarks/ 目录？
- [ ] `decorators/cache.py` 是直接删除还是先标记为 deprecated 再删除？
