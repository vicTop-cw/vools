# vools-actus 公共 API 文档

> **子项目**：`actus`（动作引擎核心）
> **模块路径**：`vools.actus`
> **文档编号**：#A26
> **最后更新**：2026-11-11
> **配套文档**：`docs/actus/03-动作规范.md`（动作分类体系与元数据规范）、`actus/docs/DEVELOPMENT_STANDARDS.md`（开发操作规范）
> **说明**：本文档按代码事实编写，覆盖 actus 公共 API 面（resolver / cli / validate / indexer / executor / model / errors / 公共导出）。

---

## 1. 模块总览

```
vools.actus
├── resolver.py      目标解析层（target 六形态 + 扩展入参解析）
├── indexer.py       索引层（扫描 / 构建 / 加载 / 查询）
├── validate.py      校验层（action 校验 / 图校验 / 分类校验）
├── cli.py           命令行入口（main / 子命令分发）
├── executor.py      执行层（kind 分发 / 参数注入 / 幂等）
├── model.py         动作数据模型（Action / 双 front-matter 解析）
├── errors.py        错误约定（ActionError）
├── scattered.py     散路径动作解析（scattered 形态前置分流）
└── constants.py     分类体系常量（KIND_LEVELS 等）
```

**资源路径约定**：仓库资源（`contracts/`、`actions/`、`_meta/`）随宿主仓库走，
**禁止**用 `__file__` 直接推导这些路径；需要仓库根时使用 `ACTUS_REPO_ROOT` 环境变量约定（详见 `actus/README.md`）。

---

## 2. 目标解析层（resolver.py）

### 2.1 `ResolvedTarget`

解析结果对象（`resolver.py:42`）。字段以解析结果为准，包含目标类型、来源、动作 id、路径等。

### 2.2 `resolve_target(target, allow_hosts=None, expect_digest=None, expect_signature_key=None) -> ResolvedTarget`

核心目标解析函数（`resolver.py:223`）。

- **⚠️ 可能写盘**：action_id / md5 分支不建索引（缺失时内存扫描，`write_cache=False`）；**URL 分支会下载到磁盘**（远程动作源解析固有行为，白名单 / 指纹 / 签名由调用方负责）。
- **支持六形态**（优先级链，本地优先）：

| 形态 | 判定 | 说明 |
|------|------|------|
| `path` | 本地路径存在 | 本地动作文件，最优先 |
| `id` | `_is_action_id()` | 已知动作 id（查 `_known_index()`） |
| `name` | `_lookup_by_name()` | 按动作名模糊命中（多候选时抛歧义） |
| `md5` | `_is_hex32()` | 按动作文件 md5 精确匹配（`_lookup_by_md5()`） |
| `url` | `_is_url()` | 远程动作源；需 `allow_hosts` 白名单 + 指纹/签名校验（`_assert_host_allowed` / `_download_url`） |
| `scattered` | `scattered.is_scattered_path()` 前置分流 | 散路径动作（由 CLI 在调用 resolver 前分流） |

- **错误约定**：非法输入抛 `ActionError('action_invalid')`；路径不存在抛 `ActionError('action_not_found')`。
- **URL 安全**：`allow_hosts` 为空列表表示禁止所有远程（CLI 的 `info/preview/validate` 明确传 `allow_hosts=[]`）。

### 2.3 `find_action_file(action_id, actions_root) -> Optional[str]`

按 id 在动作根下查找动作文件（`resolver.py:383`）。**按解析后的 `meta['id']` 比对，格式无关**（新格式 YAML front-matter 与旧格式 `#!cfg` 均命中）。统一了 resolver / author / dependency 三套历史查找逻辑。

### 2.4 `resolve_params_extended(params_str, allow_hosts=None, max_action_depth=3) -> dict`

扩展入参解析器（`resolver.py:409`）。支持七种入参来源：

| # | 来源 | 说明 |
|---|------|------|
| 1 | JSON 字面量 | 原逻辑，如 `{"a": 1}` |
| 2 | `@file` | 本地 JSON 文件 |
| 3 | `-` | stdin |
| 4 | `@https://…*.json` | URL 下载 JSON（走白名单） |
| 5 | `@action:<action_id>` | 递归引用另一动作的产出参数 |
| 6 | 空 / `{}` | 空参数，返回 `{}` |
| 7 | 非法输入 | 抛 `ActionError` |

