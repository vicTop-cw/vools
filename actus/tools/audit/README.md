# tools/audit —— 可复跑的审计证据（已入库）

这些脚本是 **15 轮审计攒下来的可复跑证据**：每条"某功能是假的 / 某契约被破坏"的结论，
都能用这里的脚本在**临时目录隔离**下重新跑出来。

> **历史教训**：它们原先放在 `actus/build/audit/`，而仓库根 `.gitignore` 有 `build/`，
> 于是 **57 个脚本 0 个入库** —— 换台机器 / 在 CI 上都拿不到，"可复跑的证据"实际不可复现。
> 现在迁到 `actus/tools/audit/`（未被忽略），**新脚本放这里天然被跟踪**。

## 怎么跑

```bash
cd /path/to/vools/actus
python tools/audit/<script>.py            # 大多数直接跑
python tools/audit/readonly_name_writes.py --depth 3 --json ro.json
python tools/audit/desktop_smoke.py
```

共同约定：**全部在 tmp 隔离**（`HOME` / `ACTUS_META_DIR` / `ACTUS_REPO_ROOT` 指向临时目录），
不写真实 `~/.actus`、不改产品代码。

## CI 里用到哪些

| 脚本 | CI 用途 |
|---|---|
| `readonly_name_writes.py` | `guards` 作业的 AST 扫描（**告警级**，写 Job Summary） |
| `ci_readonly_summary.py` | 把上一步 JSON 渲染成 Job Summary 的 Markdown |
| `desktop_smoke.py` | desktop smoke 的本地版（CI 用等价的内联版本，避免依赖 | 的额外安装差异） |

## 脚本清单（一句话说明）

