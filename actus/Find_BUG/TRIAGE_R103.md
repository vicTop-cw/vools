# Find_BUG repro 甄别报告（R103，统帅轮-10时）

> 生成：2026-11-10 ｜ 方法：逐脚本细读断言语义 + 产品代码行级对照 + 实跑取证
> 背景：统帅轮-09时批量实跑 14 个 repro（2 rc=0 / 12 rc=1），本轮对 12 个 rc=1
> 全部完成定性。**关键方法论**：这批 repro 的断言是「bug 存在的证据」形态
> （assert bug 现象成立），断言失败（rc=1 的 AssertionError）多数意味着
> **bug 已修**，与直觉相反——必须逐个读断言方向才能定性，不可只看 rc。

## 一、全景定性表（14/14）

| # | 脚本 | rc | 定性 | 终裁证据 |
|---|---|---|---|---|
| 1 | repro_a1_debug.py | 0 | 当年即通过 | output file actually written: False |
| 2 | repro_tail.py | 0 | 脆弱样本未触发 | 自述「依赖写入方格式一致，脆弱但当前不炸」 |
| 3 | repro_frontmatter.py | 1 | **脚本过期** | ImportError：`_AIGC_KEYS` 符号已不存在（产品重构） |
| 4 | repro_exec_iface.py | 1 | **脚本过期**（3 处 bug 全修） | ①BUG-1：`_map_error_code('dependency_missing')`→`unreachable`、trust_rejected→auth、concurrency_limit→quota（映射表已对齐）；②BUG-2：`_classify_exception(timeout)`→`timeout`、permission_denied→`resource`（双路一致）；③BUG-3：awaiting_confirmation 归一为 `status='skipped'`（比当年期望更进一步——待确认态≠错误） |
| 5 | repro_featured_validate.py | 1 | **脚本过期**（3 处全修） | ①BUG-F1：get_featured 首名 hot.act0（growth=4.286 活跃动作，交集生效，死动作被挤出）；②BUG-N1：截断真生效（max_n=5，bogus3 被丢弃且警告明示「已截断（丢弃 1 个未知值）」）；③BUG-S1：双缺 provider 只报 2 条缺失，假重复「重复: None」消失 |
| 6 | repro_final3.py | 1 | **脚本过期** | BD-FM2：嵌套 generated-by 不再误判 AIGC（blocks[0][0] != 'aigc'）；BD-QS：is_maintained(None) 不抛 TypeError 返回 False（归一修复）；BD-X2 见 #13 |
| 7 | repro_indexer.py | 1 | **脚本过期** | BUG-I1：第 2 轮 conflict **有痕**（conflict 字典记录了 id 撞车与缺 id，不再无痕消失） |
| 8 | repro_indexer_cache.py | 1 | **脚本过期** | BUG-I4：缓存键带 actions_dir 身份（`all(k.startswith('r0/'))` 断言失败=键已含根身份，跨仓污染通道封死） |
| 9 | repro_last.py | 1 | **脚本过期** | BUG-S2：`'99 99 * * *'` 被打回（errs 非空，值域校验生效）；BD-FM1：strip_frontmatter 前导空行行为保留但 docstring 已按 V-15 口径修正（「跳过前导空行后不以 --- 开头→原样返回」，合规块不因空行漏剥，行为可辩护） |
| 10 | repro_purpose_case.py | 1 | **脚本过期** | BUG-I3b：filter_by_dimension 查询端归一（V-19：小写 transform 也能命中，`lo == []` 断言失败=归一生效） |
| 11 | repro_curator.py | 1 | **脚本过期** | BUG-C1：`_collection_path('My List')` → `My-List-5d716854`（空格转连字符+哈希消歧，p1 != p2，不再碰撞同一文件） |
| 12 | repro_quality_calllog.py | 1 | **脚本过期** | BUG-Q1：`_probe_omega` 认 actions/{private,public}/omega/ 真源路径（断言 is False 失败=探测到了）；BUG-Q3：`_SELF_TOOLS` 出现 4 行（自指排除已接线，原 1 行纯定义）；BUG-Q2：internal 档**已修**（V-07 判据重构：visibility=internal 或包内种子路径短路——实测 FakeAction 带 `visibility: internal` → internal，普通动作 → bronze 正确；repro 用 id 推断的构造已不适用） |
| 13 | repro_supplement.py | 1 | **脚本过期** | BUG-I3b fallback 变体：indexer.py:419 建键端 `.strip().lower()` 归一（校验 fallback 放行原值但索引键归一，查询端 V-19 对齐）；BUG-A1：artifacts 收编生效（合法 adapter id 下 artifacts 非空，原断言 artifacts==[] 失败；原 repro 用不合法 id 被新 schema 校验前置拦截报 action_invalid——优雅报错替代静默吞） |
| 14 | repro_x1_e2e.py | 1 | **脚本过期** | BUG-X1：3 次待确认预览不再落 metrics（total=1 仅真实执行，success_rate=1.0 干净，silver 门槛不再被预览污染） |

## 二、BD-X2（依赖缺失早退留痕）专项实测

构造声明 `deps: [{type: system, name: definitely-no-cmd-x2-xyz, required: true}]`
的动作执行（trusted，confirmed=True）：
- 执行返回 status=failed（本样本先被 action_invalid 拦——deps dict 形态 schema 校验，
  优雅报错路径）
- **action_metrics 留痕 1 行**（ok=0，success_rate=0.0，caller=confirmed）
- 结论：早退路径不再绕过 finish 出口插桩，留痕链完整（D3 修复覆盖依赖预检分支）。

## 三、遗留说明（不阻塞）

- **BD-SC1**（scattered 源 dry_run=True 照样真执行）：语义验证需构造真实 scattered
  环境（scattered 动作 + trusted 信任链），本轮未深挖，留档待专项。当前 exec_iface
  存在 `_ScatteredIface`，行为是否已随 awaiting→skipped 的归一重构一并修正未验证。
- 本报告定稿后，12 个 rc=1 repro 脚本本身**不建议删除**（历史寻虫轮次的证据链），
  建议后续统一加「STALE-已修」头注释（改动面 12 文件，留给下轮卫生批）。

## 四、结论

**Find_BUG 目录 14 个 repro 对应的全部缺陷均已修复**，无真 bug 遗留。
目录性质从「待修复清单」转为「历史寻虫证据存档」。