- 递归引用默认最大深度 3（`max_action_depth=3`），含环检测。

### 2.5 CLI 侧入参入口

`cli._parse_params(s)`（`cli.py:1902`）为 CLI 主入口，仅支持 JSON 字面量 / `@file` / `-` 三种；`run` 子命令走 `resolve_params_extended` 获得完整七种能力。

---

## 3. 索引层（indexer.py）

| 函数 | 位置 | 说明 |
|------|------|------|
| `scan_actions(actions_dir=None, validate=True, ...)` | `indexer.py:144` | 扫描动作目录，返回动作字典（可带校验） |
| `build_index(actions_dir=None, meta_dir=None, ...)` | `indexer.py:301` | 构建并落盘 `_meta/actions.index.json` |
| `load_index(meta_dir=None, build=True) -> dict` | `indexer.py:475` | 加载索引；缺失且 `build=True` 时自动构建 |
| `get_action(action_id, actions_dir=None, ...)` | `indexer.py:522` | 按 id 精确匹配 `scan_actions` 结果取动作 |
| `filter_by_dimension(dimension, value, meta_dir=None)` | `indexer.py:536` | 按分类维度（kind/purpose/...）过滤 |

**索引结构**（`build_index` 产物，`indexer.py:403-446`）：

- `brief`：含 `name` / `md5` / `kind` / `languages`；
- 反向索引：`by_name` / `by_md5` / `by_kind`。

**扫描根解析**（`indexer._action_roots`）：显式传 `actions_dir` 只扫该目录（测试/单仓场景）；缺省 = 用户项目 `actions/` + 包内种子目录（去重保序）。**文件后缀双轨**：`.actus.schema.md`（新格式 YAML front-matter）与 `.actus.md`（旧格式 `#!cfg`）都进索引、都过同一套 validate 管线。

---

## 4. 校验层（validate.py）

### 4.1 主入口

| 函数 | 位置 | 说明 |
|------|------|------|
| `validate_action(action, check_index=True) -> List[str]` | `validate.py:287` | 单动作全量校验，返回错误列表 |
| `validate_graph(actions) -> None` | `validate.py:1258` | 动作图整体校验（不合法时抛异常） |
| `analyze_graph(actions) -> dict` | `validate.py:1317` | 动作图分析（返回结构化 dict） |
| `load_and_validate(path) -> Action` | `validate.py:1424` | 读取 + 校验一条路径 |
| `is_valid(errors) -> bool` | `validate.py:83` | 错误列表是否为空 |
| `split_validation(errors) -> (errors, warnings)` | `validate.py:63` | 拆分硬错误与软警告 |

### 4.2 专项校验函数

| 函数 | 位置 | 校验内容 |
|------|------|---------|
| `check_md5_consistency(action, meta_dir=None)` | `validate.py:217` | md5 与索引一致性 |
| `check_link_target(action, check_index=True, ...)` | `validate.py:259` | link 目标的指向合法性 |
| `check_classification(meta)` | `validate.py:464` | 分类体系字段合法性 |
| `classification_notices(meta)` | `validate.py:485` | 分类软警告 |
| `check_entry_block(action)` | `validate.py:590` | `kind=exec` 强制 entry 块 |
| `check_block_languages(action)` | `validate.py:613` | 块语言声明 |
| `language_notices(action)` | `validate.py:651` | 语言软警告 |
| `check_args_schema(meta)` | `validate.py:671` | 入参 schema |
| `check_triggers(meta)` | `validate.py:731` | 触发器（含 cron 表达式范围） |
| `check_secrets(meta)` | `validate.py:806` | 密钥声明 |
| `check_ai_meta(meta)` | `validate.py:851` | AI 元数据 |
| `check_platform(meta)` | `validate.py:885` | 平台声明 |
| `check_id_namespace(meta)` | `validate.py:911` | id 命名空间 |
| `check_usage_executable(meta)` | `validate.py:927` | 用途可执行性 |
| `resolve_test_binding(action)` | `validate.py:1013` | 测试绑定解析 |
| `check_trust_tests(action)` | `validate.py:1063` | 信任测试 |
| `check_self_contained(action)` | `validate.py:1091` | 自包含性 |
| `check_secrets_hardcode(action)` | `validate.py:1159` | 硬编码密钥 |
| `check_omega_gate(action)` | `validate.py:1207` | Ω-gate |
| `governance_notices(meta)` | `validate.py:1236` | 治理软警告 |
| `validate_schema_md(action)` | `validate.py:1442` | `.schema.md` 结构校验 |
| `check_schema_md_structure(body, meta=None)` | `validate.py:1541` | schema.md 结构专项 |
| `check_security(action)` | `validate.py:1593` | 安全扫描 |

