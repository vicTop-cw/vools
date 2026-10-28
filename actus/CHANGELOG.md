# Changelog — vools-actus

本文件记录 `vools-actus` 包的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循语义化版本。

> **依赖提示**：`vools-actus` 依赖 `vools` 与 `vools-bridges`。三者的版本通常同步发布；
> 只升级 actus 而不升级依赖，可能拿到不含对应修复的底层实现。

## [Unreleased]

> 本段记录 **0.9.0 发布之后**、尚未发版的改动。版本号（0.9.1 / 1.0.0）待下次发布时确定，
> 此处不预设。核心是 `actus probe` 环境探测器从「能跑」做到「跑得快、数据可信」。

### ⚡ 性能：`actus probe` 冷启动 **79 052ms → 稳态 ~2 000ms（≈41x）**

| 探测器 | 改造前 | 改造后 | 手段 |
|---|---|---|---|
| 整体（串行 → 线程池） | 79 052ms | 11 136ms | 线程池 + `as_completed` 收结果后按原下标保序 |
| `system_tools` | 10.7–15.3s | **1.48s**（现 1.2–1.5s） | PATH 一次性 `scandir` 建索引预筛（65 条里 42 条是负向查找） |
| `environment` | 6 551ms | **77ms** | `os.scandir` + PATHEXT 判据（≈85x） |
| `python_pkgs` | 6.4–11.1s | **0.88s → 0.079s** | 元数据索引一次读（395→48ms）、`pkg_resources` 门槛跳过（555ms→0）|
| `runtimes` | 3.59–6.83s | **0.38s** | 同一实例按 name+aliases 去重（20 条 items 只有 7 个真实运行时） |
| `compilers` | 1.4–3.9s | **0.39s** | 11 条并发 + PATH 索引 |

- **最终冷探测**：wall **2.13 / 2.21 / 2.50s**，`elapsed_ms` **1 823 / 1 897 / 2 171ms**；
  文档复核时本机复测 **2 045 / 2 189 / 2 212ms**（items=173）。
- 按保守口径折算各探测器贡献：`system_tools` ≈6.5x、`environment` **≈85x**、
  `python_pkgs` ≈12x（再降到 0.079s 后又约 ×11）、`runtimes` ≈10.4x、`compilers` ≈10x。
  （`environment` 按 `6 551ms → 77ms` 实算为 **85x**，不取「≈100x」这类约数 ——
  能被验算的数比听起来漂亮的数有用。）
- **重要结论：并行化只贡献 79s → 11s，剩下 11s → 2s 全靠分探测器优化**。
  「加个线程池就快了」是错的：真正的瓶颈是逐个工具的 `subprocess` 版本探测与 PATH stat 风暴。
- 并发调优是**有数据结论**的，不靠猜：跨探测器共享信号量实测**更慢**
  （重压下不限 2.15s vs 限 24 并发 2.86s —— 它只约束自己、不约束别人），故默认关闭仅留旋钮；
  内层线程数自适应（被外层池调用时 16→8 拿回 29%：2.87s → 2.04s，单跑 16 最优）。
- 全量测试套件耗时 **237s → 107s**（因 probe 提速连带）。

### ✨ 新增能力

- **`analyze_actions()` 兑现 `PROBE_PLAN.md` §4.7**（此前该节只是设计草图，代码里零命中）：
  `analyze_actions(actions_dir=None, probe_report=None) -> dict` 按动作文件声明的 `deps`
  逐项比对探测结果 → `total` / `ready` / `blocked` / `missing_deps` 契约四件套 +
  逐动作 `verdicts`（含 `blocked_reasons` 原因链）+ `undeclared` / `parse_failed` /
  `unverifiable` / `duplicate_ids` / `index_source`。
- **探测报告新增第 3 个条目 `action_readiness`**：`probe()` 报告里**终于有 ready/blocked 字段**
  （items **172 → 173**）；既有两个条目 `actions` / `action_dependencies` 一个字段都没改。
  实跑 **`total=14 ready=14 blocked=0`**，其中 8 个种子动作未声明 `deps`（带 `undeclared` 显式信号）
  —— **真实动作里没有任何一个声明非空 deps，所以"0 blocked"是依赖层面的正确结论**，
  没有为了演示编造 blocked。（限定语见下一条：`ready` 的语义范围仅到依赖层。）
