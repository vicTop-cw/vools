---
AIGC:
    Label: "1"
    ContentProducer: [REDACTED-AIGC-PRODUCER-ID]
    ProduceID: [REDACTED-AIGC-TRACE-ID]
    ReservedCode1: SkLzrS/4xAdMIBJdvKHzgbRFO8DOFFos720xEsVRDsxJFWQYq8Vqx/oxLHjqyIaPguJWUyBAi60AhmcDQYijbm15MyvttnV1skrRCBHREyBd4HfQHkadOBNuhvpGGVqhkxn6ax5TRP0Nrw0hMQkqTKtqFvq0tRZlzk8c8cd8WYe9UExRngPhJdMEKNk=
    ContentPropagator: [REDACTED-AIGC-PRODUCER-ID]
    PropagateID: [REDACTED-AIGC-TRACE-ID]
    ReservedCode2: SkLzrS/4xAdMIBJdvKHzgbRFO8DOFFos720xEsVRDsxJFWQYq8Vqx/oxLHjqyIaPguJWUyBAi60AhmcDQYijbm15MyvttnV1skrRCBHREyBd4HfQHkadOBNuhvpGGVqhkxn6ax5TRP0Nrw0hMQkqTKtqFvq0tRZlzk8c8cd8WYe9UExRngPhJdMEKNk=
---

# Actus 改造计划：多形态参数解析 + 动作规范性扩展

> 状态：**规划稿（暂不实施）** · 2026-10-16
> 范围：① `actus run` 及子命令的目标/入参多形态解析；② 动作规范性扩展（无源码动作、任意语言入口、link/demo/template 等动作类型）
> 依据代码：`vools/actus/cli.py`（CLI 主入口，`main` L115 / `_dispatch` L805）、`vools/actus/{indexer,executor,scattered,runtimes}.py`、`bridges/vools/bridge/md/runner.py`、`contracts/action.schema.json`、`docs/03-动作规范.md`、`docs/DEVELOPMENT_STANDARDS.md`

