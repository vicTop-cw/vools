# vools 项目环视与建设性意见计划

> 日期：2026-06-22  
> 范围：代码质量 / 仓库健康 / 架构 / 工程化 / 技术债  
> 性质：**非编辑型建议报告**（附可执行优化项的分步计划）

---

## 一、项目概况

**vools** 是一个 Python 函数式编程工具集，核心模块包括：

| 模块 | 说明 |
|------|------|
| `vools/decorators/` | 装饰器（curry、overload、cache、shotcut 等）|
| `vools/functional/` | 函数式工具（placeholder、iif、box、pipe）|
| `vools/reactive/` | 响应式编程（Observable、Subject、monitor、operators）|
| `vools/data/` | 数据结构（Seq、vicText、vicDate、vicList）|
| `vools/serialize/` | 序列化框架（JSON/msgpack/pickle + callable handler）|
| `vools/task/` | 任务调度与规则引擎 |
| `vools/security/` | 安全求值 |
| `vools/utils/` | 通用工具（Stuff、Hoder）|
| `vools/recorder/` | 键鼠录制/回放（含 GUI）|
| `vools/crypto/`、`vools/encoding/` | 加密/编码工具 |

当前版本：`0.1.18`，由 Victor 维护。

---

## 二、一眼可见的主要问题

### 2.1 仓库"脏"——临时/调试文件混入仓库

问题最严重的区域：

| 目录 | 文件数 | 是否应进入仓库 |
|------|--------|----------------|
| `Temp/` | ~25 个临时脚本（`add_do_ast.py`、`fix_4files.py`…）| ❌ 应删除 |
| `debug/` | ~10 个 debug 脚本 | ❌ 应移动到 `tests/` 或删除 |
| `dev_tools/` | ~15 个一次性修复脚本 | ⚠️ 应归档/整理（不在仓库分发）|
| `db/` | `tasks.db`、`tasks.db-wal`、`test_batch.db` | ❌ 运行时产物 |
| `tests/__persist__/`、`vools/decorators/__persist__/` | 持久化测试产物 | ⚠️ 应加入 `.gitignore` |
| `.run/` | IDE 运行配置 | ⚠️ 可选（建议忽略个人 IDE 配置）|

**风险：**
- 这些文件会让 PyPI sdist 体积膨胀
- 影响 `pip install` 用户对项目质量的第一印象
- `flake8`/`mypy` 扫描时容易误报或被污染
- CI 中 `pip install -e .[dev]` 时 `find_packages()` 可能把 `Temp/` 之类意外打包

### 2.2 技术债：旧的分析报告/临时计划仍位于根目录

- `analysis/FEATURE_EXTENSION_PLAN.md`、`analysis/IMPLEMENTATION_PLAN.md`… 这些应迁移到 `.trae/documents/` 或 `docs/`，或直接删除
- `.workbuddy/` 是 AI 工具产物，其内容不在仓库分发范围内
- `_plan_writer.py` 是临时脚本，不应在根目录

### 2.3 CI 配置的可改进点

