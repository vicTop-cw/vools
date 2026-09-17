# vools-actus — Actus 动作引擎核心

工作流自动化与动作编排引擎，提供动作数据模型、执行器、工作流调度、注册表、密钥管理、信任决策、安全扫描、沙箱环境等核心功能。

## 安装

```bash
pip install vools-actus
```

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
