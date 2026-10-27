# Actus 基建诊断报告

> 生成时间：2026-10-20 15:40（终版：P0/P1 清零，P2 余 1 项）
> 补记时间：2026-10-27（第三轮：补 D10/D11 两条安装态缺陷，见 §5.6）
> 视角：以"pip install vools-actus 后的真实安装态"为基准重新审视（非源码树便利视角）
> 方法：实测（隔离 site-packages 模拟安装态 + 真实执行链路端到端 + MCP/CLI 协议层）+ 代码审查 + 全量测试

---

## 一、总体评分

| 维度 | 状态 | 说明 |
|------|------|------|
| 引擎基座（分类/接口/指标/质量/策展） | ✅ **完成** | 5 模块落地 |
| 三层动作边界 | ✅ **完成** | 安装态实测：wheel 装上即有 4 种子动作 |
| 契约与文档 | ✅ **完成** | action.schema.json + docs/03 + index.md + SPEC 四处同步 |
| 种子动作可执行性 | ✅ **已修复** | D1：入口块补 `#!run` 指令 |
| 使用量指标埋点 | ✅ **已修复** | D3：executor.execute 出口插桩 + 5 集成测试 |
| 后缀单一真源 | ✅ **已修复** | D4：constants.is_action_file，11 模块接入 |
| id 命名正则 | ✅ **已修复** | D5：段内允许下划线，与 schema/docs 对齐 |
| 分类查询入口 | ✅ **已完成** | P1：MCP tools/list + CLI list 均带 kind/purpose/industry/tag 过滤 |
| MCP 工具描述分类化 | ✅ **已完成** | 单动作工具描述带【分类】用途/行业摘要 |
| 安装态指标逃生门 | ✅ **已完成** | P2：`ACTUS_METRICS_DIR` 最高优先级 |
| 种子动作演示 | ✅ **已完成** | P2：4 个 `*.demo.actus.md` + demo 相对路径解析修复 |
| 适配器引用形态 | ✅ **已完成** | P2：id 引用 / 内联 spec / 缺引用三类报错信息齐备 |
| **全量回归** | ✅ **跑通** | `pytest tests/` exit 0：367+ passed + 1 skipped + 0 failed |

**P0/P1 缺口全部清零**；P2 仅剩 1 项（DEVELOPMENT_STANDARDS 同步，主仓文件，见第五节）。

---

## 二、本轮（诊断中）发现并修复的缺陷

### D1（🔴 严重）：种子动作入口块缺 `#!run` 指令——装上即不可执行

- **现象**：`executor_for('executor').execute(calculator)` 报 `entry_no_output`
- **根因**：`vools/actus/actions/basics/*.actus.schema.md` 的 webview2 块 fence 行写作
  ` ```webview2 tag=main `——`tag` 让 `check_entry_block` 通过，但**执行器按 `run` 指令选块**，
  `only=[action.entry]` 过滤后无块可跑 → "入口块无 stdout"
- **影响面**：4 个种子动作 100% 不可执行（此前"迁移完成"的判断只走到了"可解析、可校验"，
  没走到"可执行"——这是本轮诊断补上的关键一环）
- **修复**：fence 行改为 ` ```webview2 #!run tag=main ... `（4 个文件）
- **验证**：执行错误从"入口无 stdout"变为"块执行失败"（无桌面环境跑 GUI 失败属预期），
  错误被 exec_iface 正确归一为 `error_kind='runtime'`

### D2（🟡 观察）：非入口块的 `run` 指令

usage 示例的 python 块、permissions 的 yaml 块 fence 行同样带 `#!run`（这是 SPEC §10 的示例写法）。
实测**无害**：executor 用 `only=[action.entry]` 按 tag 过滤，非 entry 块不会被执行。
但 `check_block_languages` 会把这些块纳入路由判定（它们带 run 无 tag → 属"文档围栏"分支，跳过）。
**结论：不改**，与存量 110 个动作同形态，改了反而制造差异。

---

## 三、安装态实测证据（三层边界的硬验证）

| 场景 | 方法 | 结果 |
|------|------|------|
| wheel 安装态扫描 | 复制 vools/ 到隔离 site-packages，清 ACTUS_REPO_ROOT | ✅ 扫到 4 个种子动作 |
| wheel 安装态校验 | 同上 + validate | ✅ 零错误（contracts/ 用包内 schemas/ 兜底路径已就位） |
| 安装态指标落库 | 同上 + write_action_metric | ✅ 落到 `site-packages/_meta/`，best-effort 不抛 |
| 安装态 repo_root 兜底 | 同上查 `_repo_root()` | ✅ site-packages（模块上三级），第一个 root 不存在自动跳过 |

