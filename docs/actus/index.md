# vools-actus（actus 子项目）{#A24}

> **子项目**：`actus`（动作引擎核心）
> **模块路径**：`vools.actus`
> **文档编号**：#A24
> **最后更新**：2026-10-19
> **配套规范**：[docs/03 动作规范](03-动作规范.md)（三层边界 / 分类体系 v2.0 / 生态层 / 协议统一）

---

## 简介

`vools-actus` 是工作流自动化与动作编排引擎，提供动作数据模型、执行器、
工作流调度、注册表、密钥管理、信任决策、安全扫描、沙箱环境，以及
跳板机文件传输（jump）等核心功能。

## 安装

```bash
pip install vools-actus
```

`pip install vools-actus` 自带 4 个基线 GUI 种子动作（calculator /
todo-list / text-editor / image-viewer，定义见 `vools/actus/actions/basics/*.actus.schema.md`）。

## 核心功能

### 1. 动作数据模型

```python
from vools.actus import Action, parse_cfg_from_file

action = parse_cfg_from_file("my_action.actus.schema.md")

# 或手动创建
action = Action(
    name="my-action",
    description="我的动作",
    version="1.0.0",
    entry="main",
    blocks={"main": {"language": "python", "content": "print('Hello from Actus!')"}},
)
```

### 2. 执行引擎

```python
from vools.actus import execute, preview

result = execute(action, params={"input": "value"})  # 执行动作
preview(action)                                       # 预览（不实际执行）
```

### 3. 工作流引擎

```python
from vools.actus import Workflow, run_workflow

workflow = Workflow(
    name="my-workflow",
    steps=[
        {"id": "step1", "action": "action1", "depends": []},
        {"id": "step2", "action": "action2", "depends": ["step1"]},
    ],
)
result = run_workflow(workflow)
```

### 4. 注册表

```python
from vools.actus import build_registry, search_registry

registry = build_registry("/path/to/actions")  # 构建动作注册表
results = search_registry(registry, "search term")
```

### 5. 密钥管理

```python
from vools.actus import set_key, get_key, resolve_secrets

set_key("api_key", "secret-value")
api_key = get_key("api_key")
resolved = resolve_secrets(action)
```

### 6. 信任决策

```python
from vools.actus import decide, check_permissions

decision = decide(action, context={"user": "admin"})
permissions = check_permissions(action, required=["read", "write"])
```

### 7. 安全扫描

```python
from vools.actus import SecurityScanner

scanner = SecurityScanner()
report = scanner.scan(action)
```

### 8. 沙箱环境

```python
from vools.actus import prepare, sandbox_env

sandbox = prepare(action)
with sandbox_env(sandbox):
    result = execute(action)
```

## 跳板机文件传输（jump）

`vools.actus.jump` 提供跳板机（jump host）文件传输的纯 Python 实现，
供 `.actus.md` 动作与测试共用：

| 公开 API | 说明 |
|----------|------|
| `push` | 推送到远端（默认 paramiko，可回退 ssh 命令） |
| `pull` | 从远端拉取 |
| `sync` | 双向同步（method 语义同 push，默认 paramiko） |
| `compute_sync_plan` | 计算同步计划（方向 / 策略） |

安全特性：

- 远端命令统一经 `shquote` 做 POSIX 单引号安全引用，杜绝注入。
- 远程路径恒用 POSIX 分隔符（`remote_join`），避免 Windows 反斜杠导致 scp/sync 静默失败。
- `_is_safe_relpath` 拒绝穿越型相对路径（`..` / 绝对路径 / 盘符）。

## 动作定义格式

- **新格式（推荐）**：`.actus.schema.md`（YAML front-matter 元数据 + 带 `tag` 的代码块）
- **旧格式（向后兼容）**：`.actus.md`（`#!cfg` JSON 内联元数据块）

两种后缀都进引擎索引、过同一套校验（`indexer.ACTION_SUFFIXES`）。