- **`ready` 的语义边界显式化（`ready_scope="deps_only"`）**：`verdict=ready` 只表示
  「声明的 deps 都满足 + 动作文件可解析」，**不保证**入口块的语言/指令被当前引擎支持 ——
  后者只能在执行期确定。实测反例：`actus.basics.calculator` 依赖全满足、`verdict=ready`，
  但 `actus run` 报「块执行失败: 未知指令: devtools」。本包**不做**指令级静态校验
  （支持面随引擎漂移，静态校验极易把能跑的动作误判 blocked = 假阴性），改为把
  `ready_scope` 随 `analyze_actions()` 结果与每个 `verdicts[id]` 一起下发，
  消费方（含 `IntentRouter` 门禁）应把它当作**必要条件而非充分条件**。
- **`runtime:` 依赖前缀真正进 resolver**（`dependency.py`）：此前 `_parse_dep_string` 无该分支，
  `runtime:python` 会被当成一个名叫 `runtime:python` 的动作、永远找不到 → **永远 blocked**。
  现新增 `DepType.RUNTIME` + 解析分支 + `fix_command` + `_check_runtime()`，
  并做抽象名展开（`shell`→bash/sh/powershell、`rust`→rustc/cargo、`node`→nodejs，同名命令优先）；
  `probe/actions.py` 里此前的临时兜底已删除，统一走 resolver 真源。
- **`IntentRouter` 接上依赖级门禁**：`_is_ready()` 从一道门变两道 ——
  ①动作必须在探测报告里（既有语义不变）；②**不得被 `verdicts` 明确判 blocked**（新增）。
  向后兼容三重保险：无 `action_readiness` 条目 / 条目 `available=False` / `verdicts` 结构异常
  → 门禁不启用，绝不因为分析自己炸了就把全部动作误杀。`list_actions()` 改走 `_is_ready()`
  （原先 `route()` / `list_actions()` 各写一遍判据正是漂移温床）。
- **平台特有探测补齐**（新增 `probe/platform_tools.py`）：
  Windows —— VS Build Tools（`vswhere` + `VC\Tools\MSVC\*` + `vcvars64.bat`）、
  WSL（`wsl -l -v`，专门判 **UTF-16LE 无 BOM** 编码、按「最后一列是整数」语言无关解析）、
  Windows Terminal（从商店包目录名取版本，**不执行 `wt.exe`**——空参会弹窗）；
  Linux —— systemd（`systemctl --version` + `/proc/1/comm` + `/run/systemd/system`，
  分 `available` / `usable` 两层）、包管理器（10 候选判家族）；
  macOS —— Xcode CLT（`xcode-select -p` + `clang --version` 实证）、
  **Homebrew**（PATH + `/opt/homebrew/bin/brew` + `/usr/local/bin/brew` 三路 + `--version`/`--prefix`，
  拒绝非 posix 派生路径冒充 prefix）。
  判据全部真实可执行，**探测不到如实报未安装，不伪造**；非本源平台的组不执行；外部命令 5s 兜底。

### 🐛 修复

- **Windows 上 `os.access(path, X_OK)` 对任何存在的文件恒为 True** → `.dll/.pdb/.txt` 全被算成
  「可执行文件」（几万条 → **1 404 条**真可执行，本机 PATH 89 个目录实测）。
  改用 `PATHEXT` 判据 + `os.scandir`。
- **占位值冒充真实版本**：`pywin32` 的 version 是占位串 `'installed'` → 真实元数据版本 **`311`**；
  `cl` 的 version 是**用法文本**（`用法: cl [ 选项... ]`）→ 真实版本 **`19.44.35219`**；
  `unzip` 是告警文本、`scp`/`sftp` 是错误文本 → 全部改为真值或明确 `error_kind`。
