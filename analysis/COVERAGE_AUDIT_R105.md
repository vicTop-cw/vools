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
| 零散 ×11 | 各 1 | adapter.replacer / cost.alert_budget_if_over / errors.check_path_target / indexer.filter_by_dimension / intent.get_default_router / scattered.dfs / selfdrive.strong_enabled / trust_model.allowed_permissions / vault.default_meta_dir / vault2.default_vault_dir / catalog.union / platform_tools.is_capability_item | **混合**——统帅轮-14时 精确核实（import/qualified/call-site 三口径 grep）：**12 个全部确认零覆盖，无假阴性**（R105 初版对 check_path_target/filter_by_dimension 的「疑似假阴性」怀疑不成立，已撤回）。errors.check_path_target 是跨模块共用写前检查（多处产品调用面），**优先补测**；filter_by_dimension 已有 V-19 归一语义可顺带锚定；其余多为薄包装/内部工具，建议随 API 收敛评审一并定去留 |

## 二、结论与排期建议（14时 修订）

1. **sigma.py check_* 家族（14）+ constants 谓词族（6）= 20 函数**——✅ **已收口**
   （统帅轮-13时，`tests/test_sigma_checks_r107.py` 44 用例 +
   `tests/test_constants_predicates_r107.py` 69 用例，113 新用例）。
2. **model.py 安全白名单 property（6）+ visibility gated key（3）**——✅ **已收口**
   （统帅轮-14时，`tests/test_model_security_props_r108.py` 14 用例 +
   `tests/test_visibility_gated_r108.py` 5 用例，19 新用例；net_connect/net_listen/
   reserved_env 的收紧默认方向已锚死）。
3. **errors.check_path_target / indexer.filter_by_dimension**——确认零覆盖，
   两个是真实调用面（写前检查/维度查询），建议下一批补测。
4. **net_*/dfs* 等 9 个函数建议先走「公开面收敛」评审**：内部工具升 `_` 前缀
   比补测试更省（缩小维护承诺面），需主人拍板 API 收敛口径。
5. **API 一致性观察**（14时 新增）：Action 便捷读取面不对称——id/trust/entry
   有 property 而 version/name 没有（测试被迫 meta 直读），收敛评审时一并定。
6. 审计脚本 `temp/coverage_audit.py`（可复跑，AST 口径）；核实脚本
   `temp/verify_audit_r105.py`（三口径精确 grep）。
