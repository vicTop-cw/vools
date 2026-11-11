# vools-actus 本机已验证工具资产盘点（assets-inventory）

> 盘点日期：2026-11-11
> 依据：`actus/vools/actus/future_plan.txt` §2「主线：本机存量资产迁移闭环」与 §4 阶段 0 出口判据（`docs/assets-inventory.md` 盘点 ≥ 10 项）
> 范围：本机（Windows 11）实际存在且已验证的工具资产，登记**核心逻辑位置 + 既有测试路径**；未实际存在的候选对象单独标注为缺口，不虚计条目。

---

## 1. 阶段 0 出口判据对照

| 判据（future_plan §4 阶段 0） | 本文件达成情况 |
|---|---|
| 格式文档（最小字段集冻结） | ✅ 已有（docs/47 系列，§3 规范问题清单 #1/#2/#4/#5/#8 等已落地） |
| 不做清单 | ✅ 已有（future_plan §5，docs 侧有记录） |
| `docs/assets-inventory.md` 盘点 ≥ 10 项 | ✅ 本文件第 2 节盘点 **14 项**本机已验证工具资产 |
| 规范问题清单逐条修订完成 | §3 清单 10 条中 8 条 ✅ 落地，2 条 🔶（#7 deps 语义、#10 分类体系），见第 4 节 |

**盘点要求核对**（future_plan §2）：登记「核心逻辑位置 + 既有测试路径」——第 2 节每条目均满足；「以实际存在为准」——git.ops、env_config 本机无实现，按缺口标注（第 4 节），不计入盘点条目。

---

## 2. 本机已验证工具资产盘点（14 项，≥10 达标）