- **4 处 `except Exception: pass`（静默吞错）→ 分型记录**：
  `timeout` / `spawn_error` / `empty_output` / `unexpected` / `crashed` / `nonzero_exit`，
  让「没装」与「探测失败」在数据上可区分。
- **探测污染用户工作区**：并发起 JVM 时 mmap 失败，JVM 把崩溃转储
  （`hs_err_pid*.log` / `replay_pid*.log`）写进**进程 cwd**（= 用户执行 `actus probe` 的目录；
  实测仓库 `actus/` 下留下过 4 个）。→ 版本探测子进程统一改用**临时 cwd** + `atexit` 清理 +
  命中崩溃特征串记 `version_error_kind="crashed"`。
- **缓存三处静默错误**（`probe/cache.py`）：`max_age=0` 被 `max_age or _CACHE_TTL` 吞成 3600
  （`--max-age 0` 静默复用 1 小时旧数据）；**未来时间戳让缓存永久有效**；
  `[]` / `{"timestamp":"abc"}` 这类损坏缓存**直接崩**。现全部优雅降级
  （缺失/损坏/形状不对/时钟回拨 → 视为无缓存），并新增 **`schema_version` 闸门**
  （旧缓存不能冒充新报告）+ 原子写（tempfile + `os.replace`）+ `cache_info()`。
- **缓存报告"来源不可辨"**（审计发现：手写一份形状合法的 `_meta/probe_cache.json`，
  `probe()` 会全盘接受 → `platform.os=TotallyFakeOS`、`is_admin=True`、`items=['ghost']`；
  更糟的是其中的 `summary` 被原样当结论，实测能渲染出 `Available: 999 (99900%)` /
  `Unavailable: -998`）。本轮**不做**完整性签名（HMAC/密钥是另一个量级的设计），改为三件事：
  ①`ProbeReport` 新增 `report_source`（`"probe"` / `"cache"`）并进 `--json`，
  人类可读摘要对缓存来源多打一行 `Source: cache (from cache; use --force-refresh to re-probe)`；
  ②缓存命中后**用重建的 items 重算 `summary`**（不再相信缓存里的数字）；
  ③`cache.load_cache` 增加 summary 自洽性校验（`total != len(items)` 或
  `available+unavailable != total` 或出现负数 → 直接判该缓存无效）。
  以上使 **`schema_version` 3 → 4**（旧缓存整体失效一次，避免带着不可信 summary 的缓存继续被消费）。
- **报告夹带 13 个 NUL**：`wsl --version` 是 UTF-16 输出，解码后带 NUL，
  导致 `actus probe | grep` 把整份输出判成 binary。→ 所有取值经 `_clean()` 去控制字符、折叠空白。
- **KPI 曾是自欺欺人**：`elapsed_ms` 在四个维度采集器**之前**计算，实测 wall 13.66s 却上报 8714ms
  （**少报 4.95s**）。现 `elapsed_ms` = 总墙钟，并拆成
  `probers_ms / dimensions_ms / assemble_ms / cache_write_ms` 四段，**四段加和 ≈ elapsed_ms**
  （三次实测差 `+0.0 / +0.1 / +0.2 ms`：四段各自独立 `time.time()` 计时并四舍五入到 0.1ms，
  段间空隙不计入，故严格说是"≈"而不是"恒等于"——这里按可验算的口径写），
  不留黑箱；同时修掉四维度重复采集（`dimensions_ms` 6551ms → 0）。
- **外部命令探测的超时不生效（Windows 特有，影响面不止 WSL）**：`subprocess.run(timeout=...)`
  在 Windows 上**不是真上限** —— CPython 超时后是 `kill()` + **再调一次没有 timeout 的
  `communicate()`** = 等 stdout 管道 **EOF**；当子进程（如 `wsl.exe`）拉起**孙进程**且孙进程
  继承了管道句柄时，这段等待**完全不受超时约束**。
  **合成复现**：上限 0.5s，子进程 spawn 一个 3s 的孙进程 → `subprocess.run` 实际 **4.932s**；
  改为有界实现后 **0.681s**。→ 修法（已落地）：`Popen` + `kill()` + **有限回收**
  `_REAP_TIMEOUT = 0.1s`（`probe/platform_tools.py:101`、`:125-156`）。
  **这不是 WSL 专属坑**：Windows 上任何「会拉孙进程」的命令探测（构建工具、包管理器、
  终端启动器……）都会踩 —— 单条命令的 `timeout` 参数本身给不了上界保证。