### 三层动作边界

| 层 | 位置 | 分发方式 |
|----|------|---------|
| 基座种子动作 | `vools/actus/actions/` | 随 wheel（pip 装上即有） |
| 用户项目动作 | `<ACTUS_REPO_ROOT>/actions/` | Git 仓（索引优先） |
| 社区仓动作 | `curator.list_default_repos()` 指向的远程仓 | Git + 策展发现 |

### 分类体系 v2.0（front-matter）

```yaml
kind: exec                          # 执行类型（未知值打回）
purpose: [transform, ai]            # 用途，多值跨维度
industry: [general, devops]         # 行业，多值
trigger: [manual, webhook]          # 主触发声明
context_applies: ["chrome.exe"]     # 适用上下文（Quicker 式）
license: mit                        # 许可证
pricing: free                       # 定价（gated 付费预留）
```

按维度查询：

```python
from vools.actus import filter_by_dimension
filter_by_dimension('purpose', 'transform')   # → [action_id...]
```

详见 [docs/03 §2 分类体系](03-动作规范.md)。

## CLI 使用

```bash
actus run my_action.actus.schema.md
actus preview my_action.actus.schema.md
actus check my_action.actus.schema.md
actus registry build /path/to/actions
actus workflow run my_workflow.yaml
```

### 退出码语义（脚本判定依据）

| 退出码 | 含义 | 触发场景 |
|---|---|---|
| **0** | 成功 | 命令执行完成，且业务判定成功：`status ∈ {ok, success, modified, skipped, noop, published}`；纯查询/无 `status` 的返回体（如记录列表）视为成功 |
| **1** | **业务失败** | 命令**已经跑起来**，但结果判定失败：动作校验不通过、执行 `failed`、`refused`（例：未配置 `ACTUS_VAULT_KEY` 时写保险库被拒）、`not_found`、以及被 `main()` 兜底捕获的内部异常 |
| **2** | **用法错误** | `argparse` 在**执行前**拒绝：未知子命令/未知参数/缺少必需参数/非法枚举值（如 `--level weird`） |

**为什么用法错误用 2 而不是 1**：这是 POSIX/GNU 惯例 —— `argparse` 的
`parser.error()` 本身就以 2 退出，`git`、`grep`、`python` 等也如此。
把"命令写错了"（2）与"命令跑了但业务失败"（1）分开，脚本才能区分
**该修调用方式**还是**该处理业务失败**，两者的人工处置完全不同。

判定逻辑的单一真源是 `vools.actus.errors.is_failure_status()`：CLI 的
`_out_result()` 与 MCP 的 `text_result()` 共用同一份，不各写一套。

### 机器可读输出（`--json`）

`actus --json <cmd>`（或 `actus <cmd> --json`）输出**扁平** JSON
（`{status, ...}`，不套 `data` 层），形状与 MCP 工具返回一致，便于脚本解析。
已接线：`search`、`registry build|validate|info`、`visibility get|set`。
不加 `--json` 时保持人类可读文本 —— 两种模式互不影响。

## 路径契约（可移植性）

- 仓库资源（`contracts/`、`actions/`、`_meta/`）随宿主仓库走，**不要用
  `__file__` 直接推导**。
- 需要"仓库根"的模块统一遵守 `ACTUS_REPO_ROOT` 环境变量契约：
  环境变量优先，兜底用本文件上三级目录（standalone 时正确）。
- 打开仓库/用户文件必须显式 `encoding="utf-8"`（Windows 中文系统默认
  cp936/GBK，避免 `UnicodeDecodeError`）。

## 依赖

- Python >= 3.7（publisher/repo/scattered/semver/sigma 用 PEP 563）
- vools >= 0.7.0
- vools-bridges >= 0.7.9（引擎加载任何动作都要走 `vools.bridge.md.*`）

## 许可证

MIT