---

## 5. 命令行层（cli.py）

- `main(argv=None) -> int`（`cli.py:115`）：统一入口，返回退出码。
- `_dispatch(args) -> int`（`cli.py:805`）：子命令分发。
- `_resolve_cli_target(raw)`（`cli.py:1858`）：内部调用 `resolve_target(raw, allow_hosts=[])`，**URL 明确拒绝**（供 `info/preview/validate` 使用）。

### 5.1 子命令一览

| 类别 | 子命令 |
|------|--------|
| **核心动作** | `scan` / `list` / `validate` / `info` / `preview` / `run` / `status` |
| **会话循环** | `loop`（`stop` / `status` / `list`） |
| **接入与生成** | `mcp` / `probe` / `dialog` / `config` / `scaffold` / `author` / `workflow` |
| **密钥与信任** | `vault`（`set` / `get` / `list` / `delete` / `rotate` / `rotate-kek` / `migrate`）、`keygen` / `sign` / `verify` / `approve` / `pending` |
| **注册表与仓库** | `registry`（`build` / `validate` / `info`）、`install` / `uninstall` / `publish` / `search` / `sync` / `list-installed` / `rollback` / `check-update`、`reg`（`add` / `remove` / `list`）、`private`（`list` / `add` / `remove`） |
| **多语言执行** | `runtimes` / `execute` |
| **记录与产物** | `records`（`list` / `export`）、`artifacts`（`list` / `cleanup`）、`export` / `replay` |
| **触发器与事件** | `triggers`（`add` / `list` / `status` / `remove`）、`events` |
| **治理与团队** | `team`（`create` / `add-member` / `remove-member` / `list`）、`visibility`（`get` / `set`）、`bug`（`list` / `report` / `stats`） |
| **验证与进化** | `omega`（`verify` / `template` / `learn` / `batch` / `format`）、`evolve` / `selfheal` |
| **运维辅助** | `webhook` / `project` / `project-mgmt` / `deps` / `dep-tree` / `desktop` / `viz` / `concurrency`（`status` / `set` / `reset` / `list`）/ `notify` / `health` / `cost` / `selfdrive` / `template` |

> 完整参数面以 `_build_parser()`（`cli.py:152`）为准。

---

## 6. 执行层（executor.py）

| 函数 | 位置 | 说明 |
|------|------|------|
| `execute(action_id, params=None, ...)` | `executor.py:313` | 动作执行主流程（按 kind 分发） |
| `new_exec_id() -> str` | `executor.py:64` | 生成执行 id |

**kind 分发**（与 `constants.KIND_LEVELS` 对齐，共 7 种）：

| kind | 执行语义 |
|------|---------|
| `exec` | 强制 entry 块，执行代码 |
| `link` | 链接目标转发 |
| `demo` | 演示展开 |
| `template` | 模板渲染 |
| `alias` | 别名转发 |
| `bundle` | 子动作集合 |
| `doc` | 文档动作 |

**执行管线**：参数注入（`_validate_params` / `_inject_params_into_body` / `_deep_merge_params`）→ 安全门（`_security_gate` / `_visibility_gate`）→ 环境注入（`_apply_env_injections` / `_sanitize_path_env`）→ kind 分支 → 记录（`record_gate`）。支持**幂等重放**（`_idempotent_*` 系列）。

---

## 7. 数据模型与动作规范（model.py / 03-动作规范.md）

### 7.1 数据模型

