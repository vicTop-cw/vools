# R10H 基线复测结论（T0r3.4.2）

- 复测时间：2026-11-08
- 依据基线：`docs/BASELINE_R10H.md`（6 文件 10 用例，生成于 2026-11-07）
- 复测方式：`python -m pytest <6 文件> -q --tb=no -p no:cacheprovider --junitxml <独立xml>`，工作目录 `actus/`，计数以 junitxml 为准（pytest 9.1.1 终端摘要行被吞）

## 一、复测统计

| 文件 | 基线用例数 | 基线 failed | 本次复测 |
|---|---|---|---|
| `test_ai_catalog.py` | 13 | 3 | passed 13，EXIT=0 |
| `test_ai_gaps.py` | 17 | 2 | passed 17，EXIT=0 |
| `test_ai_selector.py` | 29 | 1 | passed 29，EXIT=0 |
| `test_python_pkgs_contracts_r95.py` | 46 | 2 | passed 46，EXIT=0 |
| `test_registry_installer_contracts.py` | 20 | 1 | passed 20，EXIT=0 |
| `test_vault_roundtrip.py` | 15 | 1 | passed 15，EXIT=0 |
| **合计** | **140** | **10** | **140 passed，0 failed，0 error，0 skipped** |

- 本次复跑 EXIT=0；唯一输出为 `vools/actus/probe/python_pkgs.py:434` 的 `pkg_resources is deprecated` UserWarning（已知弃用提示，非失败）。

## 二、复测结论

1. **基线复测全绿、无回退**：6 文件 140 用例全部通过，T0r2 修复项（10 个基线失败用例）全部保持转绿状态，无新增失败、无回归。
2. **与 T0r2.1.2 结论一致**：10 个失败用例的根因分类仍为——索引缓存过期自愈（3 项：ai_catalog/ai_gaps/ai_selector）、T0r4.1 收口修复（2 项：python_pkgs_contracts_r95）、环境隔离时序（1 项：registry_installer_contracts）、基线驱动伪失败（1 项：vault_roundtrip），本次复跑无需新增任何修复。

## 三、计划文档与 R10H 基线一致性核验

- 全仓库 `R10H` 关键词仅命中 `docs/BASELINE_R10H.md`；`analysis/IMPLEMENTATION_PLAN.md`、`analysis/FEATURE_EXTENSION_PLAN.md`、`analysis/ACTUS_REFACTOR_PLAN.md`、`analysis/PROBE_PLAN.md`、`docs/DEVELOPMENT_STANDARDS.md`、`docs/REFACTOR_COMPLETION.md`、`docs/INFRA_DIAGNOSTIC.md` 均无 R10H 引用，不存在与 R10H 基线冲突的记载。
- 计划文档中的测试数量记载（如 FEATURE_EXTENSION_PLAN 的 506 passed、REFACTOR_COMPLETION 的 480 passed、INFRA_DIAGNOSTIC 的 367+ passed）均为历史快照，与 R10H 基线（全量 5780 用例基线中的失败子集复测）维度不同、无矛盾。
- 复测脚本 `tools/_baseline_r10h.py` 的覆盖范围与 `BASELINE_R10H.md` 记录的 6 文件一致。

## 四、结论

T0r3.4.2 验收通过：基线复测全绿、无回退、结论已落盘。