查看 [ci.yml](file:///e:/IDEProjects/AI/vools/.github/workflows/ci.yml)：

- `pip install -e .[dev]` 用 `setuptools>=42`，当前现代 Python 项目推荐用 `hatchling` 或 `pdm`
- `python-version: ["3.11", "3.12", "3.13"]` 与 `requires-python = ">=3.6"` **不一致**，且 `classifiers` 中仅列出 3.6-3.9。实际上 3.13 仍处于测试期，CI 中使用 `3.13` 会不稳定。**建议：将 CI 与 `requires-python`、classifiers 对齐**（或反过来说，明确声明支持版本）
- lint job 用 `ubuntu-latest`，但项目声明"OS Independent"，而 reactive 的键鼠模块只在 Windows 工作。**建议：明确平台支持矩阵或使用 `pytest.mark.skipif`**
- 大量 `--ignore=test_clipboard_*.py --ignore=test_file_observer_*.py`，说明需要**更清晰的 marker 划分**（如 `@pytest.mark.integration`、`@pytest.mark.windows_only`），而不是长串 `--ignore`
- 没有 `mypy --strict` 的类型检查步骤
- coverage 阈值设 `fail_under=80`，但 CI 中 coverage job 只是跑一下而已，**未强制执行该阈值**（`.trae/documents/api-optimization-evaluation/evaluation_report.md` 中提到过覆盖率问题）

### 2.4 构建与打包配置

- 同时存在 `setup.py` 和 `pyproject.toml`——`setup.py` 已是 legacy，建议迁移到纯 `pyproject.toml`
- `pyproject.toml` 中缺少 `[tool.setuptools.packages.find]` 或 `exclude`，`Temp/`、`debug/`、`dev_tools/` 可能被打包进 wheel/sdist
- `requirements.txt` 与 `pyproject.toml.optional-dependencies.dev` 有重复，维护两套容易漂移
- 缺少 `[tool.mypy]`、`[tool.black]`、`[tool.isort]` 的统一配置

### 2.5 模块架构与耦合

参考 `.workbuddy/vools-audit-report-2026-06-18.md` 的历史分析：

- `vools/serialize/callable/` 中的 handler 方式与 `__getstate__` 新方式并存
- `curry_core.py` ↔ `selector.py` ↔ `overload.py` 之间的循环 import 依赖
- reactive 的 Subject 族仍未完成 `__getstate__` 迁移
- `vools/task/` 模块是否为活跃代码仍需核实

---

## 三、建议（按优先级分组）

### 高优先级（建议立即处理）

1. **清理仓库临时文件**——删除 `Temp/`、`debug/`、`db/`、`_plan_writer.py`；将 `dev_tools/` 中有用的脚本移动到 `scripts/` 并加入 `.gitignore`
2. **统一 Python 版本声明**——`classifiers` / `requires-python` / CI matrix 三方保持一致
3. **排除非发布包目录**——`pyproject.toml` 中配置 `[tool.setuptools.packages.find]` 的 `exclude`
4. **迁移到纯 `pyproject.toml`**——删除 `setup.py`，将打包配置统一到 `pyproject.toml`
5. **增加 marker 划分 CI 测试**——`@pytest.mark.integration`、`@pytest.mark.windows_only`，替代长串 `--ignore`
6. **更新 `.gitignore`**——覆盖 `__pycache__/`、`*.pyc`、`.pytest_cache/`、`*.egg-info/`、`build/`、`dist/`、`db/`、`__persist__/`、`.idea/`、`.vscode/` 等

### 中优先级（建议下个迭代）

7. **引入 `mypy --strict`** 作为 CI 的一个 job
8. **统一 `black` / `isort` 配置** 到 `pyproject.toml`
9. **完成 Reactive 类的 `__getstate__` 迁移**（Subject / Observable 等）
10. **删除 `Temp/Backup/`、`Temp/stuff_benchmark/` 等旧备份**（Git 本身就是版本控制）
11. **添加 `CHANGELOG` 自动化**——如 `towncrier` 替代手动写 `changelog/v0.1.x.md`
12. **添加 `pre-commit` 真正启用**——`.pre-commit-config.yaml` 已存在，但需要确认 CI 中是否跑起来

### 低优先级（长期优化方向）

13. **替换 `setuptools` 为 `hatchling`**——更现代的构建系统
14. **重构 `vools/serialize/callable/`**——彻底移除旧 handler 方式
15. **将 `dev_tools/` 中有用脚本转为 CLI 子命令**（如 `vools check`、`vools doctest`）
16. **文档站点**——引入 MkDocs 或 Sphinx，自动生成 API 文档

---

## 四、具体可执行步骤（编辑计划）

> 以下步骤需用户确认后执行。如果用户接受，将按顺序创建独立任务并逐一落地。

### Step 1 — 清理仓库临时目录和文件
- 删除 `Temp/` 整个目录
- 删除 `debug/` 整个目录
- 删除 `db/` 整个目录（或仅保留 `tasks.db` 作为示例数据并在测试中清理）
- 删除根目录 `_plan_writer.py`
- 审查 `dev_tools/` 中是否有仍在使用的脚本，无用的删除，有用的移动到 `scripts/` 并配置到 `.gitignore` 中的非打包目录

### Step 2 — 迁移到纯 `pyproject.toml` 打包配置
- 在 `pyproject.toml` 中补全 `[tool.setuptools]`、`[tool.setuptools.packages.find]`
- 设置 `exclude = ["Temp*", "debug*", "dev_tools*", "analysis*", "guide*", "examples*", "autopypi*", "changelog*", ".workbuddy*", ".trae*", ".atomcode*", ".run*"]`
- 删除 `setup.py`
- 合并 `requirements.txt` 内容到 `pyproject.toml.dependencies`（或删除 `requirements.txt` 统一用 `pip install -e .[dev]`）

### Step 3 — 统一 Python 版本声明
- `requires-python` 建议提升到 `>=3.9`（现代项目基线；若仍需 3.8+ 也可）
- 更新 `classifiers` 中 `Programming Language :: Python :: 3.x` 到实际测试的版本
- CI matrix 从 `"3.11", "3.12", "3.13"` 调整为 `"3.9", "3.10", "3.11", "3.12"`，移除 3.13（或标记为 experimental）

### Step 4 — 清理/改进 CI
- 引入 `@pytest.mark.windows_only`、`@pytest.mark.integration` marker
- 用 `-m "not integration and not windows_only"` 替代长串 `--ignore`
- 增加 `mypy vools/` job（先用宽松配置，后续收紧）
- coverage job 加上 `--cov-fail-under=80` 真正强制执行

### Step 5 — 统一代码格式化 / lint 配置
- 在 `pyproject.toml` 中添加 `[tool.black]`、`[tool.isort]`、`[tool.flake8]`
- 运行一次全项目 `black vools/ tests/` 统一格式

### Step 6 — 更新 `.gitignore`
- 覆盖常见 Python 忽略项 + 本项目特定运行时产物

---

## 五、风险评估

| 步骤 | 风险 | 缓解方式 |
|------|------|----------|
| Step 1 删除 `Temp/` 等 | 某些测试可能意外依赖这些目录 | 删除前先跑一次完整 `pytest` 确认绿；并在独立分支操作 |
| Step 2 移除 `setup.py` | 老的发布流程（`autopypi/`）可能依赖 | 先检查 `autopypi/packaging.py`、`autopypi/release.py` 是否读 `setup.py`，若依赖则同步改造 |
| Step 3 提升 `requires-python` | 现有用户若仍在 3.6/3.7 将无法升级 | 先在 `changelog/v0.1.19.md` 中声明"放弃旧版本"，并在 README 中醒目提示 |
| Step 4 marker 改造 | 大量测试文件需批量加 marker | 用脚本（如 `dev_tools/add_do_to_file.py` 类似思路）批量加装饰器 |
| Step 5 black 格式化 | 单次改动巨大，Git diff 爆炸 | 单独开一个 PR 只做格式化，在 commit message 注明"no-op reformat"，便于 `git blame -w` |

---

## 六、交付物

- ✅ 本计划文档（`.trae/documents/project-overview-suggestions_plan.md`）
- 执行后将产出：
  - 干净的仓库目录结构
  - 统一的 `pyproject.toml` 打包配置
  - 一致的 Python 版本声明
  - 更清晰的 CI marker 机制
  - 完整的 `.gitignore`
