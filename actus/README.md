# vools-actus — Actus 动作引擎核心

工作流自动化与动作编排引擎，提供动作数据模型、执行器、工作流调度、注册表、密钥管理、信任决策、安全扫描、沙箱环境等核心功能。

## 安装

```bash
pip install vools-actus
```

## 资源与路径（开发必读）

> 本模块已迁入 `vools.actus`，而仓库资源（`contracts/`、`actions/`、`_meta/`）随宿主
> 仓库走。**不要用 `__file__` 直接推导这些路径** —— 迁入后落点不再是原位置。
> 以下规则是实测总结，违反会在 Windows 中文系统上出现难查的崩溃或空索引。

### 1. `ACTUS_REPO_ROOT` 环境变量契约

所有需要"仓库根"的模块（`validate`、`adapter`、`desktop`、`indexer`、`cost`、
`omega_strong`、`records`、`scaffold`、`bugreport`、`calllog`）都应：

```python
root = os.environ.get('ACTUS_REPO_ROOT')      # 1. 环境变量优先
if root:
    return root
# 2. 兜底：本文件上三级（= vools/actus 子项目根，standalone 时正确）
return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

**为什么不能只用 `__file__`**：模块在 `vools/actus/vools/actus/<mod>.py`，
`dirname^2` 落在无意义的中间层（`.../vools/actus/vools`），不是任何项目根。
`dirname^3` 才是 vools/actus 子项目根。而 Actus 宿主模式下真正要的是
`ACTUS_REPO_ROOT/...`。**实测落点必须是真实项目根**，不能只看用了几个 `dirname`。

### 2. 打开仓库/用户文件必须显式 `encoding="utf-8"`

Windows 中文系统 `locale.getpreferredencoding(False)` = **cp936**（GBK）。默认
`open()` 读仓库提交的 UTF-8 文本（含中文注释/文案）会 `UnicodeDecodeError`。

```python
with open(path, encoding="utf-8") as f:      # 必须写 encoding
    data = json.load(f)
```

判据（按读的是什么文件）：
- **用户自建**配置（`mcp_servers.json`、`workflow.json`）→ **必须** UTF-8，用户可能在 UTF-8 环境生成
- **工具自产**产物（npm `package.json`）→ 恒 ASCII，可省
- **自己写自己读**（round-trip）→ 自洽，可省但建议仍写

### 3. `_shiki/node_modules` 取舍（已知、接受）

`vools/actus/_shiki/node_modules/`（约 14.3MB）**刻意不入 wheel**：体积过大。
- **仓库内**：Shiki 完整可用，`check_shiki_available()=True`，真渲 ANSI 色码
- **pip 安装态**：`node` 缺 `node_modules` → **优雅降级**为回退着色（`shiki available=False`）
- 这是功能取舍，不是缺陷。若要安装态也全量 Shiki，需预打包单文件 bundle（esbuild）

### 4. `contracts/` 与 `schemas/` 的落点

- `contracts/` 保留在宿主仓库（`ACTUS_REPO_ROOT/contracts/`），**不在 wheel 内**
- `vools/actus/schemas/*.json` 是打包进来的**可移植副本**，供安装态回退
- `pyproject.toml` 的 `package-data "vools.actus"` 已包含 `_shiki/*.mjs`、
  `_shiki/*.json`、`schemas/*.json` 等资源；`templates/*`、`static/*`、
  `config.template.py` 三条 glob **指向不存在的路径**（0 文件），保留无害但已过时

## 核心功能

### 1. 动作数据模型

```python
from vools.actus import Action, parse_cfg

# 从文件解析动作
action = parse_cfg_from_file("my_action.actus.schema.md")

# 或手动创建
action = Action(
    name="my-action",
    description="我的动作",
    version="1.0.0",
    entry="main",
    blocks={
        "main": {
            "language": "python",
            "content": "print('Hello from Actus!')"
        }
    }
)
```

### 2. 执行引擎

```python
from vools.actus import execute, preview

# 执行动作
result = execute(action, params={"input": "value"})

# 预览执行（不实际执行）
preview(action)
```

### 3. 工作流引擎

```python
from vools.actus import Workflow, run_workflow

# 定义工作流
workflow = Workflow(
    name="my-workflow",
    steps=[
        {"id": "step1", "action": "action1", "depends": []},
        {"id": "step2", "action": "action2", "depends": ["step1"]},
    ]
)

# 执行工作流
result = run_workflow(workflow)
```

### 4. 注册表

```python
from vools.actus import ActionRegistry, build_registry

# 构建动作注册表
registry = build_registry("/path/to/actions")

# 搜索动作
results = search_registry(registry, "search term")
```

### 5. 密钥管理

```python
from vools.actus import Vault, set_key, get_key

# 设置密钥
set_key("api_key", "secret-value")

# 获取密钥
api_key = get_key("api_key")

# 解析动作中的密钥
resolved = resolve_secrets(action)
```

### 6. 信任决策

```python
from vools.actus import decide, check_permissions

# 信任决策
decision = decide(action, context={"user": "admin"})

# 权限检查
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
from vools.actus import prepare, sandbox_env, guard_write

# 准备沙箱
sandbox = prepare(action)

# 在沙箱中执行
with sandbox_env(sandbox):
    result = execute(action)
```

## 动作定义格式

支持两种格式：

### 1. 新格式：`.actus.schema.md`

```markdown
---
name: my-action
description: 我的动作
version: 1.0.0
entry: main
---

# 我的动作

```python #!run tag=main
print("Hello from Actus!")
```
```

### 2. 旧格式：`.actus.md`

```markdown
# 我的动作

```python #!run tag=main
print("Hello from Actus!")
```
```

## CLI 使用

```bash
# 执行动作
actus run my_action.actus.schema.md

# 预览动作
actus preview my_action.actus.schema.md

# 检查依赖
actus check my_action.actus.schema.md

# 构建注册表
actus registry build /path/to/actions

# 运行工作流
actus workflow run my_workflow.yaml
```

## 依赖

- Python >= 3.6
- vools >= 0.7.0

## 许可证

MIT
