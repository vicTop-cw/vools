# API 收敛评审备料（R110，统帅轮-15时）

> 性质：**只备料，不拍板不擅自改**。供主人决策 API 收敛口径时参考。
> 背景：COVERAGE_AUDIT_R105 指出 9 个零覆盖公开函数疑似「内部工具公开面过宽」，
> 14时 新增 Action property 对称性观察。

## 一、候选 A：内部工具升 `_` 前缀（缩小维护承诺面）

> **16时 定案（grep 调用面分析）**：8 个待查函数中 7 个**零外部调用**（确认降级候选），
> 1 个（intent.get_default_router）被 mcp_server.py 调用（**保留公开**）。
> grep 口径为字符串级（含误报空间），但「有外部调用者」的判据方向足够扎实。

| 函数 | 产品内调用点分析 | 降级建议 |
|---|---|---|
| model.net_connect / net_listen | Action property（docs/46 安全契约读取面）——**有外部消费语义**（sandbox/executor 判定网络权限时应读它） | ⚠️ 不建议降级——安全面 property，**该补测**（14时 已补锚定默认方向） |
| validate.dfs / dfs_cycle | validate.py 内部图算法 | ✅ 建议降级 `_dfs`/`_dfs_cycle`（若外部确无引用） |
| scattered.dfs | scattered.py 内部图算法 | ✅ 同上 |
| model.net_* 之外的 reserved_env | Action property（安全面） | ⚠️ 同 net_*，不建议降级 |
| catalog.union | **零外部调用（定案）** | ✅ 可降级 |
| adapter.replacer | **零外部调用（定案）** | ✅ 可降级 |
| cost.alert_budget_if_over | **零外部调用（定案）** | ✅ 可降级 |
| intent.get_default_router | **被 mcp_server.py 调用（定案）** | ⛔ 保留公开（MCP 协议面消费） |
| selfdrive.strong_enabled | **零外部调用（定案）** | ✅ 可降级 |
| platform_tools.is_capability_item | **零外部调用（定案）** | ✅ 可降级 |
| vault.default_meta_dir | **零外部调用（定案）** | ✅ 可降级（薄包装） |
| vault2.default_vault_dir | **零外部调用（定案）** | ✅ 可降级（薄包装） |

**降级操作注意**：改 `_` 前缀要同步 `__all__`（若有）与全部产品内调用点，
且跑全量基线确认零回归（DEVELOPMENT_STANDARDS：签名变更必有回归验证）。

## 二、候选 B：Action 便捷读取面对称性

现状（14时 实测）：`id` / `trust` / `entry` 有 property；`version` / `name`
没有（测试被迫 `meta['version']` 直读）。

* 方案 B1（补 property）：加 `version` / `name` property，与既有三兄弟对齐；
  风险极低（纯增量），收益是读取面一致。
* 方案 B2（不动）：维持现状，测试直接 meta 读——零成本但不对齐。
* 建议 B1（两行 property + 无破坏面）。

## 三、拍板动线

主人拍板其一：
- 「A 表按建议执行」→ 下一轮逐函数降级 + 回归
- 「先查完 🔍 项再定」→ 下轮补齐调用面分析
- 「B1 执行」→ 加两个 property + 测试
- 「全部不动」→ R105 报告把相关函数改判「公开面维持，补测排期」