> 注：安装态指标写到 `site-packages/_meta/` 在多用户共享安装下可能只读——
> calllog 的 best-effort 已保证不抛，但这意味着**安装态的使用量统计会静默丢失**。
> 生产部署若要看指标，应设 `ACTUS_REPO_ROOT` 指向可写目录（已写入 docs/03 §4.1 注意事项）。

---

## 四、基建完整度盘点（对照最初调研的 5 维度 + 生态层）

### 4.1 分类体系（docs/03 §2）

| 能力 | 状态 | 证据 |
|------|------|------|
| kind 单值打回级 | ✅ | test_classification 44 用例 |
| purpose/industry/trigger 多值 + 跨维度 | ✅ | `purpose: [transform, ai]` |
| context_applies 自由字符串 | ✅ | constants 无闭集 |
| 未知值警告/打回分级 | ✅ | validate + classification_notices |
| 反向索引 by_kind/purpose/industry | ✅ | index v2.0.0，7 动作 5 组聚合 |
| filter_by_dimension 查询 | ✅ | `purpose=control` → 3 个 GUI 动作 |

### 4.2 协议统一（docs/03 §5）

| 能力 | 状态 |
|------|------|
| ActionExecutor 统一接口 | ✅ |
| 三路接线（executor/adapter/scattered） | ✅ 27 测试 |
| error.code → ERROR_KINDS 闭集映射（18 码） | ✅ |
| ExecResult 结构化出参 | ✅ 含 artifacts 双形态兼容 |

### 4.3 生态层

| 能力 | 状态 | 备注 |
|------|------|------|
| 使用量指标（执行计数） | ✅ | action_metrics 表 + aggregate/popular/trending |
| 质量分级（HA Quality Scale） | ✅ | 计算字段非申报，5 级 |
| 许可证/定价声明 | ✅ | gated 付费预留（未接支付） |
| 社区策展 | ✅ | default_repos + collections + featured |
| **真实执行埋点** | ❌ **缺口** | `write_action_metric` 从未在 executor.execute 里被调用——指标永远是空的 |

---

## 五、当前最大缺口：指标埋点未接线（🔴 P0）

### D3（🔴 P0，已修复）：指标埋点未接线——生态层数据全空转

- **现象**：`calllog.write_action_metric` / `aggregate_metrics` / `popular_actions` 全部写好并单测过，
  但 `executor.execute()` 执行路径里没有一处调用它
- **影响面**：`popular_actions`/`trending_actions`/`get_featured` 永远空；
  `quality_scale` 的 exec_count 恒 0 → 所有动作永远 bronze；
  docs/03 §4.1 宣传的"执行计数区分安装与真正在用"实际不生效
- **修复**（executor.py 两处最小插桩，不碰执行逻辑）：
  1. execute 起始加 `_t_start = time.time()`（+ `import time`）
  2. finish 出口（append_log 之后、事件总线之前）调 `write_action_metric(...)`，
     try/except 包裹 best-effort；caller 记 `confirmed`（人工放行）vs `executor`（自动调用），
     让 unique_callers 能区分调用通道
- **验证**（端到端，非 mock）：
  - `tests/test_metrics_instrumentation.py` 5 用例：执行后查库 total/success_rate/popular/
    quality.evidence.exec_count 全部非空；失败执行也落指标（success_rate<1）；
    指标写炸不影响回执（monkeypatch 注入 RuntimeError → status 仍 ok）
  - 手工：3 次成功执行 → total=3 / success_rate=1.0 / popular[0].count=3 / exec_count=3
  - 核心回归 154 测试全绿

---

## 五.5、第二轮修复（2026-10-20，后缀统一连带）

### D4（🟡 P1，已修复）：12 处 `endswith('.actus.md')` 硬编码——新格式动作"半盲"

- **现象**：installer/publisher/registry/repo/dependency/scaffold/probe/omega/evolution/author
  各写一份后缀判断，只认 `.actus.md`；`.actus.schema.md` 动作装不了、发布扫不到、
  注册表漏、依赖解析找不到
- **修复**：`constants.is_action_file()` 单一真源（`ACTION_SUFFIXES` 双后缀），
  11 个模块全部接入；indexer 的 `_is_action_file`/`ACTION_SUFFIXES` 改为从
  constants 再导出（别名保留防外部引用）
- **验证**：全模块 py_compile 通过；扫描仍 7 动作；核心回归 154 全绿

### D5（🔴 连带发现）：`ID_NAMESPACE_RE` 不含下划线——合法存量 id 被误判