| 脚本 | 作用 |
|---|---|
| `accept_runtime_notes.py` | 验收：runtime: 提示不算动作校验失败 —— 裸仓库四步（全 Python，免 shell 引号地狱）。 |
| `audit_doc_claims.py` | 扫描「文档/注释声称有 actus CLI/MCP 入口，但实际不存在」的清单。 |
| `audit_registry_omega.py` | 审计 registry.py / omega_strong.py：反例实测（全 tmp 隔离，不碰真实 ~/.actus）。 |
| `audit_registry_readonly_cli.py` | 补充证据：load_* 读语义零写盘快照 + CLI registry validate 假校验。 |
| `audit_unused_exports.py` | `__all__` 导出但无跨模块引用的扫描（只看校验/安全相关模块）。 |
| `audit_validation_candidates.py` | 第三轮：候选函数的全部引用行（产品 / 测试），带行文本用于区分注释/导出/真实调用。 |
| `audit_validation_refs.py` | 第二轮：统计"裸引用"（表驱动/动态接线）与真实调用，区分死代码 vs 动态接线。 |
| `audit_validation_wiring.py` | 审计：枚举校验/验证类函数并统计真实调用方（只读，输出表格原料）。 |
| `audit_wiring_categories.py` | 第 11 轮审计：stats/cleanup/migrate/register 四类「写了但没接线」扫描。 |
| `audit_wiring_round11.py` | 第 11 轮实证：artifacts 口径 / cleanup 名实 / cost 读端 / intent workflow / eventbus 订阅。 |
| `audit_wiring_suffix_stats.py` | 第 11 轮补充：后缀式 stats/summary/count/report 扫描 + 短名单引用证据（含 tests）。 |
| `check_imports.py` | 只读审计：静态校验 vools.actus 内部所有 `from vools.actus.X import Y` 是否可解析。 |
| `ci_readonly_summary.py` | 把 `readonly_name_writes.py --json` 的结果渲染成 Job Summary 用的 Markdown。 |
| `desktop_smoke.py` | desktop smoke：首页 + 动作列表 + 动作详情 + 运行端点（13 轮两个 500 的回归守卫）。 |
| `diagnose_event_leak.py` | 诊断：逐个测试文件跑，找出谁在全局 EventBus 上留下未跟踪的订阅。 |
| `false_green_probes.py` | 假绿灯探针：在内存里把被测逻辑改坏，看目标测试是否仍然绿。 |
| `final_verify.py` | 最终验收：6 条修复逐项复跑（隔离 HOME）。 |
| `prove_cache_forge.py` | 只读验证：手写缓存能否冒充真实探测报告（probe 报告权威性）。 |
| `prove_cost_fix.py` | 只读验证：cost.get_cost_summary 的账本完整性信号（改前/改后对比）。 |
| `prove_misc.py` | 只读审计：为 4 条候选缺陷取证（不碰产品代码，全部临时目录）。 |
| `prove_usage_wiring.py` | 只读验证：AI 调用收口接线后，成本账本从 0 行变 >0 行，且 cost_usd 口径诚实。 |
| `readonly_name_writes.py` | 只读命名审计：找出"名字像只读、实际有写副作用"的函数（AST + 调用传递闭包）。 |
| `real_path_writes_scan.py` | 测试卫生扫描：找出 tests/ 里可能**写真实仓库文件**的语句。 |
| `scan_cmd_crashes.py` | 只读扫描：给每个 CLI 子命令喂一组无害参数，抓 AttributeError/NameError 类崩溃。 |
| `scan_missing_imports.py` | 全库扫描：函数内把 X 当模块用（X.attr），但模块级/函数内都没有 import X。 |
| `security_audit.py` | 安全审计：vault2.py / visibility.py（全部在 tmp 隔离目录，不碰 ~/.actus）。 |
| `security_audit2.py` | 安全审计 part2：团队文件写坏/路径逃逸/大小写绕过 + vault2 证据（全 tmp 隔离）。 |
| `sigma_audit.py` | sigma.py 审计：17 条 Iron Laws 逐条反例 + 门禁假通过探测。 |
| `sigma_flip_stats.py` | 统计：把 canonical tests 失败纳入 passed 后，有多少 spec/动作会由 pass 变 fail。 |
| `test_suite_coverage_map.py` | 测试覆盖测绘：哪些 vools/actus 模块没有被任何测试文件引用/断言到。 |
| `three_entry_audit.py` | 三方一致性审计：CLI / MCP / Python API 对同一操作的契约对比。 |
| `verify_registry_fixes.py` | 验收 P1-A/B/C + P2 批（registry.py / omega_strong.py / cli.py）。全 tmp 隔离。 |
| `verify_round10_changes.py` | 验收 ① 结构校验 / ③ security 分级 / 性能与影响面（修正版）。 |
| `verify_round10_perf.py` | 性能与 executor 门禁定向验收（③-C / ③-D 修正版）。 |
| `verify_round11_changes.py` | 第 11 轮验收：cost / selfdrive / workflow / artifacts / unsubscribe。 |
| `verify_round12_public_api.py` | 第 12 轮收尾验收：list_secret_names / delete_secret（与私有路径逐字段对比 + 只读快照）。 |
| `verify_round12_readonly_readpath.py` | 第 12 轮残留验收：resolve_secret / resolver_status / vault get / executor vault:// 读路径零写。 |
| `verify_round12_resolver.py` | 第 12 轮验收：统一 secret resolver（6 步 + executor 接线）。 |
| `verify_round13_readonly_names.py` | 第 13 轮实证：只读命名函数的写副作用快照（isolation: ACTUS_REPO_ROOT / ACTUS_META_DIR / HOME）。 |
| `verify_round14_readonly_writes.py` | 第 14 轮验收：D 类 vault2.get_secret(read_only) + indexer/MCP 只读路径零写。 |
| `verify_round15_migrate.py` | 第 15 轮验收：actus vault migrate CLI + MCP（dry-run 零写 / 迁移 / 失败 / 无凭据）。 |
| `verify_runtime_consumers.py` | 验收：indexer / author / evolution / scattered 四处对 runtime: 的分流（裸仓库 vs 正常仓库）。 |
| `verify_runtime_consumers2.py` | 验收 v2：indexer/author/evolution/scattered 的 runtime 分流（裸仓库 vs 正常仓库）。 |
| `verify_vault2_keyring.py` | 验收：vault2 seed_key 不再明文落库（keyring / passphrase / file-key / fail-closed / 迁移）。 |
| `verify_vault2_migrate.py` | 迁移验收（语义正确版）：把真实 seed_key 改回明文 → 重开自动迁移 → 旧 secrets 仍可读。 |
| `weak_tests_scan.py` | AST 扫描：找出「所有断言都很弱」的测试函数（假绿灯高风险）。 |

