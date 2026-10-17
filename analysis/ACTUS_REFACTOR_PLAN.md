---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9f2a11add43fbf12a546606fb2b962ab_d35de711c8ff11f18b7f525400393706
    ReservedCode1: SkLzrS/4xAdMIBJdvKHzgbRFO8DOFFos720xEsVRDsxJFWQYq8Vqx/oxLHjqyIaPguJWUyBAi60AhmcDQYijbm15MyvttnV1skrRCBHREyBd4HfQHkadOBNuhvpGGVqhkxn6ax5TRP0Nrw0hMQkqTKtqFvq0tRZlzk8c8cd8WYe9UExRngPhJdMEKNk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9f2a11add43fbf12a546606fb2b962ab_d35de711c8ff11f18b7f525400393706
    ReservedCode2: SkLzrS/4xAdMIBJdvKHzgbRFO8DOFFos720xEsVRDsxJFWQYq8Vqx/oxLHjqyIaPguJWUyBAi60AhmcDQYijbm15MyvttnV1skrRCBHREyBd4HfQHkadOBNuhvpGGVqhkxn6ax5TRP0Nrw0hMQkqTKtqFvq0tRZlzk8c8cd8WYe9UExRngPhJdMEKNk=
---

# Actus 改造计划：多形态参数解析 + 动作规范性扩展

> 状态：**规划稿（暂不实施）** · 2026-10-16
> 范围：① `actus run` 及子命令的目标/入参多形态解析；② 动作规范性扩展（无源码动作、任意语言入口、link/demo/template 等动作类型）
> 依据代码：`engine/actus/__main__.py`、`vools/actus/{indexer,executor,scattered,runtimes}.py`、`vools/bridges/vools/bridge/md/runner.py`、`contracts/action.schema.json`、`docs/03-动作规范.md`、`docs/DEVELOPMENT_STANDARDS.md`

---

## 一、目标与范围

### 1.1 目标 A：多形态目标与入参

`actus run <target> <jsonexpr>` 中的 `<target>` 需支持以下全部形态，其它子命令按需对齐：

| 形态 | 示例 | 现状 |
|---|---|---|
| 动作 id（反域名） | `actus.cli.jq` | ✅ 支持 |
| 本地零散动作路径（文件） | `./actions/foo.actus.md` | ✅ 支持 |
| 本地零散动作路径（目录） | `./lib/foo.actus/` | ✅ 支持 |
| 动作名称（可读名） | `bench_polyglot` | ❌ 不支持 |
| 动作唯一指纹（内容 MD5） | `9f2c…`（32 hex） | ❌ 不支持 |
| URL（http/https 动作源） | `https://…/foo.actus.md` | ❌ 不支持 |

`<jsonexpr>` 入参需支持：

| 形态 | 示例 | 现状 |
|---|---|---|
| JSON 字面量 | `'{"a":1}'` | ✅ 支持 |
| 本地 JSON 文件 | `@args.json` | ✅ 支持 |
| stdin | `-` | ✅ 支持 |
| JSON URL | `@https://…/args.json` / `https://…/args.json` | ❌ 不支持 |
| 无参动作引用（执行后取其返回 JSON 作入参） | `@action:actus.demo.produce` | ❌ 不支持 |

### 1.2 目标 B：动作规范性扩展

1. **无源码动作**：动作可以不含可执行源码，分两类——「展示源码动作」（源码仅展示/展开）与「命令封装型可执行动作」（展示源码被做成可执行文件，新动作内调用命令）。
2. **任意语言入口**：入口代码块不再限定 Python，只要标明代码块语言 + 入口 tag 即可（shell / powershell / cmd / bat / node / go / rust / ruby / php / typescript / …）。
3. **新动作类型文件**：`*link.actus.md`（动作链接，参数可为空）、`*.demo.actus.md`（用法示例）、`*.template.actus.md`（模板生成）及其它类型规划。
4. **配套规范**：命名后缀矩阵、契约要求、校验面、索引扩展。

---

## 二、现状盘点（已核实代码事实）

