# vools.actus — Actus 动作引擎核心

迁移自 Actus engine/actuscore/，提供完整的动作执行引擎。

## 核心模块

| 模块 | 能力 |
|------|------|
| `model` | 动作数据模型（Action）、配置解析 |
| `executor` | 动作执行器、预览、执行ID生成 |
| `workflow` | 工作流引擎、DAG调度、运行工作流 |
| `registry` | 动作注册表、搜索、构建索引 |
| `vault` | 密钥管理、密钥解析 |
| `trust` | 信任决策、权限检查 |
| `security` | 安全扫描、审计日志、敏感信息检测 |
| `sandbox` | 沙箱环境、写保护、清理 |
| `runtime` | 运行时注册、块执行 |
| `dependency` | 依赖解析、依赖图 |
| `adapter` | CLI/HTTP/Quicker/MCP 适配器 |
| `eventbus` | 事件总线、事件类型 |
| `evolution` | 进化引擎 |
| `selfheal` | 自愈引擎 |
| `installer` | 动作安装器 |
| `notify` | 通知管理 |
| `highlight` | 代码高亮 |
| `project` | 项目编排、导入导出 |
| `health` | 健康检查 |
| `webhook` | Webhook接收 |
| `triggers` | 触发器引擎、定时调度 |
| `intent` | 意图路由 |

## 使用示例

```python
from vools.actus import Action, execute, Vault

# 创建动作
action = Action(name="demo", command="echo hello", trust_level="low")

# 执行
result = execute(action)

# 密钥管理
Vault.set_key("api_key", "xxx")
key = Vault.get_key("api_key")
```