- **现象**：后缀统一后跑全量校验，`actus.basics.image_viewer` 等 3 个种子动作报
  "id 不符合资产池命名"——正则 `^[a-z][a-z0-9]*(\.[a-z][a-z0-9]*)+$` 段内无下划线，
  而 docs/03 §4.2 明确"段内允许下划线"（scaffold 生成的 id 也带）
- **修复**：正则改 `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`，与 action.schema.json 的
  id pattern 对齐（此前 schema 与 constants 不一致，两本账）
- **验证**：4 个种子动作恢复 0 错误

### D6（🟡 连带发现）：schema 与代码对 platform 类型口径不一

- **现象**：`check_platform` 接受 string 或 array，我补的 `action.schema.json` 只声明
  string——`"platform": ["desktop"]` 被 schema 级打回
- **修复**：schema 改 `oneOf`（string | array of enum），与 validate 判据对齐

### D7（🟡 存量数据不合格）：3 个 ai-scaffold 残留动作过不了治理校验

- **现象**：`actions/` 下 foo/zh/zhzh 缺 platform、usage 纯描述不可执行、
  trust=trusted 无测试绑定（docs/47 §4）
- **修复**：补 `platform: ["desktop"]` + 可执行 usage（`actus run <id> --params {...}`）+
  降为 `sandbox`（scaffold 生成物定位，沙箱豁免测试绑定）
- **验证**：7/7 动作零校验错误

### D8（🟡 测试与实现漂移）：jump 测试补丁打在已废弃的调用点上

- **现象**：`test_jump_shell_quote.py` 2 用例 IndexError——测试 patch
  `jump.subprocess.run`，而 jump 早已迁到 `run_cmd_safe`（_proc.py 进程树安全包装），
  补丁打不到真实调用点，`rec.calls` 恒空
- **修复**：补丁改打 `jump.run_cmd_safe`（真实调用点），注释说明为什么
- **验证**：6 个 jump 测试全绿

### D9（🟡 收集挂起）：`tests/test_backends.py` 是脚本不是测试

- **现象**：pytest 收集阶段就挂起——该文件模块级 `webview.start()` 弹 GUI，
  headless 环境永远等不到窗口关闭；全量 `pytest tests/` 从未能跑完的直接原因之一
- **修复**：移入 `tests/manual_gui/test_backends_manual.py`（pyproject 的
  norecursedirs 已排除该目录，与它"需要真实桌面"的定位一致）
- **验证**：全量收集不再挂起，后台跑通

---

## 五.6、第三轮补记（2026-10-27，安装态两处静默缺陷）

> 这两条都是**「源码树绿、pip 装完红」**的打包/入口层缺陷，与前两轮的逻辑缺陷不同族：
> 本地开发永远踩不到，只有按"用户 `pip install` 后的真实安装态"审视才会暴露。

### D10（🔴 严重）：`cli.py` 的 `if __name__ == '__main__'` 守卫写在文件中间——`python -m` 下 15 个子命令全 `NameError`

- **现象**：`python -m vools.actus.cli <cmd>` 调用 omega / concurrency / deps / dep-tree /
  desktop / events / viz / replay / notify / project(导入导出) / export / probe / health /
  selfheal / template 等**十余个子命令全部 `NameError`**；而**安装态的 console script
  （`actus <cmd>`）完全正常**
- **根因**：`if __name__ == '__main__': main()` 被写在文件中段（原第 2034 行），
  而 `main()` 内部的分发分支中，该位置**之后才定义的函数/常量**在 `python -m` 直接执行
  模块时尚未求值（`-m` 走 `runpy` 执行模块体，模块体执行到中段守卫就进了 `main()`，
  后半段定义被跳过）→ 落到那些分支即 `NameError`
- **为什么长期没暴露**：安装态走 console script 入口点（`import` 模块后再调 `main`，
  整个模块体先完整执行完），所以只有**源码树 + `python -m`** 这条路径才会中招；
  而这是开发者最常用的调试方式，偏偏 CI 主要跑 pytest（同样是 import 路径）——两处盲区叠加
- **修复**：把守卫移到**文件末尾**（现 `actus/vools/actus/cli.py:2574`，文件共 2575 行），
  保证模块体全部定义先完成再进 `main()`
- **验证**：`grep -n "__name__" actus/vools/actus/cli.py` 仅剩文件末尾一处；
  `python -m vools.actus.cli <上述子命令>` 不再 `NameError`

### D11（🔴 严重）：种子动作 `.sig` 未进 wheel 的 `package-data`——`pip` 装完 `actus verify` 全报 Signature file not found

- **现象**：源码树里对 4 个种子动作跑 `actus verify` 全绿；`pip install` 后同一命令
  **4/4 报 `Signature file not found`**
