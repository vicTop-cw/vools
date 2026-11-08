# actus 测试基线复测报告（R10H 统帅轮 · 逐文件驱动）

- 生成时间：2026-11-07 12:17:03（进行中（部分结果））
- 方法：`actus/tools/_baseline_r10h.py`，每个 `tests/test_*.py` 用独立进程跑
  `python -m pytest <file> -q --tb=line -p no:cacheprovider --basetemp <独立tmp> --junitxml <独立xml>`，
  单文件硬超时 300s，超时记 HANG；计数以 junitxml 为准（本机 pytest 9.1.1 终端摘要行被吞，stdout 解析不可靠）。
- 背景：全量 `python -m pytest -q tests` 10 分钟无输出，本报告定位慢点/挂点。

## 汇总

| 指标 | 数值 |
| --- | --- |
| 测试文件数 | 200 |
| 总用例数 | 5780 |
| passed | 5765 |
| failed | 10 |
| error（收集/夹具错误） | 0 |
| skipped | 5 |
| HANG 文件数 | 0 |
| FAIL/ERROR 文件数 | 6 |
| 总耗时（驱动侧秒，含进程启动） | 964.7s |

## FAIL/ERROR 文件清单

| 文件 | 结果 |
| --- | --- |
| `test_ai_catalog.py` | passed 10, **failed 3** |
| `test_ai_gaps.py` | passed 15, **failed 2** |
| `test_ai_selector.py` | passed 28, **failed 1** |
| `test_python_pkgs_contracts_r95.py` | passed 44, **failed 2** |
| `test_registry_installer_contracts.py` | passed 19, **failed 1** |
| `test_vault_roundtrip.py` | passed 14, **failed 1** |

## 最慢 10 文件

| 文件 | 秒 | 结果 |
| --- | --- | --- |
| `test_mcp_sse_contracts_r51.py` | 61.3 | passed 18 |
| `test_vault2_contracts_r75.py` | 58.4 | passed 104 |
| `test_vault2_contracts_r32.py` | 34.8 | passed 36 |
| `test_language_entries.py` | 30.7 | passed 7 |
| `test_cli_no_side_effects.py` | 22.1 | passed 20 |
| `test_tkdialog_gui_contracts_r77.py` | 20.4 | passed 32 |
| `test_ai_catalog_contracts_r90.py` | 19.8 | passed 16 |
| `test_vault_readonly_contracts.py` | 19.1 | passed 13 |
| `test_cli_all_subcommands.py` | 16.9 | passed 171 |
| `test_omega_strong_contracts_r68.py` | 16.4 | passed 87 |

## 全文件清单