| 函数/类 | 位置 | 说明 |
|---------|------|------|
| `Action` | `model.py:40` | 动作对象模型 |
| `parse_cfg(body) -> dict` | `model.py:242` | 解析 `#!cfg` 内联 JSON |
| `parse_cfg_from_file(path) -> Action` | `model.py:289` | 按文件解析动作（双后缀） |
| `parse_action_from_schema_md(raw, path='') -> Action` | `model.py:414` | 解析 `.schema.md` 动作 |

### 7.2 动作文件形态

- **双 front-matter 设计**：区域 0（AIGC 合规声明，可省略）+ 区域 1（动作定义元数据，含 `id`/`name`/`kind` 等）；
- **后缀双轨**：`.actus.schema.md`（新格式，推荐）与 `.actus.md`（旧格式，向后兼容）；
- **核心原则**：单一 `.md` 文件 = 完全自包含的动作定义，无 JSON 文件、无外部 schema 引用；
- **分类体系 v2.0**：五维度（`kind` 单值必填、`purpose`/`industry`/`trigger` 多值、`context_applies` 可选），单一真源 `vools.actus.constants`，机器校验真源 `contracts/action.schema.json`；
- 详见 [docs/actus/03-动作规范.md](actus/03-动作规范.md)。

---

## 8. 错误约定（errors.py）

| 错误 | 位置 | 语义 |
|------|------|------|
| `ActionError` | `errors.py:62` | actus 统一异常基类 |

约定用法（DEVELOPMENT_STANDARDS 回归用例要求）：
- 非法输入 → `ActionError('action_invalid')`
- 路径/目标不存在 → `ActionError('action_not_found')`

---

## 9. 公共导出（__init__.py）

`vools.actus` 顶层导出按能力域聚合，主要分组：

| 能力域 | 导出符号 |
|--------|---------|
| executor | `execute` / `preview` / `new_exec_id` |
| validate | `validate_action` / `validate_graph` |
| trust | `decide` / `check_permissions` |
| vault | `Vault` / `set_key` / `get_key` / `delete_key` / `list_keys` / `resolve_secrets` |
| runtimes | `RuntimeRegistry` / `execute_block` / `get_available_runtimes` |
| workflow | `Workflow` / `WorkflowExecutor` / `DAGScheduler` / `run_workflow` |
| registry | `ActionRegistry` / `RegistryEntry` / `build_registry` / `search_registry` |
| indexer | `scan_actions` / `load_index` / `get_action` |
| records | `write_run_record` / `append_log` / `load_run_record` / `load_status` |
| omega | `verify_output` / `compute_output_fingerprint` |
| eventbus | `EventBus` / `EventType` / `get_event_bus` |
| sandbox | `prepare` / `sandbox_env` / `guard_write` / `cleanup` |
| scaffold | `scaffold_action` / `match_template` |
| trust_model | `TrustEvaluator` / `KeyManager` / `SignatureVerifier` / `ScopeEnforcer` |
| visibility | `VisibilityEngine` |
| security | `SecurityScanner` / `AuditLogger` / `SensitiveInfoDetector` |
| adapter | `AdapterSpec` / `CLIAdapter` / `HTTPAdapter` / `QuickerAdapter` / `MCPAdapter` |
| installer / evolution | `ActionInstaller` / `EvolutionEngine` |
| selfheal | `SelfHealingEngine` |
| template | `create_action_from_template` / `list_templates` |
| export / project | `export_history` / `ProjectOrchestrator` / `ProjectConfig` / `detect_and_init` / `export_project` / `import_project` |
| viz | `visualize_workflow` |

---

## 10. 开发约束速查（DEVELOPMENT_STANDARDS）

- **新增 target 形态**：写 resolver 优先级链 → 写回归用例（合法输入解析正确 / 非法输入抛 `action_invalid` / 路径不存在抛 `action_not_found`）→ 接入 CLI → 更新索引；优先级 `path > id > https`。
- **新增 kind**：注册 `KIND_LEVELS` → 更新 `contracts/action.schema.json` 枚举 → 写校验规则 → 落地 executor 分支 → 补种子动作与 `.sig` → 同步文档。
- **不许跳过回归用例**；CLI 测试子进程必须显式设置 `PYTHONPATH` 指向源码树（`actus/vools/`），避免 import 系统旧装。
- 详见 [actus/docs/DEVELOPMENT_STANDARDS.md](../actus/docs/DEVELOPMENT_STANDARDS.md)。