> **实现状态（核实于 2026-11-08，T0r3.2.2 复跑）** —— 上方「规划稿（暂不实施）」**已过时**，实际已实施 **100%（28/28）**：
> 已实现（28）：任意语言入口（`known_languages`/`is_routable` 路由）、
> 四种新 kind 的执行语义（link/demo/template/bundle/doc，见 `executor.py`）、
> `by_name` / `by_md5` / `by_kind` 反向索引（`build_index`）、`brief` 增加 `name`/`kind`/`md5`/`platform`/**`languages`**（复跑实测已落盘）、
> verify 校验面扩展（入口语言白名单、无源码动作入口豁免、kind 合法性 `validate.is_known_kind`、link/alias target 存在性校验、md5 一致性告警，均复跑实测 OK）、
> `actus run` 多形态 target 解析（resolver）、文档同步等。
> 遗留开放问题（非实现条目，已核实澄清 2026-11-11）：§六.6 `_find_action_file` **并非旧式残留**——`785601e6` 已收口到 `resolver.find_action_file`，`vools/actus/{author,dependency,omega}.py` 三处保留的 `_find_action_file` 均为**委托 resolver 的兼容薄壳**（保留签名供测试/调用方引用，见 §六.6 更新声明），审计脚本已同步改为区分旧式实现与薄壳，复跑不再误报 MISS。
> 核实方法（**可复跑**）：`cd actus && python tools/audit/plan_audit_actus.py`
> （脚本自建临时 `ACTUS_META_DIR`，不污染仓库）。

---

## 一、目标与范围

### 1.1 目标 A：多形态目标与入参

`actus run <target> <jsonexpr>` 中的 `<target>` 需支持以下全部形态，其它子命令按需对齐：

> **实现状态（2026-11-11）**：**完成** —— 全部子命令已接入 resolver：
> `run` 走 `resolve_target`（cli.py:935）；`validate`/`info`/`preview` 走
> `_resolve_cli_target`（cli.py:1858，内部调用 `resolve_target(raw, allow_hosts=[])`）。
> 目标五源（id/name/md5/path/url）与扩展入参（JSON URL / `@action:`）均已落地。

| 形态 | 示例 | 现状 |
|---|---|---|
| 动作 id（反域名） | `actus.cli.jq` | ✅ 支持 |
| 本地零散动作路径（文件） | `./actions/foo.actus.md` | ✅ 支持 |
| 本地零散动作路径（目录） | `./lib/foo.actus/` | ✅ 支持 |
| 动作名称（可读名） | `bench_polyglot` | ✅ 支持（resolver 五源含 name，查索引 `by_name`） |
| 动作唯一指纹（内容 MD5） | `9f2c…`（32 hex） | ✅ 支持（resolver 五源含 md5，查索引 `by_md5`） |
| URL（http/https 动作源） | `https://…/foo.actus.md` | `run` ✅ 支持（需 `--allow-host`，远程未校验默认拒绝）；`validate`/`info`/`preview` ❌ 拒绝 —— **设计决策**，非缺口：这三个命令不提供隐式下载，远程请用 `run --allow-host`（见 cli.py:1858 docstring） |

`<jsonexpr>` 入参需支持：

| 形态 | 示例 | 现状 |
|---|---|---|
| JSON 字面量 | `'{"a":1}'` | ✅ 支持 |
| 本地 JSON 文件 | `@args.json` | ✅ 支持 |
| stdin | `-` | ✅ 支持 |
| JSON URL | `@https://…/args.json` / `https://…/args.json` | ✅ 支持（`resolve_params_extended`，resolver.py:409；远程下载默认禁，需 `--allow-host` 白名单） |
| 无参动作引用（执行后取其返回 JSON 作入参） | `@action:actus.demo.produce` | ✅ 支持（`resolve_params_extended`，最大递归深度默认 3，含环检测） |

### 1.2 目标 B：动作规范性扩展

1. **无源码动作**：动作可以不含可执行源码，分两类——「展示源码动作」（源码仅展示/展开）与「命令封装型可执行动作」（展示源码被做成可执行文件，新动作内调用命令）。
2. **任意语言入口**：入口代码块不再限定 Python，只要标明代码块语言 + 入口 tag 即可（shell / powershell / cmd / bat / node / go / rust / ruby / php / typescript / …）。
3. **新动作类型文件**：`*link.actus.md`（动作链接，参数可为空）、`*.demo.actus.md`（用法示例）、`*.template.actus.md`（模板生成）及其它类型规划。
4. **配套规范**：命名后缀矩阵、契约要求、校验面、索引扩展。

---

## 二、现状盘点（已核实代码事实）

| 层 | 文件 | 事实 |
|---|---|---|
| CLI 主入口 | `vools/actus/cli.py`（`main` L115 / `_dispatch` L805；唯一 vools 级 `__main__.py` 为 `vools/__main__.py`） | `run`（L925）走 `resolver.resolve_target`：id/name/md5/path/url 六形态（scattered 由 `is_scattered_path()` 判定前置分流），URL 需 `--allow-host` 白名单 + 指纹校验；入参走 `resolve_params_extended`；`info/preview/validate`（L882/L900/L860）走 `_resolve_cli_target`（内部 `resolve_target(raw, allow_hosts=[])`，URL 明确拒绝）；`author`（L1049）/`workflow`（L1058）/`triggers`（L1088）各走专属分支 |
| 入参解析 | `vools/actus/cli.py` `_parse_params`（L1902）/ `resolve_params_extended`（L984，resolver.py L409） | `run` 支持七种入参：JSON 字面量 / `@file` / `-` / `@https://…*.json` URL 下载 / `@action:<action_id>` 递归引用（默认最大深度 3、含环检测）；`preview` 等仍用 `_parse_params`（仅 JSON 字面量 / `@file` / `-`；要求最终是 JSON object） |
| 索引层 | `vools/actus/indexer.py` | `get_action(action_id)` 仅精确 id 匹配 `scan_actions` dict，无 name/md5/url 回退；`build_index` 落盘 `_meta/actions.index.json`，条目为 `brief`（含 name/md5/kind/languages），并含 `by_name` / `by_md5` / `by_kind` 反向索引（indexer.py L403-446） |
| 执行层 | `vools/actus/executor.py` | `execute(action_id, params)` 内部 `get_action(id)` → `load_and_validate` → 依赖/信任/沙箱门禁 → `run_md(path, only=[entry])`；出参 = 入口块 stdout 优先 JSON 解析（docs/03 §7.3.7） |
| 零散动作 | `vools/actus/scattered.py` | `is_scattered_path` 判 `.actus.md` 文件 / `.actus/` 目录；含授权根与路径逃逸防护 |
| 运行时 | `vools/actus/runtimes.py` | 已注册 python / shell(bash,sh,powershell,pwsh,cmd) / node / go / rust / ruby / php |
| 块执行器 | `bridges/vools/bridge/md/runner.py` | `_execute_block` 直接分支：python、shell/bash/sh、webview2、sigma；其余走 `_execute_via_bridge`（编译器桥包 / 注册表别名）；已有 `only-code` 指令（源码展开不执行） |
| 动作 schema | `contracts/action.schema.json` | 字段：id/name/version/trust/visibility/entry(tag)/platform/deps/permissions/args/secrets/triggers/workflow/tags…；已含 `kind` 与 `md5` 字段（kind=exec 时强制 `entry`） |
| 规范文档 | `docs/03-动作规范.md` | §1 定义 / §2 config / §3 trust / §4 代码块规范 / §5 最小示例 / §6 校验（6.1 verify 前置门槛）/ §7 入参出参契约 |
| 开发规范 | `docs/DEVELOPMENT_STANDARDS.md` | 与动作规范交叉引用；改动需同步两处 |

---

## 三、设计

### 3.1 目标解析器（新增 `vools/actus/resolver.py`）

职责：把 CLI 传入的 `<target>` 字符串解析为「动作定位结果」，统一后续管线。

```
输入形态判定顺序（首命中即返回，避免歧义）：
  1. is_scattered_path()  →  本地 .actus.md 文件 / .actus/ 目录
  2. 含 "." 且不含 "/"、不匹配 hex32、不匹配 URL → 视为 action_id（保持现状）
  3. 32 位 hex → 按指纹查索引
  4. http:// 或 https:// 前缀 → URL 动作源
  5. 其余（无特殊前缀的短串）→ 按 name 查索引
```

解析结果结构（`ResolvedTarget`）：

```python
{
    "source": "id|name|md5|path|url",
    "action_id": "actus.cli.jq",        # 解析后可得
    "path": "...",                       # 本地文件路径（path/url 已落盘后）
    "raw": "原始输入串",
    "ambiguous": [],                     # 多命中时的候选列表
}
```

### 3.2 入参解析器扩展（改造 `_parse_params`）

新增两种来源，保留原有三种，最终仍归一为 JSON object：

| 形态 | 解析动作 |
|---|---|
| `@https://…` / `https://…/*.json` | 下载 → JSON 解析；需 `--allow-host` 白名单 + 超时 + 大小上限 |
| `@action:<action_id>` | 递归执行该动作（无参）→ 取其出参 JSON → 作为本动作入参；需最大递归深度（默认 3）与循环检测 |
| 其余 | 原逻辑不变 |

### 3.3 动作类型（kind）体系

在 `config` 区新增可选字段 `kind`，默认 `exec`（现状语义）：

| kind | 语义 | 入口要求 |
|---|---|---|
| `exec`（默认） | 可执行动作 | 必须有 `entry` 指向可执行代码块（任意语言） |
| `link` | 动作链接 | 无源码；`target` 指向另一个动作；参数做浅合并后转发 |
| `demo` | 用法示例 | 只含 `#!only-code` 块 + 说明；`run` 走"演示模式"（执行并展开源码） |
| `template` | 模板生成 | 无 entry；执行 `scaffold` 生成动作文件 |
| `alias` | 别名 | 无源码；`target` 指向另一个动作 id |
| `bundle` | 动作集 | 无源码；列出成员动作 id 列表 |
| `doc` | 纯文档 | 无源码；仅渲染 |

### 3.4 任意语言入口

- 入口块语言标记放开：`python`/`shell`/`bash`/`sh`/`powershell`/`pwsh`/`cmd`/`bat`/`node`/`go`/`rust`/`ruby`/`php`/`typescript`/`zig`/`nim` 等，只要 runner 能路由即可。
- `docs/03 §4` 增补：入口 tag（默认 `main`）语义不变；"入口块必须是 python" 的硬约束删除，改为"入口块必须可执行"。
- `only-code` 语义扩展：demo 动作的全部块默认视为 `only-code` 展开。

### 3.5 索引扩展（`indexer.py` + `_meta/actions.index.json`）

索引条目在现有 `brief` 基础上增加：

```json
{
  "brief": "…",
  "name": "jq 命令行工具",
  "kind": "exec",
  "md5": "9f2c…",
  "languages": ["python"],
  "platform": "all"
}
```

并新增反向索引：`by_name`（小写归一，多值）、`by_md5`（单值）、`by_kind`（分组计数）。

> **实现状态（2026-11-08，T0r3.2.2 复跑）**：`by_name` / `by_md5` / `by_kind` 已落盘；
> 条目中的 `name` / `kind` / `md5` / `platform` 已进 `brief`；
> **`languages` 字段已落盘**（复跑实测 `brief 含 languages: True`）→ 本条已完成。

### 3.6 校验面扩展（verify 前置门槛）

| 规则 | 说明 |
|---|---|
| 入口语言白名单校验 | 入口块语言必须在"可执行语言集合"内，否则 verify 报错 |
| kind 合法性校验 | kind 必须属于 `{exec,link,demo,template,alias,bundle,doc}` |
| link/alias 的 target 存在性校验 | target 必须能解析到已注册动作（本地或索引） |
| 无源码动作的入口豁免 | kind ≠ exec 时不要求 entry |
| 指纹一致性校验 | md5 与实际内容不符时告警（不阻断） |

> **实现状态（2026-11-08，T0r3.2.2 复跑，逐项核实）**：
> ✅ 入口语言白名单校验（`validate.check_block_languages`）；✅ 无源码动作入口豁免；
> ✅ kind 合法性校验（`validate.is_known_kind`）；
> ✅ link/alias target 存在性校验（`validate.py` 已含 target 校验）；
> ✅ 指纹（md5）一致性告警（`validate.py` 已含 md5 告警）。
> 复跑：`cd actus && python tools/audit/plan_audit_actus.py`（可复跑，秒级）。

---

## 四、兼容性

1. **CLI 形态兼容**：原有三种 target 与三种 params 形态**完全不变**；新形态通过解析器顺序自然向后兼容（"看起来像 id" 的串仍走 id）。
2. **规范文档同步**：`docs/03-动作规范.md` 与 `docs/DEVELOPMENT_STANDARDS.md` 必须同步改动；规范是校验与实现的契约，不允许代码先于文档漂移。
3. **索引兼容**：`actions.index.json` 为增量字段扩展；旧索引缺 `kind/md5/by_name` 时按默认值回填（kind=exec），不破坏读取。
4. **trust 门禁兼容**：link/alias 等无源码动作不改变 trust 判定（仍按 config 的 trust 字段）；远程 URL 动作默认 trust=audit，需指纹校验通过才允许 run。
5. **MCP 兼容**：MCP 工具描述中把 target/params 的可能形态写清楚，避免调用方猜测。

---

## 五、实施阶段

| 阶段 | 内容 | 出口 |
|---|---|---|
| 0 | 规范定稿：kind 矩阵、后缀矩阵、语言白名单、校验规则表 | 文档可评审 |
| 1 | resolver.py：target 六形态 + params 七形态；CLI 接入 | 新形态跑通、旧形态回归无差异 |
| 2 | 任意语言入口：runner 路由放开 + only-code 扩展 | powershell/cmd/bat/node/go 入口可执行 |
| 3 | link/alias/bundle/doc 执行语义（无源码动作族） | link 合并参数执行、template 走 scaffold、demo 可演示 |
| 4 | 索引扩展：name/md5/kind 索引 + verify 校验面扩展 | `by_name/by_md5` 落盘；verify 对 kind/语言/契约新规则报错 |
| 5 | 存量修复与回归：全量 verify 0 error（目标），回归锁跑通 | 已达标（2026-11-11 实测 14 动作全量 validate 0 error / 0 warning） |

依赖关系：0 →（1,3 可并行）→ 2 → 4 → 5 → 6。

---

## 六、风险与开放问题

1. **powershell/cmd 路由**（已关闭 2026-11-11 / T0r5.4.1）：已对齐。`vools/actus/runtimes.py` L167 `aliases = ['bash','sh','powershell','pwsh','cmd']`；L178-182 `_detect_shell` 分支 powershell → `['powershell','-NoProfile','-Command',code]`、cmd/win32 → `['cmd','/c',code]`、else bash/sh；L208-214 按内容返回 `'powershell'/'cmd'/'bash'/'sh'`。bat 调用统一走 `cmd /c` 包装（executor 无 `.bat` 直接 spawn 分支）。测试：`tests/test_runtimes_contracts_r32.py` L284-287（Write-Host→powershell、`$env:PATH`→powershell、`@echo off`→cmd、echo hi→bash）全绿。
2. **名称消歧 UX**（已关闭 2026-11-11 / T0r5.4.1）：已对齐。CLI 统一 `_ambiguous_error(target, candidates)`（`vools/actus/cli.py` L940/967/974/978/1844-1880），候选来源 `details.get('candidates') or details.get('ambiguous')`；MCP 层抛结构化 `ambiguous`（含 candidates）（`vools/actus/mcp_server.py` L254-267）。测试：`tests/test_cli_mcp_cross_entry.py`、`tests/test_mcp_target_forms.py` 全绿。
3. **远程动作信任模型**（已关闭 2026-11-11 / T0r5.4.1）：已落地。`vools/actus/resolver.py` L136-149 `_assert_host_allowed` 空白名单即拒、需显式 `--allow-host`；L44-52 `source/url/sha256/digest_verified` 字段；L70-77 `_is_url/_is_fingerprint`；L90-108 URL 与 32 位 hex 指纹回退。签名支持：L318-338 `--require-signature` 下载同名 `.sig` 并本地可信公钥验签（`SignatureVerifier`），缺失/非法即拒（`remote_signature_missing/remote_signature_invalid`）；CLI `sign` 子命令（`cli.py` L624-626）；demo 目录 `.sig` 先例已复用。测试：`tests/test_trust_model_contracts_r96.py`、`tests/test_trust_model_approval_contracts_r32.py`、`tests/test_resolver_contracts_r100.py` 全绿。
4. **link 参数合并深度**（已关闭 2026-11-11 / T0r5.4.1）：已实现。`vools/actus/executor.py` L228-244 `_deep_merge_params(base, override)` 递归合并 dict、其它类型整体替换；L245-260 `_merge_link_params` 由 `action.meta.get('merge')` 决定，`'deep'` 深合并否则浅合并。测试：`tests/test_link_merge.py`（浅合并不保留 base 的 B、deep 递归合并保留 B 覆盖 A）全绿。
5. **存量 92 error**（已关闭 2026-11-11 / T0r5.4.1）：口径复核——§6 中「92 error」为计划阶段预估；当前代码实际状态为全量 validate 0 error / 0 warning（2026-11-11 实测 `scan_actions` 14 动作 + `validate_action`，check_index=False 与 True 均为 0），阶段五目标「全量 verify 0 error」已达标（见上表）。「42 个错误码无测试引用」口径已另行收口（`tests/test_error_codes_coverage_r102.py` 8 用例全绿，与 92 error 无冲突）。
6. **`_find_action_file`（已核实澄清 2026-11-11）**：原声明「`__main__.py` 中存在旧式文件查找逻辑」已过时——`__main__.py` 已不存在；`785601e6` 已将 author/dependency/omega/installer/publisher 五处旧式查找**收口为 `resolver.find_action_file` 单一实现**，消除双轨漂移。`vools/actus/{author,dependency,omega}.py` 三处 `_find_action_file` 为**委托 resolver 的兼容薄壳**（异常吞掉返回 None），保留函数名仅为兼容下游引用（`test_author_contracts_r84`、`test_omega`、`test_dependency_contracts_r52` 等 monkeypatch/import 依赖此名）。审计脚本按 `def _find_action_file` 名称匹配会产生**误报**（author.py:32 / dependency.py:644 / omega.py:99 均为薄壳而非旧式查找），已同步改进审计判定：仅将含 glob/os.walk/字符串搜内容等旧式特征、未委托 resolver 的实现计入 MISS；`build/lib/vools/actus/` 下副本与源文件 MD5 一致，随构建重新生成，无需单独处理。
*（内容由AI生成，仅供参考）*