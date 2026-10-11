# vools 文档站点建设规范

## Why

vools 是一个功能丰富的 Python 工具库，当前文档分散在多个 README 和文档中，缺乏统一的展示平台。需要建立专业的文档站点，让用户能够方便地浏览、查找和使用 vools 的各项功能。

## What Changes

### 1. 技术选型

- **文档框架**：MkDocs + MkDocs Material 主题
- **托管平台**：GitHub Pages（免费）
- **文档格式**：Markdown
- **代码高亮**：PyMdown Extensions（支持语法高亮、代码片段、Tab 切换）

### 2. 文档结构

```
docs/
├── index.md              # 主页（#001）
├── getting-started/
│   ├── installation.md  # 安装（#002）
│   └── quickstart.md     # 快速开始（#003）
├── core/
│   ├── decorators.md     # 装饰器（#004）
│   ├── placeholder.md    # 占位符（#005）
│   ├── overload.md       # 函数重载（#006）
│   ├── curry.md          # 柯里化（#007）
│   └── memoize.md        # 缓存装饰器（#008）
├── functional/
│   ├── pipe.md           # 管道操作（#009）
│   ├── seq.md            # Seq 序列（#010）
│   ├── box.md            # Box 包装器（#011）
│   └── result.md         # Result 类型（#012）
├── reactive/
│   ├── overview.md       # 响应式编程概述（#013）
│   ├── observable.md     # Observable（#014）
│   ├── operators.md      # 操作符（#015）
│   └── monitoring.md     # 系统监控（#016）
├── data/
│   ├── vlist.md          # VList 增强列表（#017）
│   ├── vtext.md          # VText 增强文本（#018）
│   └── vdate.md          # VDate 日期处理（#019）
├── bridge/
│   ├── overview.md       # 多语言桥接概述（#020）
│   ├── rust.md           # Rust 桥接（#021）
│   ├── nim.md            # Nim 桥接（#022）
│   ├── go.md             # Go 桥接（#023）
│   └── others.md         # 其他语言（#024）
├── sql/
│   ├── overview.md       # SQL 工具概述（#025）
│   ├── sqlite.md          # SQLite 支持（#026）
│   └── spark.md          # Spark 支持（#027）
├── appendix/
│   ├── changelog.md      # 更新日志（#A01）
│   ├── faq.md            # 常见问题（#A02）
│   ├── benchmark.md      # 性能基准（#A03）
│   ├── platform.md        # 平台限制说明（#A04）
│   └── contribute.md     # 贡献指南（#A05）
└── api/
    └── reference.md      # API 参考索引（#A06）
```

### 3. 全局唯一编号规则

- **功能模块**：#001 - #999（按文档顺序）
- **附录模块**：#A01 - #A99（附录文档）
- 编号规则：
  - 每个 `#` 编号在文档中必须唯一
  - 编号用于锚点定位：`#004` → `{#004}`
  - 便于后续修改、移除和新增

### 4. 文档元数据规范

每个功能文档必须包含以下头部信息：

```markdown
# 功能名称 {#004}

> **模块路径**：`vools.decorators`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#004
> **最后更新**：2026-06-30

## 功能描述

...
```

### 5. 示例代码规范

```markdown
### 基本用法 {#004-01}

!!! info "示例说明"
    此示例展示装饰器的基本用法。

```python
from vools import memorize

@memorize(duration=60)
def expensive_function(x):
    return x ** 2

result = expensive_function(5)  # 首次调用，执行计算
result = expensive_function(5)  # 第二次调用，使用缓存
print(result)  # 输出: 25
```

- ✅ 测试通过：已在 `tests/decorators/test_cache.py` 中验证
- 🪟 Windows：支持
- 🍎 macOS：支持
- 🐧 Linux：支持

### 代码可运行性要求

所有示例代码必须满足以下要求：

1. **完整的可运行代码**：用户复制后直接运行即可，无需添加任何额外代码
2. **包含输出说明**：如示例有输出，必须在代码中 `print()` 并注释说明输出结果
3. **依赖明确标注**：如需额外依赖，必须在示例开头注释说明
4. **测试验证**：所有示例必须通过实际测试验证

```markdown
### 完整可运行示例 {#004-01}

!!! tip "要求"
    所有示例必须是完整的、可直接运行的代码块。

```python
# 依赖: pip install vools
from vools import memorize

@memorize(duration=60)
def expensive_function(x):
    return x ** 2

# 首次调用，执行计算
result = expensive_function(5)
print(result)  # 输出: 25

# 第二次调用，使用缓存（快速返回）
result = expensive_function(5)
print(result)  # 输出: 25
```

### 示例代码验证标记

每个示例必须包含以下验证标记：