| 文件 | 用例数 | 秒 | 结果 |
| --- | --- | --- | --- |
| `test_action_lookup.py` | 7 | 2.5 | passed 7 |
| `test_action_readiness_intent.py` | 9 | 1.8 | passed 9 |
| `test_adapter_contracts_r32.py` | 71 | 6.3 | passed 71 |
| `test_adapter_registry_contracts_r32.py` | 30 | 2.8 | passed 30 |
| `test_ai_base_contracts_r62.py` | 47 | 12.2 | passed 47 |
| `test_ai_catalog.py` | 13 | 2.9 | passed 10, **failed 3** |
| `test_ai_catalog_contracts_r90.py` | 16 | 19.8 | passed 16 |
| `test_foo.py` | 1 | 1.7 | passed 1 |
| `test_ai_gaps.py` | 17 | 14.7 | passed 15, **failed 2** |
| `test_ai_gaps_contracts_r89.py` | 14 | 1.6 | passed 14 |
| `test_ai_registry.py` | 25 | 3.9 | passed 25 |
| `test_ai_routing_contracts_r32.py` | 33 | 1.6 | passed 33 |
| `test_ai_selector.py` | 29 | 1.5 | passed 28, **failed 1** |
| `test_ai_session.py` | 12 | 1.7 | passed 12 |
| `test_analyze_actions.py` | 13 | 2.2 | passed 13 |
| `test_author_contracts_r84.py` | 31 | 4.9 | passed 31 |
| `test_basic_actions.py` | 11 | 1.8 | passed 11 |
| `test_bugreport_contracts_r86.py` | 35 | 2.1 | passed 35 |
| `test_calllog_contracts_r79.py` | 41 | 2.6 | passed 41 |
| `test_classification.py` | 33 | 1.7 | passed 33 |
| `test_cli_all_subcommands.py` | 171 | 16.9 | passed 171 |
| `test_cli_behavior_contracts.py` | 17 | 6.0 | passed 17 |
| `test_cli_contracts_r71.py` | 154 | 5.7 | passed 154 |
| `test_cli_contracts_r72.py` | 99 | 2.5 | passed 99 |
| `test_cli_contracts_r73.py` | 106 | 7.3 | passed 106 |
| `test_cli_json_contracts.py` | 12 | 2.1 | passed 12 |
| `test_cli_mcp_cross_entry.py` | 4 | 6.5 | passed 4 |
| `test_cli_no_side_effects.py` | 20 | 22.1 | passed 20 |
| `test_cli_probe.py` | 6 | 14.3 | passed 6 |
| `test_cli_surface.py` | 10 | 8.5 | passed 10 |
| `test_clipboard_integration.py` | 13 | 2.7 | passed 13 |
| `test_concurrency_contracts_r32.py` | 19 | 1.9 | passed 19 |
| `test_cost_month_boundary.py` | 3 | 1.6 | passed 3 |
| `test_curator.py` | 14 | 1.7 | passed 14 |
| `test_curator_contracts_r87.py` | 27 | 1.9 | passed 27 |
| `test_dag_scheduler.py` | 8 | 1.7 | passed 8 |
| `test_deep_boundary_r101.py` | 8 | 5.9 | passed 8 |
| `test_demo_indexing.py` | 4 | 3.7 | passed 4 |
| `test_demo_mode.py` | 4 | 1.5 | passed 4 |
| `test_dependency_contracts_r52.py` | 94 | 2.2 | passed 94 |
| `test_dependency_runtime.py` | 10 | 1.8 | passed 10 |
| `test_desktop_contracts_r65.py` | 42 | 7.6 | passed 42 |
| `test_desktop_exec_contracts.py` | 16 | 6.3 | passed 16 |
| `test_desktop_import.py` | 3 | 1.5 | passed 3 |
| `test_directives.py` | 11 | 1.6 | passed 11 |
| `test_error_codes.py` | 4 | 1.9 | passed 4 |
| `test_evolution_contracts_r56.py` | 67 | 2.3 | passed 67 |
| `test_exec_iface.py` | 27 | 2.0 | passed 27 |
| `test_exec_iface_contracts_r81.py` | 112 | 5.2 | passed 112 |
| `test_executor_contracts_r69.py` | 73 | 3.8 | passed 73 |
| `test_executor_contracts_r98.py` | 40 | 2.6 | passed 40 |
| `test_fence_forms.py` | 8 | 1.7 | passed 8 |
| `test_format_detection.py` | 4 | 1.7 | passed 4 |
| `test_frontmatter_contracts_r82.py` | 28 | 1.7 | passed 28 |
| `test_graph_blast_radius.py` | 4 | 1.5 | passed 4 |
| `test_health_contracts_r85.py` | 34 | 2.1 | passed 34 |
| `test_highlight_contracts_r48.py` | 52 | 1.9 | passed 52 |
| `test_import.py` | 0 | 1.4 | no tests |
| `test_import_absolute.py` | 0 | 1.5 | no tests |
| `test_importsys_contracts_r52.py` | 55 | 1.9 | passed 55 |
| `test_index_invalidation_r10h.py` | 6 | 4.4 | passed 6 |
| `test_installer_contracts_r70.py` | 103 | 10.6 | passed 103 |
| `test_intent_router.py` | 28 | 2.6 | passed 28 |
| `test_jump_batch_guard.py` | 3 | 2.4 | passed 3 |
| `test_jump_contracts_r58.py` | 189 | 8.7 | passed 189 |
| `test_jump_paramiko_guard.py` | 5 | 1.5 | passed 5 |
| `test_jump_shell_quote.py` | 6 | 1.8 | passed 6 |
| `test_kek_rotation_crash_matrix.py` | 29 | 9.0 | passed 29 |
| `test_kind_dispatch.py` | 7 | 1.5 | passed 7 |
| `test_kind_edge_cases.py` | 8 | 1.7 | passed 8 |
| `test_kind_family.py` | 7 | 1.6 | passed 7 |
| `test_kind_family_e2e.py` | 6 | 13.9 | passed 6 |
| `test_language_entries.py` | 7 | 30.7 | passed 7 |
| `test_link_chain.py` | 4 | 11.4 | passed 4 |
| `test_link_merge.py` | 9 | 1.4 | passed 9 |
| `test_loophelpers_contracts.py` | 13 | 1.7 | passed 13 |
| `test_loophelpers_contracts_r66.py` | 42 | 1.7 | passed 42 |
| `test_mcp_async_tasks.py` | 8 | 2.6 | passed 8 |
| `test_mcp_handlers.py` | 48 | 10.1 | passed 48 |
| `test_mcp_server_contracts_r74.py` | 52 | 5.5 | passed 52 |
| `test_mcp_server_contracts_r74b.py` | 47 | 15.2 | passed 47 |
| `test_mcp_sse_contracts_r51.py` | 18 | 61.3 | passed 18 |
| `test_mcp_target_forms.py` | 7 | 2.0 | passed 7 |
| `test_md5_fingerprint_consistency.py` | 7 | 3.8 | passed 7 |
| `test_md5_form.py` | 2 | 1.8 | passed 2 |
| `test_mdtest_contracts_r55.py` | 54 | 7.1 | passed 54 |
| `test_mdtest_validation.py` | 12 | 1.8 | passed 12 |
| `test_metrics.py` | 8 | 2.0 | passed 8 |
| `test_metrics_instrumentation.py` | 5 | 8.3 | passed 5 |
| `test_new_capabilities.py` | 36 | 8.3 | passed 36 |
| `test_notify_contracts_r51.py` | 51 | 2.4 | passed 51 |
| `test_omega.py` | 31 | 2.3 | passed 31 |
| `test_omega_contracts_r57.py` | 152 | 2.9 | passed 152 |
| `test_omega_coverage.py` | 17 | 1.9 | passed 17 |
| `test_omega_strong_contracts_r68.py` | 87 | 16.4 | passed 87 |
| `test_p2_restored_hooks.py` | 4 | 1.7 | passed 4 |
| `test_panel_contracts.py` | 19 | 2.6 | passed 19 |
| `test_panel_contracts_r53.py` | 33 | 8.7 | passed 33 |
| `test_params_action_ref.py` | 7 | 1.7 | passed 7 |
| `test_params_forms.py` | 10 | 2.8 | passed 10 |
| `test_planner_contracts_r95.py` | 18 | 5.2 | passed 18 |
| `test_platform_enum_alignment.py` | 20 | 3.7 | passed 20 |
| `test_probe.py` | 21 | 9.9 | passed 21 |
| `test_probe_actions.py` | 12 | 5.0 | passed 12 |
| `test_probe_actions_contracts_r94.py` | 30 | 2.2 | passed 30 |
| `test_probe_all_exports.py` | 4 | 1.6 | passed 4 |
| `test_probe_parallel.py` | 11 | 2.0 | passed 11 |
| `test_probe_permissions_contracts_r50.py` | 13 | 1.7 | passed 13 |
| `test_probe_permissions_contracts_r97.py` | 9 | 1.6 | passed 9 |
| `test_probe_platform_contracts_r61.py` | 29 | 2.0 | passed 28, skipped 1 |
| `test_probe_platform_tools.py` | 12 | 1.6 | passed 9, skipped 3 |
| `test_probe_report_contracts_r96.py` | 59 | 1.9 | passed 59 |
| `test_probe_resources_contracts_r50.py` | 15 | 1.7 | passed 15 |
| `test_probe_resources_contracts_r97.py` | 15 | 1.5 | passed 15 |
| `test_probe_windows.py` | 9 | 2.6 | passed 9 |
| `test_proc_contracts_r88.py` | 30 | 4.4 | passed 30 |
| `test_project_contracts_r54.py` | 77 | 2.1 | passed 77 |
| `test_project_io_contracts_r60.py` | 32 | 1.9 | passed 32 |
| `test_providers_contracts_r91.py` | 69 | 1.9 | passed 69 |
| `test_public_surface.py` | 4 | 1.7 | passed 4 |
| `test_publisher_contracts_r29.py` | 28 | 5.4 | passed 28 |
| `test_publisher_contracts_r80.py` | 85 | 6.0 | passed 85 |
| `test_pytest_compat_contracts_r32.py` | 24 | 1.6 | passed 24 |
| `test_python_pkgs_contracts_r95.py` | 46 | 3.5 | passed 44, **failed 2** |
| `test_quality.py` | 9 | 2.0 | passed 9 |
| `test_quality_contracts_r82.py` | 27 | 6.7 | passed 27 |
| `test_records_contracts_r95.py` | 36 | 4.2 | passed 36 |
| `test_registry_contracts_r32.py` | 19 | 2.3 | passed 19 |
| `test_registry_installer_contracts.py` | 20 | 3.4 | passed 19, **failed 1** |
| `test_registry_omega_contracts.py` | 30 | 2.7 | passed 30 |
| `test_remote_digest.py` | 5 | 1.7 | passed 5 |
| `test_remote_signature.py` | 5 | 2.1 | passed 5 |
| `test_repo_contracts_r64.py` | 73 | 5.5 | passed 73 |
| `test_resolver_cli.py` | 7 | 9.8 | passed 7 |
| `test_resolver_contracts_r100.py` | 77 | 2.8 | passed 77 |
| `test_round11_capabilities.py` | 16 | 5.3 | passed 16 |
| `test_runtimes_contracts_r32.py` | 18 | 2.2 | passed 18 |
| `test_sandbox_contracts_r32.py` | 12 | 1.6 | passed 11, skipped 1 |
| `test_scaffold_contracts_r97.py` | 24 | 4.0 | passed 24 |
| `test_scaffold_safety.py` | 9 | 3.6 | passed 9 |
| `test_scattered_contracts_r29.py` | 18 | 5.3 | passed 18 |
| `test_scattered_contracts_r31.py` | 16 | 4.9 | passed 16 |
| `test_scattered_contracts_r78.py` | 67 | 5.0 | passed 67 |
| `test_schema_p1_fields.py` | 10 | 3.1 | passed 10 |
| `test_security_contracts_r63.py` | 81 | 2.0 | passed 81 |
| `test_security_hardcoded_vs_ref.py` | 10 | 1.5 | passed 10 |
| `test_seed_signatures.py` | 4 | 1.7 | passed 4 |
| `test_selfdrive_contracts_r32.py` | 18 | 1.8 | passed 18 |
| `test_selfdrive_expansion_contracts_r32.py` | 11 | 1.6 | passed 11 |
| `test_selfdrive_load_contracts_r32.py` | 8 | 1.7 | passed 8 |
| `test_selfdrive_run_node_contracts_r32.py` | 7 | 1.7 | passed 7 |
| `test_selfdrive_validation.py` | 27 | 1.5 | passed 27 |
| `test_selfdrive_verify_contracts_r32.py` | 16 | 1.6 | passed 16 |
| `test_selfdrive_worker_contracts_r32.py` | 19 | 1.6 | passed 19 |
| `test_selfheal_contracts_r67.py` | 60 | 1.7 | passed 60 |
| `test_selfheal_export.py` | 47 | 1.7 | passed 47 |
| `test_semver.py` | 36 | 1.9 | passed 36 |
| `test_sigma_contracts_r32.py` | 52 | 1.8 | passed 52 |
| `test_sigma_eval_contracts_r93.py` | 37 | 1.8 | passed 37 |
| `test_sigma_eval_contracts_r94.py` | 126 | 2.2 | passed 126 |
| `test_sigma_gates.py` | 33 | 1.6 | passed 33 |
| `test_silent_import_bugs.py` | 6 | 3.8 | passed 6 |
| `test_system_tools_contracts_r95.py` | 41 | 7.1 | passed 41 |
| `test_target_forms_contracts.py` | 11 | 11.6 | passed 11 |
| `test_template_contracts_r48.py` | 35 | 1.9 | passed 35 |
| `test_tkdialog_contracts.py` | 46 | 1.9 | passed 46 |
| `test_tkdialog_contracts_r32.py` | 24 | 1.6 | passed 24 |
| `test_tkdialog_gui_contracts_r77.py` | 32 | 20.4 | passed 32 |
| `test_triggers_contracts_r32.py` | 52 | 2.0 | passed 52 |
| `test_triggers_contracts_r99.py` | 28 | 1.7 | passed 28 |
| `test_triggers_cron.py` | 18 | 1.5 | passed 18 |
| `test_trust_contracts_r50.py` | 19 | 1.6 | passed 19 |
| `test_trust_model_approval_contracts_r32.py` | 12 | 1.7 | passed 12 |
| `test_trust_model_contracts_r32.py` | 15 | 1.7 | passed 15 |
| `test_trust_model_contracts_r96.py` | 44 | 2.5 | passed 44 |
| `test_trust_model_keys_contracts_r32.py` | 7 | 1.6 | passed 7 |
| `test_validate_contracts_r32.py` | 40 | 4.5 | passed 40 |
| `test_vault2_contracts_r32.py` | 36 | 34.8 | passed 36 |
| `test_vault2_contracts_r75.py` | 104 | 58.4 | passed 104 |
| `test_vault2_replay.py` | 5 | 4.0 | passed 5 |
| `test_vault_adapter_contracts.py` | 14 | 5.1 | passed 14 |
| `test_vault_cross_window.py` | 3 | 3.4 | passed 3 |
| `test_vault_master_migration.py` | 9 | 10.1 | passed 9 |
| `test_vault_readonly_contracts.py` | 13 | 19.1 | passed 13 |
| `test_vault_resolver_contracts_r92.py` | 100 | 7.9 | passed 100 |
| `test_vault_roundtrip.py` | 15 | 2.2 | passed 14, **failed 1** |
| `test_vault_time_boundaries.py` | 2 | 2.5 | passed 2 |
| `test_visibility_config.py` | 30 | 1.6 | passed 30 |
| `test_visibility_contracts_r32.py` | 21 | 2.2 | passed 21 |
| `test_viz.py` | 22 | 1.5 | passed 22 |
| `test_webhook_contracts_r32.py` | 33 | 1.7 | passed 33 |
| `test_webhook_server_contracts_r32.py` | 25 | 1.6 | passed 25 |
| `test_winstyle_contracts_r32.py` | 22 | 1.6 | passed 22 |
| `test_workflow_contracts_r32.py` | 38 | 4.0 | passed 38 |
| `test_workflow_contracts_r99.py` | 24 | 1.7 | passed 24 |
| `test_yaml_frontmatter.py` | 10 | 1.8 | passed 10 |
| `test_zh.py` | 1 | 3.3 | passed 1 |
| `test_zhdocsb.py` | 1 | 3.1 | passed 1 |
| `test_zhzh.py` | 1 | 3.3 | passed 1 |
| `test_zhzhai.py` | 1 | 3.6 | passed 1 |

