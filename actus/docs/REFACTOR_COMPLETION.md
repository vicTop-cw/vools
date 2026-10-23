# Actus 重构计划完成度核验（第 30 轮）

> 目的：把 `ACTUS_REFACTOR_PLAN.md` 的**每个条目**映射到可复核的证据
> （测试文件 / 提交 / 实测结论），让"计划已落地"这句话可以被验证，
> 而不是靠开发者自述。
>
> 基线：`pytest tests` → **480 passed, 1 skipped**（59 个测试文件）。
> 命令：`cd actus && python -m pytest -q tests`

## 一、阶段 0–5

| 项 | 内容 | 状态 | 证据 |
|---|---|---|---|
| 0 | 规范定稿（kind 矩阵 / 双后缀 / 语言白名单 / resolver 六形态） | ✅ | `docs/actus/03-动作规范.md` §2.2 / §6.1 / §6.2 / §7 |
| 1 | resolver + CLI/六形态 target + 七形态入参 | ✅ | `tests/test_resolver_cli.py`、`test_params_forms.py`、`test_params_action_ref.py`、`test_remote_digest.py` |
| 2 | 任意语言入口（python/shell/node/go/rust/ruby/php） | ✅ | `tests/test_language_entries.py`（7 语言端到端实跑） |
| 3 | 无源码动作族 7 kind（exec/link/demo/template/alias/bundle/doc） | ✅ | `test_kind_dispatch.py`、`test_kind_family.py`、`test_kind_family_e2e.py`、`test_kind_edge_cases.py`、`test_link_merge.py`、`test_link_chain.py` |
| 4 | 索引扩展（by_name / by_md5 / by_kind / by_purpose / by_industry） | ✅ | `examples/index-extension.schema.json`；`tests/test_md5_form.py`、`test_action_lookup.py` |
| 5 | verify / validate 基线 0 error | ✅ | 4 个种子动作 4/4 签名验证通过；`validate` 批量 `valid=true, invalid={}`；`tests/test_format_detection.py::test_all_shipped_action_files_parse` |

## 二、§四.5 MCP 兼容

| 项 | 状态 | 证据 |
|---|---|---|
| 工具描述写清 target 六形态 | ✅ | `mcp_server.TARGET_FORMS_HINT`；`tests/test_mcp_target_forms.py` |
| MCP 侧真正走 resolver（不只是写文档） | ✅ | `resolve_action_arg()`；同文件 `test_resolver_wired_into_readonly_mcp_tools` |

## 三、§六 风险与开放问题（6 项全部关闭）

| # | 开放问题 | 状态 | 结论 |
|---|---|---|---|
| 1 | powershell/cmd 路由 | ✅ 已解决 | 实测 7 种语言入口全部可执行，无需改动（`test_language_entries.py`） |
| 2 | 名称消歧 UX | ✅ 已对齐 | CLI 与 MCP 都返回结构化 `ambiguous` + candidates（`test_mcp_target_forms.py`） |
| 3 | 远程动作信任模型 | ✅ 四件套齐 | 白名单（默认拒所有远程）+ SSL 校验 + 内容指纹 + 签名验签（`test_remote_digest.py`、`test_remote_signature.py`） |
| 4 | link 参数合并深度 | ✅ 已落地 | 按 `meta['merge']` 支持 `shallow`（默认，零回归）/ `deep`（递归）；规则用例化（`test_link_merge.py`） |
| 5 | 存量 92 error | ✅ 未复现 | 全量逐文件独立校验 11 个动作文件 **0 失败**（修前 4 失败）；`validate` 基线 `valid=true` |
| 6 | `_find_action_file` 双轨 | ✅ 已收口 | 实为**三轨**，加 author 共四处，全部收口到 `resolver.find_action_file` 单一实现；新增 lint 式守卫禁止再写"字符串搜 id"（`test_action_lookup.py`） |

## 四、计划外发现并修复的缺陷（26 个）

按严重度排列。每一项都有对应回归用例。

### 高危（3）

| # | 缺陷 | 影响 |
|---|---|---|
| 1 | **远程下载 SSL 证书校验被禁用**（`CERT_NONE`） | 远程动作源可被中间人替换 |
| 2 | **远程下载白名单语义反转**（空白名单 = 不校验） | SSRF：任意 URL 可被请求 |
| 3 | **DAG 静默丢弃缺失依赖** | 本该串行的节点并发执行，workflow「成功」但结果错 |

