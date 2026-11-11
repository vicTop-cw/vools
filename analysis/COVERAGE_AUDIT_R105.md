# 模块级测试覆盖审计（R105，统帅轮-12时）

> 生成：2026-11-10 ｜ 方法：AST 提取全仓公开函数（非 `_` 前缀）→ tests/ 全文
> 引用对照（全名/短名双口径）→ 零引用清单按文件聚类。**口径局限**：引用判定
> 是字符串级（含 docstring/注释命中），可能低估实际覆盖；GUI 回调类（tkdialog）
> 在无 Tcl 环境本就 skip，非真缺口。

## 一、零覆盖公开函数分布（53 个）

| 模块 | 数量 | 函数 | 价值分档建议 |
|---|---|---|---|
| probe/sigma.py | 14 | check_backward_compat / check_calibration / check_capabilities / check_compat_proof / check_consensus / check_effect_transparency / check_export_completeness / check_law_declaration 等 check_* 家族 | **高**——sigma 门禁校验面，误判=坏动作放行/好动作误杀；建议专项补测（一测一判据一反例） |
| constants.py | 6 | is_known_declared_feature / is_known_license / is_known_pricing / is_namespaced_id / is_secret_sensitive_name / is_testish_id | **高**——schema 校验谓词族（闭集枚举），纯函数秒测；建议 6 函数 × 3 反例一批收口 |
| model.py | 6 | cached_artifacts / context_applies / net_connect / net_listen / parse_action_from_schema_md / reserved_env | **中**——net_* 系内部网络工具（是否公开导出存疑，建议先评估降级 `_` 前缀）；parse_action_from_schema_md 是解析入口值得测 |
| tkdialog.py | 6 | after_show / enforce_focus / finish_confirm_only / on_blur / on_focus_in / on_focus_out | **低**——GUI 事件回调，Tcl 环境守卫 skip 的受害者；有 Tcl 的 CI 环境自然覆盖 |
| validate.py | 3 | check_link_target / dfs / dfs_cycle | **中**——validate 内部图算法，dfs/dfs_cycle 或应降级 `_` |
| visibility.py | 3 | get_visibility_engine / grant_gated_key / revoke_gated_key | **中**——gated key 管理面，安全语义（建议补） |
| viz.py | 3 | to_ascii / to_mermaid / visualize_action_workflow | **低**——可视化输出，golden 快照型测试 |
| 零散 ×11 | 各 1 | adapter.replacer / cost.alert_budget_if_over / errors.check_path_target / indexer.filter_by_dimension / intent.get_default_router / scattered.dfs / selfdrive.strong_enabled / trust_model.allowed_permissions / vault.default_meta_dir / vault2.default_vault_dir / catalog.union / platform_tools.is_capability_item | **混合**——errors.check_path_target 与 indexer.filter_by_dimension 疑似审计口径假阴性（字符串引用在别处），逐个核实后再定 |

## 二、结论与排期建议

1. **sigma.py check_* 家族（14）+ constants 谓词族（6）= 20 函数是第一批补测**的
   高价值标的（校验门禁面、纯函数易测、出错影响信任模型）。
2. **net_*/dfs* 等 9 个函数建议先走「公开面收敛」评审**：内部工具升 `_` 前缀
   比补测试更省（缩小维护承诺面），需主人拍板 API 收敛口径。
3. 审计脚本 `temp/coverage_audit.py`（可复跑，AST 口径）；本轮不擅自补测。