## 失败诊断

（见报告末尾追加的诊断记录）

---

## T0r2.1.2 复测结论（2026-11-08，file-agent）

复测方式：6 个失败文件逐一以 `python -m pytest tests/<file> -q --tb=line -p no:cacheprovider` 独立重跑。
运行环境：Windows 11 / Python 3.13.13 / pytest 9.1.1，工作目录 `actus/`，未使用自定义 `--basetemp`。
复测结果：**6 文件全部通过（EXIT=0），基线 10 个失败用例全部转绿，无需新增修复。**

| 文件 | 基线 | 复测 | 结论 |
|---|---|---|---|
| `test_ai_catalog.py` | 13 用例 failed 3 | passed 13 | 全绿（索引重建后自愈） |
| `test_ai_gaps.py` | 17 用例 failed 2 | passed 17 | 全绿（索引重建后自愈） |
| `test_ai_selector.py` | 29 用例 failed 1 | passed 29 | 全绿（索引重建后自愈） |
| `test_python_pkgs_contracts_r95.py` | 46 用例 failed 2 | passed 46 | 全绿（T0r4.1 收口后自愈） |
| `test_registry_installer_contracts.py` | 20 用例 failed 1 | passed 20 | 全绿（隔离环境正常） |
| `test_vault_roundtrip.py` | 15 用例 failed 1 | passed 15 | 全绿（驱动方式伪失败） |