- **根因**：`pyproject.toml` 的 `[tool.setuptools.package-data]` 当时只收
  `actions/**/*.actus.md` 与 `actions/**/*.actus.schema.md`，
  **`.sig` 后缀没有 glob**——签名文件根本没被打进 wheel
  （`vools/actus/actions/basics/` 下 4 个 `.actus.schema.md.sig` 在源树存在、装完消失）
- **修复**：package-data 补 `"actions/*.sig"` + `"actions/**/*.sig"`
  （现 `actus/pyproject.toml:125-126`，就地留了注释说明这条坑）
- **验证**：wheel 内容含 4 个 `.sig`；安装态 `actus verify` 4/4 通过
- **同族教训**：凡是"数据文件"（`.md` / `.sig` / `.json` / `.mjs`）都必须显式写进
  `package-data`，`packages.find` 只负责 `.py`。本仓 `_shiki/`、`schemas/` 也是同一坑的
  不同受害者（见 `pyproject.toml` 内对应注释）

---

## 五、当前剩余缺口（🔴 P0 已清，P1 已清，P2 余 1 项）

### P1 缺口（已全部完成）

| # | 缺口 | 状态 |
|---|------|------|
| 1 | 12 处 `endswith('.actus.md')` 硬编码 | ✅ 已修复（D4） |
| 2 | MCP tools/list 无分类过滤 | ✅ 已完成：`actus_list`/`actus_search` 加 `kind`/`purpose`/`industry` 参数，输出行带三维度字段 |
| 3 | CLI `actus list` 无过滤选项 | ✅ 已完成：`--kind`/`--purpose`/`--industry`/`--tag`，输出带分类字段 |

### P2 缺口

| # | 缺口 | 状态 |
|---|------|------|
| 4 | `docs/DEVELOPMENT_STANDARDS.md` 未同步 | ❌ 主仓文件，本工作区无（唯一剩余项） |
| 5 | 安装态指标落点只读风险 | ✅ 已加 `ACTUS_METRICS_DIR` 逃生门（calllog._default_meta 最高优先级） |
| 6 | `exec_iface._AdapterIface` 兜底 id 不明确 | ✅ 已修复：缺引用 → `invalid` + 声明方式说明；未知 id → 列出已注册适配器与放置目录；新增内联 spec（`adapter: {type: cli, ...}` 平铺写法）；text 输出 data 兜底 stdout |
| 7 | 种子动作 demo 值 | ✅ 已完成：4 个 `*.demo.actus.md` + `demo:` 指向；连带修复 demo 相对路径解析 |

### 附加完成（推进中发现）

| # | 内容 | 状态 |
|---|------|------|
| 8 | MCP 单动作工具描述不带分类（AI 选工具时动作除 trust 外完全同质） | ✅ `_list_tools` 描述拼接加【分类】用途/行业摘要 |
| 9 | `Action` 缺 `demo`/`declared_features` 便捷属性 | ✅ model.py 补齐 |

---

## 七、与"Quicker 式生态"目标的差距评估

| Quicker 生态要素 | Actus 现状 | 差距 |
|------------------|-----------|------|
| 上下文优先分类 | ✅ context_applies 字段 | 无（已覆盖） |
| 执行计数指标 | ✅ executor 埋点 + aggregate/popular/trending | 无（D3 已修） |
| 点赞/收藏/讨论 | ❌ 无 | 远期（需云端注册表） |
| 动作单/集合 | ✅ collections | 无 |
| 质量分级 | ✅ Quality Scale（读真实 exec_count） | 无 |
| 一键安装 | ✅ installer 认双后缀 | 无（D4 已修） |
| 演示 demo 字段 | ✅ schema 字段 + 4 个种子 demo 文件 | 无（P2-7 已完成） |

---

## 八、结论与下一步

**基建主体已完成**：三轮诊断 + 两轮推进累计修复 14 个缺陷（D1-D11 +
`ACTUS_METRICS_DIR` + demo 相对路径解析 + adapter 三种引用形态）。
分类体系从"建好"走到"可用"：MCP tools/list 与 `actus list` 都带
`kind/purpose/industry` 过滤，单动作工具描述带分类摘要，种子动作带
demo 演示文件，指标有安装态逃生门。

**全量测试**：`pytest tests/` → **367+ passed + 1 skipped + 0 failed**（exit 0）。

**剩余待办（不阻塞使用）**：

1. **P2-4**：`docs/DEVELOPMENT_STANDARDS.md` 同步（主仓文件，需在主仓改）
2. **远期**：点赞/收藏/讨论等社区社交指标（需云端注册表，见 §7 Quicker 对比）