- **WSL 探测尖峰**：`wsl -l -v` 与 `wsl --version` 各吃满 5s 超时会叠成 **~10s 尖峰**
  （实测到 10 012ms / 8 284ms）→ 加整组预算（约 1.8s，最坏含开销 ≈1.9s），修复后实测 **0.31–0.88s**。
  这条尖峰的**深层根因**见上一条「超时不生效」；预算只是把症状压住，`Popen` 有界回收才是根因修复。
- **「整个 WSL 不可用」的错误结论**：旧判据是 `available = list_code == 0` ——
  把「`-l -v` 超时、但 `-l -q` 成功」错报成**整个 WSL 不可用**（一个子查询失败 ≠ 平台能力缺失）。
  → 改为「**至少有一条查询应答**」：`responded = any(code == 0 for code in
  (version_code, list_code, quiet_code))`（`probe/platform_tools.py:573-579`），
  并在 `distro_source == "quiet"` 时如实标注数据来源。属「简化判据冒充真实结论」同一族。

### ✅ 验收与证据

- 全量 `pytest tests` → **741 passed, 4 skipped**（本轮起点 711，新增 30 个探针用例）。
- 新增测试：`tests/test_probe_actions.py`（387 行 / 12 用例）、
  `tests/test_probe_windows.py`（385 行 / 9 用例，假 Windows 世界 + 非 Windows 宿主整文件 skip）、
  `tests/test_action_readiness_intent.py`（329 行 / 9 用例），全部不依赖本机装了什么。
- `actus probe --json --force-refresh`：exit=0，items=**173**，`action_readiness` 恒
  `total=14 ready=14 blocked=0`。
- **Linux 分支借 WSL 真跑取证**：WSL Ubuntu 22.04.5（kernel `6.6.87.2-microsoft-standard-WSL2`）
  内加载真实产品代码 → systemd 249 `usable=true`（`/proc/1/comm=systemd` 真 PID1）、
  `apt 2.4.14` + `dpkg 1.21.1` + `snap 2.76.3`（family=debian）、`is_wsl=true`，自检 **17/17**。
- `PROBE_PLAN.md` §4.7 从「设计草图」升级为「实现现状」，§9 复选框
  **30 个 `[ ]` → 28 `[x]` + 2 `[~]`**（未完成项注明原因，并留档了此前一次**虚假勾选**的教训）。

### ⚠️ 已知问题（不阻塞使用）

- **`system_tools` 冷启动尖峰**：稳定态 1.2–1.5s，但同进程内若先跑 `actions`（`os.walk` 扫动作目录
  冲掉文件缓存）后续 PATH 扫描可慢到 ~5.7s；文档复核时另观察到一次 **7 027ms** 尖峰（随后回落）。
  属磁盘缓存效应而非代码回归 —— **KPI 应看安静环境下的数字**。
- **macOS 分支无实跑证据**：SIP（`csrutil`）、Homebrew、Xcode CLT 代码齐备，
  但从未在真 Mac 上执行过（仅平台钩子模拟 + 伪造 brew 验解析链路），故 `PROBE_PLAN` 该项保持 `[~]`。
- **两个测试缺口**（已排期补测，实现本身已提交）：`analyze_actions` 的细粒度信号
  （`verdicts` / `blocked_reasons` / `undeclared` / `unverifiable` / `duplicate_ids`）无专项单测；
  `runtime:` 依赖解析分支无单测。
- `probe/__init__.py` 外层线程池已由 8 调到 **10**（覆盖 10 个探测器）。实测对墙钟无可测影响
  （<1%），属预防性调整：等 `system_tools` 变快后 `platform_tools` 会成为新尾巴。

## [0.9.0] - 2026-10-27