| # | 资产 | 核心逻辑位置 | 既有测试路径 | 验证状态 |
|---|---|---|---|---|
| 1 | jump push/pull/sync（paramiko 跳板） | `actus/vools/actus/jump.py` | `actus/tests/test_jump_contracts_r58.py`、`test_jump_batch_guard.py`、`test_jump_paramiko_guard.py`、`test_jump_shell_quote.py` | 已实测（paramiko） |
| 2 | jump 动作封装（rhop 侧） | `rhop/vools/rhop/actions/jump.py` | `rhop/tests/test_actions.py` | 已验证 |
| 3 | vault 凭据治理 v1 | `actus/vools/actus/vault.py` | `actus/tests/test_vault_adapter_contracts.py`、`test_vault_roundtrip.py`、`test_vault_time_boundaries.py`、`test_vault_readonly_contracts.py`、`test_vault_master_migration.py`、`test_vault_cross_window.py`；`tests/actus/test_vault.py` | 已验证 |
| 4 | vault2 加固凭据治理（KEK 轮换/resolver/回放） | `actus/vools/actus/vault2.py` | `actus/tests/test_vault2_contracts_r32.py`、`test_vault2_contracts_r75.py`、`test_vault2_replay.py`、`test_vault_resolver_contracts_r92.py` | 已验证 |
| 5 | dll32 rc6plus 测试链（Windows 32 位子进程） | `dll32/vools/dll32/_lib/com/rc6plus.py`（包已构建 wheel `dll32/dist/vools_dll32-0.9.0-py3-none-any.whl`） | `dll32/tests/test_dll32_features.py`、`test_dll32_lowlevel.py`、`test_rc6plus_run.py`；`dll32/vools/dll32/tests/test_dll32.py` | 已验证 |
| 6 | rhop 任务系统（queue/store/daemon/sync/heartbeat/secrets/exec/cli） | `rhop/vools/rhop/task/`（13 模块 + 2 个 `__init__.py`：cli/config/daemon/errors/exec/heartbeat/local_runner/models/queue/secrets/sync/base + sqlite_store/pg_store） | `rhop/tests/test_task_cli.py`、`test_task_config.py`、`test_task_e2e.py`、`test_task_exec.py`、`test_task_queue.py`、`test_task_resilience.py`、`test_task_secrets.py`、`test_task_store.py`、`test_task_sync.py`、`test_heartbeat.py`、`test_heartbeat_hardening.py`、`test_local_runner.py`、`test_daemon_e2e.py` | 已验证 |
| 7 | rhop 在线传输通道（paramiko/SFTP） | `rhop/vools/rhop/transport/online.py`（+ `endpoint.py`/`selector.py`/`relay.py`） | `rhop/tests/test_sftp_live.py`（样板验收测试）、`test_transport.py`、`test_endpoint.py`、`test_relay.py` | 已实测 |
| 8 | actus probe 探测引擎 | `actus/vools/actus/probe/`（15 个 .py 模块） | `actus/tests/test_probe.py`、`test_probe_actions.py`、`test_probe_actions_contracts_r94.py`、`test_probe_all_exports.py`、`test_probe_parallel.py`、`test_probe_permissions_contracts_r50.py`、`test_probe_permissions_contracts_r97.py`、`test_probe_platform_contracts_r61.py`、`test_probe_platform_tools.py`、`test_probe_report_contracts_r96.py`、`test_probe_resources_contracts_r50.py`、`test_probe_resources_contracts_r97.py`、`test_probe_windows.py`、`test_cli_probe.py` | 已验证 |
| 9 | actus 动作校验链（indexer/validate/resolver/trust_model） | `actus/vools/actus/indexer.py`、`validate.py`、`resolver.py`、`trust_model.py` | `actus/tests/test_validate_contracts_r32.py`、`test_resolver_contracts_r100.py`、`test_index_invalidation_r10h.py`、`test_demo_indexing.py`、`test_vault_resolver_contracts_r92.py` | 已验证 |
| 10 | actus CLI | `actus/vools/actus/cli.py` | `actus/tests/test_cli_probe.py` 及 resolver/validate 的 CLI 合约测试 | 已验证 |
| 11 | vault2 KEK 审计链（崩溃矩阵） | `actus/tools/audit/kek_crash_matrix.py`、`verify_vault2_kek_step0.py`、`verify_vault2_kek_step1.py`、`verify_vault_kek_entry.py` | `actus/tests/test_kek_rotation_crash_matrix.py` | 审计脚本已验证 |
| 12 | rhop 配置/交互/加密封装 | `rhop/vools/rhop/config.py`、`interact.py`、`crypto.py`、`envelope.py`、`session.py`、`signer.py`、`integrity.py` | `rhop/tests/test_interact.py`、`test_crypto.py`、`test_envelope.py`、`test_session.py`、`test_signer.py`、`test_integrity.py`、`test_html_fernet.py` | 已验证 |
| 13 | rhop 文件同步/镜像/守护 | `rhop/vools/rhop/sync_folder.py`、`mirror.py`、`watch.py`、`daemon.py`、`compress.py` | `rhop/tests/test_sync_folder.py`、`test_mirror.py`、`test_watch.py`、`test_daemon_e2e.py`、`test_compress.py` | 已验证 |
| 14 | 资产池动作登记（14 动作，含 8 正式 + 6 testish） | `actus/_meta/actions.index.json`（schema_version 2.0.0，generated_at 2026-11-06T17:28:01+08:00） | 索引生成/校验链测试：`test_demo_indexing.py`、`test_index_invalidation_r10h.py` | 14 项 status=valid |

> 注：第 14 项为登记台账（资产池入口），正式资产与 testish 判定见第 3 节；盘点条目数以第 2 节 14 行为准。

---

## 3. 资产池动作 id 命名规范核查（14 动作）

### 3.1 判定规则（future_plan §3 #6 落地 → docs/47 §3.4）

- 命名空间规则：`check_id_namespace` 强制两段点分小写（如 `jump.push`、`git.ops`）；
- **测试味 id 排除**：indexer 的 `asset_pool` 对含 `test/generated/foo/example` 等测试味片段的 id 置 `excluded`（kind=demo 等豁免）。

### 3.2 14 动作 id 明细与归属

