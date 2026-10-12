# vools-pyk CHANGELOG

> 文档即实现：本文件记录 vools-pyk 每个版本的**所有**用户可见变更。
> 新增功能、破坏性变更、BUG 修复都必须写进这里，否则视为遗漏文档。

---

## 0.1.1 — 2026-10-12

### 新增
- **CLI 执行通道**（`vools.pyk.look_upon`）：
  - 模块级 `cli_execute(payload, timeout_sec, capture)` —— 用 Python subprocess 调用外部 CLI。
  - `LookUpon.execute_task` 在 payload 含 `cli` 子 dict 时自动走 CLI 路径（跳过 `task_function`）。
  - **无语言枚举限制**：`task_type` 是 `VARCHAR(32)` 且无 CHECK 约束；
    Scala / Java / R / Go / Node / Shell / SQL / Python / Julia / Ruby / Perl / PHP /
    dotnet / spark-submit 等都可自由填。
  - `LANGUAGE_DEFAULT_CMD`：语言 → 默认命令前缀映射。
  - `LANGUAGE_EXTENSIONS`：语言 → 脚本扩展名映射（内联 script 时用）。
  - `_detect_language(task_type)`：大小写不敏感，支持别名（`PY`→python、`SCALA`→scala、`SQL`→sql）。
  - `_find_executable(prefix)`：PATH 查找，Windows 自动补 `.exe`/`.bat`/`.cmd`。
  - 支持的 payload['cli'] 字段：`lang` / `cmd` / `args` / `script` / `script_path` /
    `workdir` / `env` / `stdin` / `stdin_from_value` / `timeout_sec` / `capture` / `shell` / `check`。
  - 找不到解释器时**明确报错**，不静默跳过。
  - CLI 结果（stdout / stderr / exit_code / duration_ms / cmd）写入任务 `back_info`。
- **测试**：`TestCliExecute`（8 条）：cmd 调用、lang 推断、内联 script、task_type 归一化、
  未知语言报错、缺失解释器报错、workdir+env 生效、stdin_from_value、超时触发。

### 变更
- `look_upon.__all__` 新增 `cli_execute` / `LANGUAGE_DEFAULT_CMD` / `LANGUAGE_EXTENSIONS` /
  `_detect_language` / `_find_executable`。
- `docs/LOOKUPON.md` 新增 §8「CLI 执行通道（无语言枚举限制）」，后续章节顺延。
- `docs/CHANGELOG.md` 新增本条目。

---

## 0.1.0 — 2026-10-12

### 新增
- **独立分发包**：`vools-pyk` 从 `vools` 核心库剥离，通过 PyPI 独立发布。
- **namespace 合并**：安装后以 `vools.pyk` 命名空间包合并进 `vools`。
- **懒加载架构**：顶层 `vools.pyk` 不再在 import 时拉起 pyspark；
  子模块通过 `__getattr__` 延迟加载，无 pyspark 时抛 `AttributeError`。
- **`install_patch()`**：把 pyk 扩展（`show_ex` / `unique_by` / `grouping_sets` 等）
  monkey-patch 到原生 `DataFrame` / `SparkSession` / `Column`，幂等。
- **`is_available()`**：快速判断环境是否有 pyspark。
- **LookUpon 任务调度**（`vools.pyk.look_upon`）：
  - 32 列 PostgreSQL 任务表（含 `deps` / `deps_task_tables` / `payload` / `tags` 等）
  - 6 状态机（`PENDING` / `LOCKED` / `RUNNING` / `COMPLETED` / `FAILED` / `RETRY_PENDING`）
  - 同表依赖（`deps INTEGER[]`）与**跨表依赖**（`deps_task_tables JSONB`）
  - 可配置重试（`max_retries` / `retry_delay_min`）
  - Worker 竞争锁 + 事务 + 乐观锁（`version` 列）
  - 超时回滚 / 过期锁回收（`clean_stale_locks`）
  - 取消请求（`cancel_requested`）
  - 优先级调度（`priority` 列）
  - 常驻运行（`run_until_done_resident`）
  - 模块级函数：`add_tasks` / `query_tasks` / `init_tasks` / `run_until_done` /
    `reset_tasks` / `update_failed_to_pending` / `run_doneEx` / `get_replaced_sql`
  - 异常：`TaskFunctionError` / `TaskAlreadyLocked` / `MaxRetriesExceeded`
- **`ConditionBuilder`**（`vools.pyk.cond`）：`CASE WHEN` / 条件构造器
  （`case` / `cases` / `when` / `whens` / `otherwise`）。
- **`configs`**：`secret_key` / `encrypt_secret` / `decrypt_secret` /
  `pg_credentials` / `load_config` / `get_spark_conf` 等。
- **`vicTools`** 聚合类（`vools.pyk.tools`）：一站式工具入口。
- **`vicTableInfo`**（`vools.pyk.tb`）：Hive 表元数据（getCols / get_partitions…）。
- **`vicCompare`**（`vools.pyk.compare`）：DataFrame 比对。
- **`vicPostgreSupport`**（`vools.pyk.postgre`）：PostgreSQL 辅助。
- **文档**：`README.md`、`docs/LOOKUPON.md`、`docs/MODULES.md`。

### 变更
- 原 `vools` 里的 `vools/vx.py`（旧版 LookUpon）拆分为独立 `vools.pyk.look_upon`。

### 修复
- BUG-33：LookUpon 表 schema 从早期版本扩展为 32 列（支持跨表依赖、payload、
  tags、cancel_requested 等）。

### 兼容
- Python 3.6 – 3.13。
- pyspark >= 2.4.3。
- `import vools.pyk` 在无 pyspark 环境下不报错（仅 `is_available()` 返回 False）。

---