这一版是**以「验收 + 缺陷围剿」为主题的版本**：从 0.8.0（10-17）之后累计 600+ 次提交，
其中 actus 包内 59 次、`bridges`（解析层）26 次、`vools` 核心 433 次。

### ✨ 新增能力（Actus 引擎）

- **无源码动作族全部落地**（`docs/actus/03-动作规范.md` §3.3）：`exec` / `link` / `demo` /
  `template` / `alias` / `bundle` / `doc` 七种 kind 均有执行语义。
  - `link`：按 `target` 转发并做参数合并；新增 `meta['merge'] = 'deep'` 递归合并
    （默认 `shallow` 保持零回归，规则与用例见 `tests/test_link_merge.py`）。
  - `alias`：直接转发；与 `link` 共用深度守卫与成环检测。
  - `demo`：演示模式——执行入口块并把全部代码块按 only-code 展开。
  - `template`：按声明调用 `scaffold` 生成动作文件。
  - `bundle`：列出成员动作清单（不执行成员）。
  - `doc`：仅渲染，不执行任何代码。
- **`resolver` 六形态 target + 七形态入参**：动作 id / 可读名 / 内容 md5 / 本地文件路径 /
  本地目录 / `http(s)` URL；入参支持 JSON 字面量 / `@file` / `-`(stdin) / `@url` / `@action:<id>`。
- **MCP 工具接入 resolver**：`actus_info` / `actus_preview` 的 `id` 参数现在真正走解析器
  （此前直接当 action_id 用），工具描述里写清六种形态。
- **远程动作信任四件套**（`docs/actus` §六.3）：
  - 域名白名单——**默认拒绝所有远程**（配置 `--allow-host` 才放行）；
  - SSL 证书校验（此前被 `CERT_NONE` 关闭）；
  - 内容指纹 `--expect-digest <sha256>`；
  - 签名验签 `--require-signature <公钥名>`（复用种子动作的 ed25519 `.sig` 机制）。
- **CLI**：新增 `--version`；`actus` 无子命令时打印用法（此前静默退出）。

### 🐛 修复（25 个 actus 内缺陷 + 解析层 6 个）

**高危**

- `CronExpr` 的星期字段**整体偏移一天**：docstring 与 cron 标准都是 0=周日，代码却拿
  `time.struct_time.tm_wday`（0=周一）比对，导致所有按星期配置的触发器错一天且完全静默。
- `CircuitBreaker(recovery_timeout<0)` 被接受 → 恢复判据恒为真，断路器永远停在半开、
  **再也不熔断**（保护静默失效）。
- 远程下载 SSL 证书校验被禁用（`CERT_NONE`）；白名单语义反转（空白名单被当成"不校验"，SSRF）。
- `cli.py` 的 `if __name__ == '__main__'` 守卫**写在文件中间**（原第 2034 行）：`python -m
  vools.actus.cli <cmd>` 下 omega / concurrency / deps / dep-tree / desktop / events / viz /
  replay / notify / project 导入导出 / export / probe / health / selfheal / template 等
  **15 个子命令全部 `NameError`**；安装态 console script 走 import 路径，模块体先完整执行
  再调 `main()`，因此长期未暴露。已把守卫移到文件末尾（`cli.py:2574`，共 2575 行）。
  诊断记录见 `docs/INFRA_DIAGNOSTIC.md` §5.6 D10。

**中危**

- 空 `user_id` 被当成合法团队成员（`is_member('')` 为真）；`role` 拼错静默收下（权限静默消失）。
- 心跳/缓存类：`DAG` 缺失依赖被**静默丢边**，本该串行的节点并发执行。
- `md5` 指纹缺失：新格式 `.actus.schema.md` 的动作 `Action.md5` 恒为空 ⇒ md5 target 形态失效。
- 动作文件查找存在**五份**独立实现，其中依赖/安装/自进化/omega 四份用「字符串搜 id」判断身份，
  **认不出新格式 YAML 的 `id: xxx`**（连种子动作都返回 None）；已统一收口到
  `resolver.find_action_file` 单一实现，并加 lint 式守卫禁止回流。
