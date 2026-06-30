# 贡献指南 (Contributing)

> **模块路径**：-
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#A05
> **最后更新**：2026-06-30

---

## 概述

感谢您对 vools 项目的兴趣！我们欢迎各种形式的贡献，包括但不限于代码提交、文档改进、Bug 报告和功能建议。

## 如何贡献

### 1. 报告问题

如果您发现 Bug 或有新功能建议，请在 GitHub Issues 中提交：

- **Bug 报告**：请包含复现步骤、期望行为和实际行为
- **功能建议**：请描述用例和预期效果

### 2. 提交代码

#### 开发环境设置

```bash
# 1. Fork 仓库
git clone https://github.com/vicTop-cw/vools.git
cd vools

# 2. 创建开发分支
git checkout -b feature/your-feature-name

# 3. 安装开发依赖
pip install -e ".[dev]"

# 4. 安装 pre-commit 钩子
pre-commit install
```

#### 代码规范

**Python 代码规范**：

- 遵循 PEP 8
- 使用 4 空格缩进
- 最大行长度：100 字符
- 使用类型注解（推荐）

**命名规范**：

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块 | 小写下划线 | `my_module.py` |
| 类 | PascalCase | `MyClass` |
| 函数 | 小写下划线 | `my_function()` |
| 常量 | 全大写下划线 | `MAX_SIZE` |
| 私有 | 下划线前缀 | `_private_func()` |

**文档字符串**：

```python
def my_function(param1: str, param2: int) -> bool:
    """简要描述函数功能。

    更详细的说明（如果需要）。

    Args:
        param1: 参数1的说明
        param2: 参数2的说明

    Returns:
        返回值的说明

    Raises:
        ValueError: 何时抛出此异常
    """
    pass
```

#### 提交 PR 步骤

1. **确保测试通过**：
```bash
# 运行所有测试
python -m pytest tests/ -v

# 仅运行相关测试
python -m pytest tests/functional/ -v
```

2. **提交代码**：
```bash
# 添加更改
git add changed_file.py

# 提交（使用语义化提交信息）
git commit -m "feat: 添加新功能"
git commit -m "fix: 修复某问题"
git commit -m "docs: 更新文档"
```

**提交信息格式**：

```
<type>(<scope>): <subject>

<body>

footer
```

| Type | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档变更 |
| style | 代码格式（不影响功能） |
| refactor | 重构 |
| test | 测试相关 |
| chore | 构建/工具变更 |

3. **推送分支**：
```bash
git push origin feature/your-feature-name
```

4. **创建 Pull Request**：

在 GitHub 上创建 PR，描述：
- 解决的问题或添加的功能
- 涉及的测试用例
- 是否需要更新文档

#### PR 审查清单

- [ ] 代码符合 PEP 8 规范
- [ ] 添加了必要的测试
- [ ] 测试全部通过
- [ ] 更新了相关文档
- [ ] 提交信息清晰准确

### 3. 文档贡献

文档位于 `docs/` 目录：

- `docs/functional/` - 函数式编程文档
- `docs/reactive/` - 响应式编程文档
- `docs/data/` - 数据处理文档
- `docs/bridge/` - 跨语言桥接文档
- `docs/appendix/` - 附录文档

### 4. 测试贡献

测试位于 `tests/` 目录：

```bash
# 运行特定测试文件
python -m pytest tests/functional/test_pipe_ops.py -v

# 运行特定测试用例
python -m pytest tests/functional/test_pipe_ops.py::test_basic_pipe -v

# 生成覆盖率报告
python -m pytest tests/ --cov=vools --cov-report=html
```

## 项目结构

```
vools/
├── vools/              # 源代码
│   ├── decorators/    # 装饰器模块
│   ├── functional/     # 函数式工具
│   ├── data/          # 数据处理
│   ├── reactive/      # 响应式编程
│   ├── bridge/        # 跨语言桥接
│   └── ...
├── tests/             # 测试文件
├── docs/              # 文档
├── examples/          # 示例代码
└── benchmark/         # 性能基准
```

## 行为准则

- 尊重所有贡献者
- 使用包容性语言
- 保持建设性讨论
- 关注社区利益

## 许可证

通过贡献代码，您同意将您的作品按照 [Apache 2.0](../../LICENSE) 许可证发布。

## 获取帮助

- **GitHub Discussions**：https://github.com/vicTop-cw/vools/discussions
- **GitHub Issues**：https://github.com/vicTop-cw/vools/issues