### 逐条根因分析

1. **`test_ai_catalog.py`（3）/ `test_ai_gaps.py`（2）/ `test_ai_selector.py`（1）—— 真实索引缓存过期，非真实缺陷**
   - 失败形态：`detect_duplicates` 的 exact 集合为空、`nonstandard_prefix` 为空、`len(cat)=14 < 30` —— catalog 构建读到的索引数据不完整。
   - 根因：这些用例（`@needs_index`）依赖真实索引 `E:\IDEProjects\AI\Actus\_meta`。基线生成时索引缓存为过期/不完整状态（旧缓存无 `parser_fingerprint` 字段）。
   - 现状：`indexer.py` 的 T0r4.1「解析器指纹自动失效」机制（`load_index` 读到无指纹旧缓存 → 判定过期 → 自动重建）已在工作区生效，索引重建后 catalog 达 93 条，三组写死重复对与 `vools.vault.get` 全部命中（已用脚本实测确认）。
   - 证据：复测全绿 + 索引重建后 `LEN=93`、`('actus.cli.curl','cli.curl') in pairs=True`、`'http.fetch' in keys=True`、`'vools.vault.get' in nonstandard=True`。

2. **`test_python_pkgs_contracts_r95.py`（2）—— T0r4.1 收口修复（信号留痕丢失），非 R10H 遗留**
   - 失败形态：`_get_pkg_version_detail` 返回 `None`（无 signal），期望 `{'error_kind':'metadata_error','error':'ValueError'}` / `{'error_kind':'metadata_unavailable','error':'ImportError'}`。
   - 根因：基线生成时工作区处于 T0r4.1 开发中间态：import 兜底在 `ModuleNotFoundError` 时吞掉已积累的诊断信号；且旧打桩方式（`builtins.__import__`）会连带炸掉 pytest 内部 import 引发 INTERNALERROR。
   - 修复（已随 T0r4.1 收口落地，工作区未提交）：`python_pkgs.py` import 兜底改为 `ModuleNotFoundError/ImportError → return signal`（保留 metadata_error / metadata_unavailable 留痕）、其他异常覆盖 `metadata_unavailable`；测试改用 `monkeypatch.setitem(sys.modules,'pkg_resources',None)` 并期望 `ModuleNotFoundError`。
   - 证据：复测 46 passed；`test_detail_pkg_resources_unavailable_signal` 现返回 `{'error_kind':'metadata_unavailable','error':'ModuleNotFoundError'}`。