| 层 | 文件 | 事实 |
|---|---|---|
| CLI 主入口 | `engine/actus/__main__.py` | `run` 在 1422 行 dispatch：`is_scattered_path()` 命中走 scattered 管线，否则 `actuscore.execute(id, _parse_params(params))`；`info/preview/validate` 直接 `get_action(id)`；`check` 吃 path；`author/workflow/triggers` 吃 id |
| 入参解析 | 同上 `_parse_params`（2909 行） | 仅三种：JSON 字面量 / `@file` / `-`；要求最终是 JSON object |
| 索引层 | `vools/actus/indexer.py` | `get_action(action_id)` 仅精确 id 匹配 `scan_actions` dict，无 name/md5/url 回退；`build_index` 落盘 `_meta/actions.index.json`，条目只有 `brief`（无 name 索引、无指纹） |
| 执行层 | `vools/actus/executor.py` | `execute(action_id, params)` 内部 `get_action(id)` → `load_and_validate` → 依赖/信任/沙箱门禁 → `run_md(path, only=[entry])`；出参 = 入口块 stdout 优先 JSON 解析（docs/03 §7.3.7） |
| 零散动作 | `vools/actus/scattered.py` | `is_scattered_path` 判 `.actus.md` 文件 / `.actus/` 目录；含授权根与路径逃逸防护 |
| 运行时 | `vools/actus/runtimes.py` | 已注册 python / shell(bash,sh,powershell,pwsh,cmd) / node / go / rust / ruby / php |
| 块执行器 | `vools/bridges/vools/bridge/md/runner.py` | `_execute_block` 直接分支：python、shell/bash/sh、webview2、sigma；其余走 `_execute_via_bridge`（编译器桥包 / 注册表别名）；已有 `only-code` 指令（源码展开不执行） |
| 动作 schema | `contracts/action.schema.json` | 字段：id/name/version/trust/visibility/entry(tag)/platform/deps/permissions/args/secrets/triggers/workflow/tags…；**无 kind、无 md5 字段** |
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

### 3.6 校验面扩展（verify 前置门槛）

| 规则 | 说明 |
|---|---|
| 入口语言白名单校验 | 入口块语言必须在"可执行语言集合"内，否则 verify 报错 |
| kind 合法性校验 | kind 必须属于 `{exec,link,demo,template,alias,bundle,doc}` |
| link/alias 的 target 存在性校验 | target 必须能解析到已注册动作（本地或索引） |
| 无源码动作的入口豁免 | kind ≠ exec 时不要求 entry |
| 指纹一致性校验 | md5 与实际内容不符时告警（不阻断） |

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
| 5 | 存量修复与回归：全量 verify 0 error（目标），回归锁跑通 | verify 基线达标 |

依赖关系：0 →（1,3 可并行）→ 2 → 4 → 5 → 6。

---

## 六、风险与开放问题

1. **powershell/cmd 路由**：runner 直接分支与 ShellRuntime 方言检测（`_detect_shell` 按内容猜 bash/powershell）之间需对齐；bat 文件调用（`.bat` 直接 spawn）与 `cmd /c` 包装二选一，实施时定。
2. **名称消歧 UX**：多命中时 CLI 交互与 MCP 工具描述如何呈现（候选列表 vs `--choose`），需与 MCP 层对齐。
3. **远程动作信任模型**：下载即执行的供应链风险；建议默认 audit + 指纹校验 + 白名单域名（`--allow-host`），开放问题：是否支持签名（如 demo 目录已有 `.sig` 文件先例，可复用）。
4. **link 参数合并深度**：浅合并是否满足组合场景；深合并的递归规则需示例验证。
5. **存量 92 error**：多语言入口放开后可能新增校验噪音，阶段六需先冻结规则再修存量，避免来回改。
6. **`_find_action_file`**：`__main__.py` 中存在旧式文件查找逻辑（未被 run 使用），实施时评估删除或并入 resolver，避免双轨漂移。
*（内容由AI生成，仅供参考）*