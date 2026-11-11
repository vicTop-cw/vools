# 在途改动落库方案（R104，统帅轮-11时）

> **✅ 已执行完毕（统帅轮-11时收口，2026-11-10）**：主人拍板「按方案提交，与 vools
> 项目无关的踢出去」。落库回执：
> * C1 → `246c9033` test: GUI 探测守卫防半可用环境 ERROR；补 analyze_actions/runtime:/错误码 44 用例；清理打包死条目（10 文件 983+）
> * C2 → `1bb89536` fix: SIP disabled 被 enabled 子串误报为开启态（disabled ⊃ enabled 安全语义反转）；判据改 status: enabled + 4 回归用例（2 文件）
> * C3 → `39682495` docs: Find_BUG 14 repro 全景甄别——全部已修零遗留，脚本加 STALE 头转证据存档（13 文件）
> * C4 → `3fd59251` docs: 三本账实测对齐 + reports 门禁目录与 audit wrapper 入库（7 文件）
> * 均未 push。无关项处置：OUTFILE/nul 已删除；T1 验收报告剥离水杉 AIGC 合规块
>   （与项目内容无关）后归位 reports/T1-acceptance.md 入库，带水印原件留在 memory/ 不入库。
> * 本文档性质转为执行凭证，留在 analysis/ 作轮次记录。

> 生成：2026-11-10 ｜ 性质：**方案建议，交主人拍板**——未经授权不擅自 commit。
> 盘点口径：git status 全量（24 M + 8 ??）。

## 一、改动全景

两轮统帅轮（09时/10时，均已 FIST 归档）+ 本轮 11时 的改动全部在工作区：
- 测试基建修复 5 文件（GUI 守卫×2 / desktop skip / 环境分档×2）
- 新测试 4 文件（signals 21 用例 / runtime 15 / errorcodes 8 / sip 4）
- 产品修复 1 处（SIP 判据，platform.py）
- 打包面清理（pyproject / README）
- 账本 3 处（CHANGELOG / REFACTOR_COMPLETION / PROBE_PLAN）
- Find_BUG 存档收尾（TRIAGE_R103.md + 12 个 STALE 头注释）
- 上一轮 T0r2（11-08 并行轮）遗留未跟踪：验收报告 memory/、审计工具 actus/tools/audit/、reports/

## 二、建议提交分组（4 个 commit）

### C1 actus 测试基建修复与专项单测补齐（统帅轮-09时）
```
actus/tests/test_tkdialog_gui_contracts_r77.py     # 真 Tk() 探测守卫（32 ERROR→skip）
actus/tests/test_panel_contracts_r53.py            # 同款守卫（20 ERROR→skip）
actus/tests/test_desktop_exec_contracts.py         # fastapi importorskip
actus/tests/test_python_pkgs_contracts_r95.py      # pkg_resources 可用性分档
actus/tests/test_system_tools_contracts_r95.py     # locale 分档（UTF-8 mode）
actus/tests/test_analyze_actions_signals.py        # 新增 21 用例
actus/tests/test_runtime_dep_resolution.py         # 新增 15 用例
actus/tests/test_error_codes_coverage_r102.py      # 新增 8 用例
actus/pyproject.toml                               # 死 glob 清理
actus/README.md                                    # 资源面描述修正
```
提交说明草案：`test: GUI 探测守卫防半可用环境 ERROR；补 analyze_actions/runtime:/错误码 44 用例；清理打包死条目（统帅轮-09时，基线 5710+76 全绿）`

### C2 SIP 探测安全语义反转修复（统帅轮-10时）
```
actus/vools/actus/probe/platform.py                # "status: enabled" 判据
actus/tests/test_platform_sip_r103.py              # 4 用例（disabled 误报为关键回归点）
```
提交说明草案：`fix: SIP disabled 被 "enabled" 子串误报为开启（disabled ⊃ enabled）；判据改 "status: enabled" + 4 回归用例`

### C3 Find_BUG 全景甄别存档（统帅轮-10时/11时）
```
actus/Find_BUG/TRIAGE_R103.md                      # 14/14 定性表（零真 bug 遗留）
actus/Find_BUG/repro_*.py × 12                     # STALE-已修头注释（逻辑零改动）
```
提交说明草案：`docs: Find_BUG 14 repro 全景甄别——全部已修零遗留，脚本加 STALE 头转证据存档`

### C4 账本对齐与轮次记录（统帅轮-09时/10时/11时）
```
actus/CHANGELOG.md                                 # 两轮 Unreleased 条目
actus/docs/REFACTOR_COMPLETION.md                  # §六.1/§六.4 实测反转与对齐
analysis/PROBE_PLAN.md                             # §984 收口 + devtools 反例过时修正
memory/T0r2.4.2-m-file-triage.md                   # 上一轮 M 文件厘清记录
actus/tools/audit/_run_audit_wrapper.py            # T0r2 轮审计 wrapper（tools/audit 既有工具族配套，已追踪目录）
reports/README.md                                  # docs_check 门禁要求的报告目录说明（整目录未追踪，本轮入库）
```
提交说明草案：`docs: 三本账实测对齐（REFACTOR §六.1 42→1、§六.4 已实现、PROBE_PLAN §984 收口）+ reports 门禁目录与 audit wrapper 入库`

### C4-附：T1 验收报告归位（可选，随 C4 一起）
```
memory/vools-actus-infra-T1-acceptance.md → reports/T1-acceptance.md（git mv 语义：落新位置后原路径不入库）
```
依据：reports/README.md 明言「T1-acceptance.md：T1 轮验收报告」但该文件缺位，
验收报告实际躺在 memory/ 下且带 AIGC 合规头——按门禁约定归位 reports/。
**注意**：该报告带水杉 AIGC 合规标注块（Label/ContentProducer 等），入库前请主人
确认该合规块是否应随文件进公开仓库（拍板点，不擅自定）。

## 三、不入库项（待主人拍板处置）

| 项 | 性质 | 建议 |
|---|---|---|
| `actus/OUTFILE` | repro_a1_debug 运行残留（11 字节），删后复跑可再生 | 删除 + 给 repro_a1_debug 改输出路径或 .gitignore |
| `nul`（仓库根） | Windows NUL 设备名残留 | `del \\?\E:\IDEProjects\AI\vools\nul` 删除 |
| `reports/` 内其余报告 | 门禁要求目录，README 已入库 | 后续轮次验收报告按约定落 reports/ |

## 四、拍板动线

主人回复其一即可：
- 「按方案提交」→ 统帅按 C1→C2→C3→C4 顺序逐组 commit（不 push）
- 「C1/C2 先提，其余再说」→ 分组执行
- 「先不提交」→ 继续在工作区漂着（不推荐：改动跨三轮迭代，丢现场风险高）