- 格式检测只看后缀 ⇒ `*.demo.actus.md` 等新格式后缀全部解析失败（4 个 demo 文件实测中招）。
- `build_index(actions_dir=…)` 写默认缓存路径 ⇒ 污染主索引、测试出现顺序依赖。
- `IntentRouter` / `Decomposer` / `export` / `viz` 等公开入口**零校验**，其中
  `tags='abc'`、`template='abc'`、`ready_ids='abc'` 会被**逐字符展开**。
- `export_history(format_='zzz')`、`visualize_workflow(format_='zzz')` **静默回退**到默认格式。
- `run_case({})` 抛 `KeyError: 'file'` 等裸错 → 改为带字段名的可读错误。

**解析层（`vools-bridges`）**

- 围栏解析只认**列 0 的反引号**：`~~~` 波浪号围栏、缩进 ≤3 空格的围栏（两者都是合法
  CommonMark）被整块漏掉，4 反引号围栏还会提前闭合且丢语言。
- 裸 `key=value` 指令的引号值被空格截断、引号从不剥离（种子动作 `title` 解析出 `'"Calculator"'`）。
- `validate.check_block_languages()` 走 `vools.bridge.md.runner.is_routable`（单一真源）。

### ✅ 验收与证据

- **`pytest tests` → 691 passed, 1 skipped**（69 个测试文件）。
- 全量逐文件校验 **11 个动作文件 0 失败**；`actus validate` 批量 `valid=true, invalid={}`。
- 4 个种子动作 **签名 4/4 通过**；7 种语言入口（python/bash/shell/powershell/pwsh/cmd/node）
  端到端实跑通过。
- 计划完成度核验报告：`docs/REFACTOR_COMPLETION.md`（逐条映射到证据文件）。

### 🔧 工程改进

- 新增开发规范 `docs/DEVELOPMENT_STANDARDS.md`。
- 新增 lint 式守卫：禁止"字符串搜 id"判断动作身份、禁止单复数分裂的错误码、仓库内动作文件必须可解析。
- 错误码从 63 个收敛（消除 `missing_param`/`missing_params` 单复数分裂），并新增
  `dag_missing_dep` / `dag_cycle` / `remote_*` 系列结构化错误。

### ⚠️ 升级注意

- **远程动作默认拒绝**：此前未配置白名单时会直接下载，现在必须显式 `--allow-host`。
- **`bundle` 空成员**现在报 `param_invalid`（此前返回 `status=ok` 的空清单）。
- **`link` 深链**（>5 跳）与**成环**现在分别报 `param_invalid`（深度超限）与
  `action_ref_cycle`（真环，附完整链路），此前统一报"疑似环"。
- **cron 星期语义修正**：升级后按星期配置的触发器会**提前/推迟一天**触发——这是修正，
  不是回归；依赖旧行为的配置需重新核对。
- CLI 退出码约定：用法错误 `2`、运行期失败 `1`、成功 `0`。

## [0.8.0] - 2026-10-17

该版本已发布到 PyPI，但**当时未写 CHANGELOG 条目**（文档缺口，此处补记）。
据提交记录（121 次提交），主要内容为合规与启动性能：

- 大批模块补 `__all__` 与子包 `README.md`（`bridges` 92 个模块、`actus.probe` 12 个等）。
- **惰性导入**：`bridge.md` 内置语言惰性注册，消除 import 期 WSL 探测 22–37s；
  `webview2` 改 PEP 562 惰性导出，`md.parser` 冷启动 **1.68s → 0.25s**。
- `wsl.check_wsl_command` 增加负缓存 TTL；`bridges/md` 补 Python <3.7 兜底。
- 修 `vDate/VDate` 紧凑日期+时间分支崩溃、`_GroupedObserver` 回调内退订漏通知等。

## [0.7.9] - 2026-10-13

详见仓库根 `CHANGELOG.md`（当时三包同步发布）。要点：`sigma` / `scattered` / `repo` /
`publisher` 四个模块首次进入 wheel；`bridge.md.runner` 新增语言可路由性单一真源。