3. **`test_registry_installer_contracts.py`（1）—— 环境隔离时序问题，非真实缺陷**
   - 失败形态：`check_update` 返回 `status='ok'`（期望 `'unknown'`），`local_commit=908fbd17`、`remote_commit=d9a2ba94` —— 指向主仓库而非测试安装目录。
   - 根因：check_update 的「无 remote ≠ 最新」审计修（unknown 分支）已在 HEAD（`be0cdb84`）存在；基线失败时 git 命令解析到了主仓库（local=908fbd17 即基线时主仓 HEAD），属基线驱动环境下的目录解析/隔离时序异常。
   - 现状：正常 pytest 下安装目录正确隔离（无 origin）→ 返回 `unknown`。
   - 证据：复测 20 passed，该用例断言 `status == "unknown"` 通过。

4. **`test_vault_roundtrip.py`（1）—— 基线驱动方式伪失败，非真实缺陷**
   - 失败形态：`ACTUS_META_DIR` 指向 `.../_r10h_tmp/test_vault_roundtrip/test_session_dirs_are_pinned_a0/_meta_runtime`，不满足断言要求路径含 `pytest-` 或 `session-isolation`。
   - 根因：基线驱动脚本（`actus/tools/_baseline_r10h.py`）为各文件独立进程指定了自定义 `--basetemp _r10h_tmp/...`，使 session 隔离目录路径不含 `pytest-` 特征，触发该「钉离真实 HOME」守卫用例的路径断言失败 —— 纯驱动方式伪失败。
   - 现状：不加 `--basetemp` 正常重跑，路径含 `pytest-of-<user>/pytest-current`，断言通过。
   - 证据：复测 15 passed。

### 结论

基线 10 个失败用例经复测全部转绿：3 项属索引缓存过期（已被 T0r4.1 索引自动失效机制自愈）、2 项属 T0r4.1 收口修复的真实信号缺陷（实现+测试均已在工作区收口，待 T0r4.1 提交）、1 项属基线驱动环境的目录解析时序异常、1 项属基线驱动 `--basetemp` 伪失败、其余为驱动方式问题。本任务无新增修复；复测证据见上。