| id | kind | trust | asset_pool | 归属判定 |
|---|---|---|---|---|
| actus.basics.calculator | exec | sandbox | included | ✅ 正式资产 |
| actus.basics.calculator.demo | demo | sandbox | included | ✅ 正式资产（kind=demo 豁免） |
| actus.basics.image_viewer | exec | sandbox | included | ✅ 正式资产 |
| actus.basics.image_viewer.demo | demo | sandbox | included | ✅ 正式资产（kind=demo 豁免） |
| actus.basics.text_editor | exec | sandbox | included | ✅ 正式资产 |
| actus.basics.text_editor.demo | demo | sandbox | included | ✅ 正式资产（kind=demo 豁免） |
| actus.basics.todo_list | exec | sandbox | included | ✅ 正式资产 |
| actus.basics.todo_list.demo | demo | sandbox | included | ✅ 正式资产（kind=demo 豁免） |
| actus.test.foo | template | trusted | included | ⚠️ 测试味 id（含 `test`）——应排除，当前 included 为索引不一致 |
| actus.generated.probe | exec | sandbox | excluded | ✅ 已排除（reason=testish_id，docs/47 §3.4） |
| actus.generated.zh | template | trusted | included | ⚠️ 测试味 id（含 `generated`）——应排除 |
| actus.generated.zhdocsb | template | trusted | included | ⚠️ 测试味 id（含 `generated`）——应排除 |
| actus.generated.zhzh | template | audit | included | ⚠️ 测试味 id（含 `generated`）——应排除 |
| actus.generated.zhzhai | template | trusted | included | ⚠️ 测试味 id（含 `generated`）——应排除 |

### 3.3 核查结论

1. **正式资产 8 个**：`actus.basics.*`（4 exec + 4 demo，kind=demo 豁免保留 included），id 命名符合 `check_id_namespace`（两段点分小写）且无测试味片段。
2. **测试/生成态 6 个**：`actus.test.foo` + `actus.generated.*`（probe/zh/zhdocsb/zhzh/zhzhai）。按 docs/47 §3.4 应全部置 `asset_pool=excluded`；
   实测仅 `actus.generated.probe` 已 excluded（reason=testish_id），**其余 5 个仍为 included**，与「indexer asset_pool 排除测试味 id」落地声明不一致 → 判定为**索引不一致（历史遗留，本轮生成后未按新规则重跑）**。
3. **处置建议**：
   - 本盘点**不将 6 个 testish id 计入正式资产**，第 2 节第 14 项的正式资产口径为 8/14；
   - 修正动作：重跑 indexer 使 5 个误 included 的 testish id 转为 `excluded`（probe 的 reason 文案作为模板）；
   - 6 个 testish 动作文件位于 `actus/actions/*.actus.md`（根级，非 `vools/actus/actions/`），可作为迁移/清理候选。

---

## 4. 候选迁移对象与缺口标注（以实际存在为准）

future_plan §2 首批候选 5 项，本机核对结果：

| 候选 | 本机实现 | 说明 |
|---|---|---|
| jump push/pull/sync | ✅ 存在 | 见第 2 节 #1/#2，paramiko 已实测 |
| vault 凭据治理 | ✅ 存在 | 见第 2 节 #3/#4（vault + vault2） |
| dll32 rc6plus 测试链 | ✅ 存在 | 见第 2 节 #5，wheel 0.9.0 已构建 |
| git.ops 建仓 | ❌ 未实现 | 全仓未检索到 git_ops/gitops 模块或动作文件；作为阶段 1 待建候选，不计入盘点 |
| env_config | ❌ 未实现 | 全仓未检索到 env_config 模块/动作；future_plan 已注明「需先修自包含问题」，当前无实体，不计入盘点 |

**规范问题清单剩余项**（阶段 0 出口判据第四项）：
- #7 deps 语义写入 docs/47 §5：🔶 未完全落地（引擎层依赖图校验沿用 analyze_graph，编排验收未强制）；
- #10 分类体系 v2.0 保留（docs/03 §2.6 反向索引）：🔶 分类字段后置不阻塞，不做清单已记录。

---

## 5. 结论

- 本文件盘点**本机已验证工具资产 14 项**（≥10 项出口判据达标，见第 2 节）；
- 资产池 14 个动作中正式资产 **8 个**，测试/生成态 **6 个**（其中 5 个应排除未排除，属索引不一致，待重跑 indexer 修正，见第 3 节）；
- 候选迁移对象 git.ops、env_config 本机无实现，已按缺口标注（见第 4 节），不虚计盘点条目。