### 中危（11）

| # | 缺陷 |
|---|---|
| 4 | 4 个种子动作 `verify` 全失败（缺 `.sig`） |
| 5 | 新格式动作漏传 `md5` → md5 target 形态完全失效（索引 3/7 有 md5） |
| 6 | `dependency._find_action_file` 用字符串搜 id，**看不见新格式动作** |
| 7 | 同类反模式另复制在 `installer` / `evolution` / `dependency.check_dep` 三处 |
| 8 | 格式检测只看 `.actus.schema.md` 后缀 → **4 个 demo 文件全部解析失败** |
| 9 | `build_index(actions_dir=…)` 写默认缓存路径 → **污染主索引**、测试顺序依赖 |
| 10 | 索引器对坏 demo 文件**完全静默忽略** |
| 11 | 空 `bundle` 返回 `status=ok`（静默 no-op，与 link/alias 不一致） |
| 12 | 深链被误诊为"疑似环"（诊断误导运维去查不存在的环） |
| 13 | 包无 `__version__`、CLI 无 `--version`、无子命令静默退出 |
| 14 | 错误码单复数分裂（`missing_param` / `missing_params`） |

### 解析层（7，全部在手写解析器里）

| # | 缺陷 |
|---|---|
| 15 | 围栏解析只认列 0 反引号 → `~~~` 围栏漏掉 |
| 16 | 缩进 ≤3 空格围栏（合法 CommonMark）漏掉 |
| 17 | 4 反引号围栏提前闭合且丢语言 |
| 18 | 裸 `key=value` 引号值被空格截断 |
| 19 | 引号从不剥离（种子动作 title = `'"Calculator"'`） |
| 20 | 空值键 `tag=` 被整条丢弃 |
| 21 | 动作文件的 demo 后缀被误判为旧格式 |

### 其余（5）

| # | 缺陷 |
|---|---|
| 22 | URL 被 `is_scattered_path` 误判为本地路径 → URL 分支被吞 |
| 23 | `link` 深合并缺失（计划 §六.4 的开放问题） |
| 24 | MCP 侧歧义静默回退（看不出"命中了多个"） |
| 25 | 数据表模块 `@rself` 装饰器破坏全部导入（共享包） |
| 26 | `_extract_blocks_builtin` 与 `parse_block_directives` 的兼容性缺口 |

## 五、系统性审计（4 次）

| 审计 | 范围 | 收敛结果 |
|---|---|---|
| 错误码全表 | 63 个码 | 1 个真问题（单复数分裂）；42 个无测试引用（遗留） |
| 静默跳过 / 静默吞异常 | 129 处 `except: pass`、0 裸 except、15 处成员判定跳过 | 2 个真问题（demo 静默吞、索引污染） |
| 解析层 | 围栏 9 形态 + 指令 16 形态 + YAML 12 形态 | 6 个真问题，全部在手写解析器；YAML（PyYAML）0 问题 |
| CLI 参数面 | 11 种调用形态 | 3 个真问题（版本 / 用法提示） |

## 六、遗留（未做，按价值排序）

1. **42 个错误码无测试引用（67%）** —— 建议按「发生频率 × 影响面」分批补；
2. `deps_` / `dependency_` 前缀不一致（命名风格，改动面大、收益低）；
3. 更深边界：template 生成失败路径、demo 递归、workflow 节点重试；
4. 索引重建仍是手工触发，建议加"格式解析逻辑变更时自动失效"机制。

## 七、一条工程结论

**手写解析/查找的地方出了 20 个缺陷；用成熟实现的地方（PyYAML、标准加密）出了 0 个。**

具体对照：
- 手写 markdown 围栏 + 指令解析 → 6 个缺陷
- 手写动作文件查找（4 份实现）→ 4 个缺陷
- 手写格式检测 → 2 个缺陷
- 手写错误码命名 → 1 个缺陷（单复数）
- **PyYAML front-matter → 0**
- **vault 加密（标准库）→ 0**

结论：**边界解析优先用成熟库；必须手写时，要有一组把"合法输入的多样性"覆盖住的用例**——
本轮 6 个解析缺陷全部是"合法但少见的输入形态"没被用例覆盖。