| 标记 | 含义 |
|------|------|
| `✅ 测试通过` | 已通过 pytest 测试验证 |
| `✅ 示例可运行` | 已手动验证可运行 |
| `⚠️ 需要依赖` | 需要额外安装依赖 |
| `🔧 需配置` | 需要额外配置才能运行 |

### 6. 平台限制标注

在文档中明确标注平台限制：

| 标注 | 含义 |
|------|------|
| ✅ | 完全支持 |
| ⚠️ | 部分支持或有条件限制 |
| ❌ | 不支持 |
| 🔒 | 仅特定版本支持 |

示例：
```markdown
| 功能 | Windows | macOS | Linux | 备注 |
|------|---------|-------|-------|------|
| memorize | ✅ | ✅ | ✅ | |
| 键盘监控 | ✅ | ⚠️ | ⚠️ | 需安装 pyHook |
| 剪贴板监控 | ✅ | ✅ | ✅ | |
```

### 7. 导航结构

- **顶部导航**：主页 / 核心功能 / 函数式 / 响应式 / 数据 / 桥接 / 附录
- **侧边栏**：自动生成，根据文档目录结构
- **面包屑**：主页 > 模块 > 功能
- **上一讲/下一讲**：文档底部自动导航
- **搜索**：MkDocs Material 内置搜索（支持中文）

### 8. 主页设计

主页应包含：
- 一句话定位：`vools - Python 函数式编程工具集`
- 核心特性卡片（4-6 个亮点）
- 快速代码示例（3-5 行）
- GitHub 链接和 PyPI 徽章
- 特性亮点列表

## Impact

- **受影响规格**：无（新增功能）
- **受影响代码**：
  - 新建 `docs/` 目录
  - 新建 `mkdocs.yml` 配置文件
  - 更新 `pyproject.toml` 添加文档依赖

## ADDED Requirements

### Requirement: 全局唯一编号系统

文档中的每个功能节点必须具有全局唯一编号，格式为 `#XXX`（功能）或 `#AXX`（附录）。

#### Scenario: 编号定位
- **WHEN** 用户需要定位特定功能
- **THEN** 通过编号 `#004` 可直接跳转或搜索到对应文档

#### Scenario: 编号维护
- **WHEN** 需要移除或新增功能
- **THEN** 可通过编号快速定位和更新

### Requirement: 平台限制说明

每个功能必须明确标注平台支持情况。

#### Scenario: 跨平台开发
- **WHEN** 用户在非 Windows 平台使用特定功能
- **THEN** 应在文档中看到明确的平台限制提示

### Requirement: 测试状态追踪

文档中的示例必须标注测试状态。

#### Scenario: 示例可靠性
- **WHEN** 用户参考文档示例
- **THEN** 应能看到该示例是否已通过测试验证

### Requirement: 示例代码可运行性

所有文档中的示例代码必须是完整、可运行的。

#### Scenario: 用户复制运行
- **WHEN** 用户从文档复制示例代码
- **THEN** 代码应能直接运行，无需任何修改
- **AND** 应包含 `print()` 输出语句并注释说明输出结果
- **AND** 应标注测试验证状态

#### Scenario: 依赖说明
- **WHEN** 示例需要额外依赖
- **THEN** 必须在代码开头注释标注依赖

### Requirement: 示例验证流程

每个示例代码必须经过验证才能写入文档。

#### Scenario: 示例编写
- **WHEN** 编写新的示例代码
- **THEN** 必须使用 pytest 或手动方式验证代码可运行
- **AND** 验证通过后在文档中标注 `✅ 测试通过`

### Requirement: 全局导航与跳转

文档站点必须支持全局导航和内部跳转。

#### Scenario: 页面导航
- **WHEN** 用户浏览文档
- **THEN** 可通过顶部导航快速切换模块，通过侧边栏浏览当前模块，通过底部链接切换上下文档

#### Scenario: 锚点跳转
- **WHEN** 用户点击文档内链接
- **THEN** 应能平滑跳转并支持返回

### Requirement: 文档与代码同步

文档内容必须与源代码保持一致。

#### Scenario: 代码变更检测
- **WHEN** 源代码发生变更
- **THEN** 应能通过测试验证文档示例的正确性

## MODIFIED Requirements

### Requirement: 现有 README 同步

将现有 `README.md`、`USER_GUIDE.md`、`guide/` 等文档内容迁移到新的文档结构中，并确保内容与源代码一致。

## REMOVED Requirements

### Requirement: 旧文档结构

**Reason**：建立统一的文档站点
**Migration**：将现有 `docs/` 和 `guide/` 目录的内容迁移到新的 `docs/` 结构，删除旧目录