## 已知局限（尤其是扫描器）

- **`readonly_name_writes.py`**（AST 扫描）：只认得出「名字像只读、链路里有写」，但
  **看不到 kwarg 常量关闭写**（如 `add_trigger(..., _persist=False)`）、
  **三方库按名字归类**（`subprocess.run` / `Path.unlink` 一律当写）、
  **动态分派 / 反射**，且只覆盖 `vools/actus/`。
  因此 CI 里它是**告警不是门禁** —— 误报请人工标注，**不要为了清零而放宽检测**。
- **`scan_cmd_crashes.py` / `weak_tests_scan.py` / `false_green_probes.py`** 是启发式扫描，
  输出是"候选"，需要人工判断。
- 凡标注「只读验证 / 验收」的脚本，结论都是**当时**的快照；产品代码改动后需要重跑确认。

## oneoff/ —— 一次性补丁脚本（已应用，**请勿重跑**）

这些是"把某个修复打到产品代码上"的一次性脚本，**对应改动早已应用**：

- `oneoff/patch_records.py`
- `oneoff/patch_round11_core.py`
- `oneoff/patch_round11_deletions.py`
- `oneoff/patch_round11_docclaims.py`
- `oneoff/patch_round11_mcp.py`
- `oneoff/patch_round12_public_api.py`
- `oneoff/patch_round12_readonly_readpath.py`
- `oneoff/patch_round12_resolver.py`
- `oneoff/patch_round14_rest.py`
- `oneoff/patch_round14_writes.py`
- `oneoff/patch_round15_migrate.py`

⚠️ **不要重跑它们**：会对已修好的产品代码重复打补丁（可能破坏当前实现）。
保留只为"当时到底改了什么"的可追溯性；真正的事实来源是 git 历史与产品代码本身。

## 未入库的产物

`actus/build/audit/` 里还留着历史产物（`*.json` 快照、`tmp_*` 临时目录等），
**故意不入库**（数据快照会过期、临时目录无意义）；需要时重跑脚本生成。

## 一个必须知道的坑：脚本 import 的是哪个 `vools.actus`

从 `actus/tools/audit/` 直接跑脚本时，当前目录不含 `actus/`，`import vools` 会解析到
**site-packages 里已发布的老版本**（本机实测 0.8.0）—— 也就是说你测的是发布版，而不是
当前工作树，**且不会有任何提示**。这曾导致一次误判（"CLI 与 API 对同一动作给出相反
校验结论"，实际是 CLI 子进程 import 了旧发布版）。

因此：脚本若 import 产品代码，必须**先把 `actus/` 插到 `sys.path` 最前并断言**：

```python
ACTUS_DIR = <repo>/actus
sys.path.insert(0, ACTUS_DIR)
import vools.actus
assert 'site-packages' not in vools.actus.__file__, (
    '必须使用工作树里的 vools.actus，实际加载: %r' % vools.actus.__file__)
```

子进程同样要继承 `PYTHONPATH=ACTUS_DIR`，否则 CLI 子进程会退回发布版。
`three_entry_audit.py` 已内置这段防御，新增脚本请照抄。
