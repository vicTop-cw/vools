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

## 分支合并策略（Trunk-Based，以本地仓库为主）

> **以本地仓库为唯一真源**：`main` 是长期开发主线（trunk）。本地 `main` 的
> 历史与状态以工作区为准，不做远程强制推送。

### 分支角色

| 分支 | 用途 | 生命周期 |
|---|---|---|
| `main` | **唯一 trunk**，长期开发主线，所有合流终点 | 永久 |
| `feat/<name>` | 新功能分支 | 极短（≤1 天），合并后立即删除 |
| `fix/<name>` | 缺陷修复分支 | 极短，合并后立即删除 |
| `gh-pages` | GitHub Pages 部署分支（仅文档产物） | 保留 |
| `master` | ~~旧默认分支~~ | **已废弃，删除** |

### 分支创建与合并

```bash
# 1. 从 main 拉分支（保持最新）
git checkout main
git pull origin main          # 本地以 main 为准，可跳过远程
git checkout -b feat/my-thing

# 2. 开发 + 提交
# ... 修改 ...
git add -A
git commit -m "feat(xxx): 简述"

# 3. 合并回 main 并删除分支（合并后必须清理）
git checkout main
git merge feat/my-thing       # 优先 --squash 保持主线干净
git branch -d feat/my-thing   # 已合并，删除
```

### 硬性规则

1. **`main` 是唯一主线**，不在 main 上做长尾实验。
2. **分支合并后立即删除**：`git log main..<branch>` 为空即代表已完全合并，
   可以 `git branch -d <branch>` 清理。
3. **短生命周期**：分支存在时间不超过 1 天；超过请先合并回 main 再开新分支。
4. **远程只作镜像**：以本地仓库为主，远程（`origin` / `github` / `gitcode`）
   只用于同步，不作真源。
5. **保留 `gh-pages`**：这是 MkDocs 部署产物，不属于代码分支，不要动它。
6. **`master` / 任何旧主线分支**：一旦被 `main` 完全包含（`git log main..master`
   为空），直接 `git branch -d` 删除。
7. **提交信息规范**：`feat(xxx): ...` / `fix(xxx): ...` / `compat(xxx): ...` /
   `docs(xxx): ...` / `chore(xxx): ...`，见 CHANGELOG 前缀约定。

### 本地维护命令

```bash
# 查看哪些分支已完全合并（可以安全删除）
git log main..<branch> --oneline   # 输出为空 = 已合并

# 一键清理已合并分支
git branch -d fix/actus-schema-path
git branch -d master

# 查看主线未推送提交（本地为主，不强制推远程）
git log origin/main..main --oneline
```

---

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
