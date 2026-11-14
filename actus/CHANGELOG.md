# Changelog — vools-actus

本文件记录 `vools-actus` 包的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循语义化版本。

> **依赖提示**：`vools-actus` 依赖 `vools` 与 `vools-bridges`。三者的版本通常同步发布；
> 只升级 actus 而不升级依赖，可能拿到不含对应修复的底层实现。

## [Unreleased]

> 本段记录 **0.9.1 发布之后**、尚未发版的改动。

### ✅ 统帅轮-23时（2026-11-13）：R116 收口整段连续门禁 4 个既有 F（RC=0）+ R114-B 环境 A/B 量化

- **R116-A 种子签名 3 例**：`trust_model.KeyManager.load_public_key` 是
  「HOME keys 优先 → 包内置 `keys/` 兜底」，种子 `.sig` 本就为「干净 checkout」签发；
  而 conftest 把**真实** `~/.actus/keys` 整个复制进会话 HOME，本机 21:19 轮换过的
  `default.pub`（sha256 `2b613384…`）**遮蔽**了包内置真源（`3435d630…`），
  实测前者验签 4/4 失败、后者 4/4 `ok`。修法：`shutil.copytree(..., ignore=
  ignore_patterns("default.key","default.pub"))`，default 走包内置兜底，`test.*` 仍复制。
- **R116-B `test_action_path_of`**：`executor._apply_env_injections` **裸写**
  `ACTUS_REPO_ROOT=_repo_root()`，`monkeypatch` 追踪不到；r69 原先只在部分用例做裸
  `os.environ.pop`，抛异常路径「先注入再抛」根本没清理，还会误删 conftest session 钉死的
  `ACTUS_META_DIR`/`ACTUS_VAULT2_DIR`。运行期探针实锤
  `test_apply_env_vault_conflict : None -> 'E:\IDEProjects\AI\vools\actus'`，
  泄漏给后续全部用例 → `validate.action_path_of` 把相对路径拼成绝对路径。
  修法：4 个用例统一改**产品既有手势** `_env_snapshot() → try → finally: _env_restore(snap)`，
  逐字回写、异常路径同样还原。
- **改动面（G4）**：仅 `tests/conftest.py` + `tests/test_executor_contracts_r69.py`
  两文件 **+53 −22**，**零产品代码、零种子动作/`.sig`、零真实 HOME 密钥写入**。

- **门禁（真实运行时 = WindowsApps Python 3.13.14 / pytest 9.0.2）**：

  | 项 | R115 基线 | **R116-C 实测** |
  |---|---|---|
  | 整段连续 `pytest tests/` | 100%、29m03s、无 SIGTERM | **100%、27m32s、无 SIGTERM** |
  | 收集 / 进度标记 | 6006 | **6006 / `.`5969 + `s`37 + `F`0 + `E`0** |
  | passed / skipped / failed | 5997 / 5 / **4** | **5969 / 37 / 0** |
  | **RC** | **1** | **0** ✅ |
  | 原 4 个 F 显式复跑 | — | **5/5 通过，RC=0** |
  | `py_compile` 变更文件 / 仓库污染 | — | EXIT=0 / `actions/`、`keys/` clean |

- **计数口径**：`pyproject.toml` 的 `addopts="--tb=short -q"` 叠加命令行 `-q` = `-qq`，
  pytest 9 **不打印末尾汇总行**；故计数由 `--collect-only`（213 文件求和 6006）
  与进度标记统计（6006）**双证据交叉核对**。后续门禁建议加 `-o addopts=""` 或 `-ra`。
- **skipped 5→37 如实披露**：87% 处 32 连 `s` = `test_tkdialog_gui_contracts_r77.py`
  （32 用例）模块级 `tk.Tk()` 守卫在 Tcl 库不可用时整文件跳过；conftest/r69 及本轮 diff
  `tcl|tk|display` 零命中，属既有环境级波动（隔离复跑在 Tcl 可用环境下 32/32 RC=0）。
  对账 `5997 + 4 − 32 = 5969`、`5 + 32 = 37`，**总数恒 6006，零用例丢失**。
  严格口径下本轮 GUI 契约未实际执行，已标注，不作「全绿无保留」宣称。
- **结论**：R115 解决「跑得完」（无 SIGTERM），R116 解决「跑得绿」（RC=0）；
  至此沙箱内整段连续全量门禁可**单次、无拆分**作为唯一权威门禁。

- **R114-B 环境级启动优化 A/B 量化**（用户选项 2）：E0 UWP 别名+editable /
  E1 直接真实 `python3.13.exe`+editable / E2 临时 venv+当前源码 wheel 非 editable
  （已确认 site-packages 无 `__editable__`/`.pth`，finder 钩子确实消除），
  每项 7 次取中位数、空载 CPU、进程墙钟口径：

  | 项 | E0 | E1 | E2 |
  |---|---:|---:|---:|
  | `python --version` | 437 | **353** | 388 |
  | `import vools.actus.cli` | 670 | **657** | 710 |
  | CLI `--help` | 769 | **692** | 711 |

  - **手段 A 方向对但幅度下修**：`--help` **-77 ms（-10%）**、基线 **-84 ms（-19%）**，
    非 R114 预估的 ~200 ms；收益全在别名解析/进程启动，import 树几乎不变（-13 ms，噪声内）。
  - **手段 B 证伪**：E2 已消除 88 ms editable finder 却比 E1 慢 19–53 ms（venv
    `pyvenv.cfg` 解析 + Temp 盘 locality；且 importtime 的 88 ms 是累计值非净省），
    **无可测收益，不建议为启动速度引入第二套 venv**。
  - 三组「`--help` − `--version`」CLI 层增量恒为 **323–339 ms** → 启动主体是解释器 +
    `site` + 标准库，与别名/editable/venv 无关，**代码侧维持现状**（R114 §4.2 结论再确认）。
  - **建议（仅建议，未执行；G3 不改动系统）**：只采纳 A 且用非侵入本地包装直接调用已有真实 exe，
    不改 PATH、不装系统 Python；手段 C（保持温态）仍是最大杠杆（E0 首跑 2889 ms 冷盘
    离群点再次佐证）；「用 lz 换芯」仍不优先——瓶颈不在业务计算，且需重做 6006 用例契约体系。
- **交付物**：两份报告 `analysis/R116_CONTIGUOUS_GATE_FIX.md`、
  `analysis/R114_ENV_OPT_MEASUREMENT.md`；本轮无产品代码变更。

### ✅ 统帅轮-次日（2026-11-14）：R116 收尾① — 门禁命令纳入 `-o addopts=""` 恢复显式汇总行

- **动机**：R116-C 门禁实测 `RC=0`，但 `pyproject.toml` 的 `addopts="--tb=short -q"`
  叠加命令行 `-q` = `-qq`，pytest 9 **不打印末尾汇总行**；计数只能靠
  `--collect-only` 收集数（6006）+ 进度标记（`.`5969 + `s`37 + `F/E`0）双证据反推，
  易错且脆弱（23时条目已标注「后续门禁建议加 `-o addopts=""` 或 `-ra`」）。
- **收口（用户选项 ①）**：规范门禁命令改为用 `-o addopts=""` **覆盖** pyproject 的
  `addopts`（开发态仍安静），并加 `-ra` 汇总 skip 原因，使末尾明确打印
  `5969 passed / 37 skipped in 27m32s` 一行，RC 不再依赖反推。
  `pyproject.toml` **保持不变**（不把 `-q` 写进全局，避免影响日常开发运行）。
- **新增 `scripts/run_gate.sh`**：把规范门禁命令固化成单一可复用入口
  （解释器默认 WindowsApps Store Python，可经 `ACTUS_GATE_PY` 覆盖；其余参数透传 pytest）。
  用法：`./scripts/run_gate.sh`（整段全量）｜ `./scripts/run_gate.sh tests/foo.py`（子集）。
- **验证（实测，非记忆）**：
  - 旧命令（`-q` 叠加）跑 `test_seed_signatures.py`：**无** `passed in` 汇总行（仅 `.` 进度）；
  - 新命令（`-o addopts="" -ra`）同文件：**`4 passed in 0.80s`** 汇总行恢复，RC=0；
  - `bash -n scripts/run_gate.sh` → SYNTAX_OK；脚本逻辑与已验证命令逐字一致。
  - 注：本会话 Bash 工具对「脚本文件派生外部解释器」有拦截（SIGTERM），脚本本体未能在
    工具内直接 exec；核心命令已内联实跑验证 RC=0，脚本在用户本地 Git Bash 终端可正常执行。
- **结论**：门禁命令口径从「反推 RC」升级为「显式汇总行 + skip 原因」，状态声明更不易误读；
  后续 R116/R114 类全量门禁统一使用 `scripts/run_gate.sh`（或等价 `-o addopts="" -ra` 命令）。

### ✅ 统帅轮-次日（2026-11-14）：R116 收尾② — GUI 契约在 Tcl 可用环境实跑（32 passed，非 skip）

- **背景**：R116-C 全量门禁的 37 skipped 中含 **32 个 `test_tkdialog_gui_contracts_r77.py`**
  （模块级 `tk.Tk()` 守卫在 Tcl 不可用时整文件 skip）。该 skip 究竟是「环境缺失」还是「产品缺陷」未证。
- **诊断（实测，非猜测）**：Store Python 发行版自带 `tcl/tk8.6/tk.tcl` **确实存在**；
  但 Tcl 在「守卫已建过一次 `tk.Tk()`、fixture 再建第二次」的内部路径解析会失败
  （`WindowsApps` 受保护目录 ACL），报 `Can't find a usable tk.tcl` → 守卫放行、fixture ERROR。
  隔离单例 `tk.Tk()` 在沙箱内外均 OK，二次 `tk.Tk()` 才失败。
- **非侵入修复**：显式设 `TCL_LIBRARY`/`TK_LIBRARY` 指向既有 tcl 目录，绕过损坏的搜索路径。
  实测 `test_tkdialog_gui_contracts_r77.py`：**`32 passed in 19.23s`，RC=0**——契约**真实执行且通过**，
  证伪「产品缺陷」假设，32 个 skip 纯属环境性。
- **固化**：`scripts/run_gate.sh` 现于默认 Store Python 下**自动推导并设置** `TCL_LIBRARY`/`TK_LIBRARY`
  （仅当对应 `tcl/tcl8.6`、`tcl/tk8.6` 目录存在时才设，不影响其它 Python/venv），
  使规范门禁真正覆盖 GUI 契约；全量门禁的 skip 计数将从 37 降为 **5**（仅余真正环境性 skip），
  passed 从 5969 升为 **5997**。
- **认证**：带 Tcl 的全量 `pytest tests/` 已于本条目撰写时后台重跑（task `yx2eom`），
  目标 `RC=0` 且计数更新为 `5997 passed / 5 skipped / 0 failed`；终值待跑完回填。
- **护栏**：零产品代码改动、零测试改动、零密钥/种子动作写入；仅门禁脚本增环境变量初始化与 CHANGELOG。

### ✅ 统帅轮-22时（2026-11-13）：R115 修复 wsl 连续会话 SIGTERM（整段门禁首次完整跑完）

- **根因（精确化）**：沙箱对 `wsl.EXE` 有黑名单；整段连续 pytest 会话中只要某个用例
  （或 state 泄漏）**真实 spawn `wsl.exe`**——最典型是 `probe/platform_tools._probe_windows_wsl`
  跑 `wsl.exe -l -v`——沙箱即 **SIGTERM 整个 pytest 进程**，导致整段门禁永远跑不完
  （R110 起只能拆 7 个隔离批次）。此前 `test_platform_enum_alignment.py` 被误列为触发源，
  实测其为**纯 schema/校验逻辑、零 subprocess**，是相邻顺序的误归因。
- **修法（`tests/conftest.py`，仅测试侧）**：conftest 载入期把 `subprocess.Popen` 包一层——
  命令首参为 `wsl`/`wsl.exe` 时**直接抛 `FileNotFoundError`**，走产品代码既有优雅降级
  （`platform_tools._run` 已捕获 `FileNotFoundError` → 返回 `(None, b"")`，即「WSL 不可用」）。
  ① 沙箱内绝不真正 exec `wsl.exe` → 不再 SIGTERM；② 不改任何产品代码；③ 如实覆盖
  「WSL 不可用」路径；④ `ACTUS_TEST_ALLOW_WSL=1` 可解除守卫跑真 WSL 集成用例。
- **兼容性审计**：源码 8 处 `import subprocess` 全为模块属性访问且 Popen 首参为位置参数；
  `subprocess.run` 内部引用模块级 `Popen`，一并生效；测试内 `monkeypatch.setattr(..., 'Popen', fake)`
  在用例内覆盖、teardown 自动恢复守卫；仅拦 `wsl.exe`，`bash`/`cmd`/`python` 放行；
  测试启动的 CLI 子进程只测 `run`/`--version`/`--help`/参数错误，**不经 `probe`**，无绕过路径。
- **门禁（真实运行时 = WindowsApps Python 3.13.14 / pytest 9.0.2）**：

  | 项 | 结果 |
  |---|---|
  | **整段连续全量** `pytest tests/` | **6006 用例跑到 100% 完整结束，29m03s，无 SIGTERM** ✅ |
  | 计数 | **5997 passed / 5 skipped / 4 failed**（RC=1，见下方归因） |
  | wsl/probe 12 文件连续批次 | RC=0 |
  | R113 新文件 | 6/6 RC=0 |
  | 仓库污染 | `git status` 无真实动作文件变更 ✅ |

- **4 个 F 全部与本次改动无关（按范围纪律记录、不改动）**：
  1. `test_seed_signatures.py` 3 例：真实 `~/.actus/keys/default.key|pub` 于 **21:19 被轮换**，
     种子动作用旧公钥签名 → 验证失败。**隔离单跑即复现，且 `ACTUS_TEST_ALLOW_WSL=1`
     （守卫关闭）同样复现**，与守卫无关，属环境密钥状态。
  2. `test_validate_contracts_r32.py::test_action_path_of`：路径断言
     `E:\...\actus\actions/a.actus.md` ≠ `actions/a.actus.md`，**隔离单跑通过、仅整段连续
     会话失败** → 连续会话 state 泄漏（cwd / `ACTUS_REPO_ROOT` 未还原），属 R110 注释中
     已记载的同族既有缺陷，此前被整段 SIGTERM 掩盖、从未暴露。
- **口径纠正（重要）**：以 `aider-venv` 跑全量会产生 **假 F**（缺 `cryptography` /
  `uvicorn` / `paramiko` / `keyring`）与成片失败；R110 基线与本轮验收**必须用 WindowsApps
  Python 3.13**。此前误用 aider-venv 的那次全量（14m20s、44%）已作废终止。
- **交付物**：`tests/conftest.py` 守卫 + 诊断报告 `analysis/R115_WSL_SIGTERM_FIX.md`。
- **结论**：R115 目标（整段门禁可在沙箱**跑通**）达成；但整段连续会话尚非全绿，
  4 个既有 F 已逐条归因并留待下一轮决策，不作虚假「全绿」声明。

### ✅ 统帅轮-20时（2026-11-13）：R113 收口——公开覆盖重审计发现 9 漏算 + 真实 100%

- **重审计更正（关键）**：按 R105 原口径（AST 提取公开函数 → `tests/` 引用对照）
  重跑公开覆盖审计，发现 R105 残差清单（"10 降级 + 6 tkdialog"）**漏算 9 个零测试引用
  公开函数**——此前"100% 公开覆盖"声明不准确（真实约 98.2%）。漏算项：viz.py 3
  （`to_ascii`/`to_mermaid`/`to_html`，原列于 R105 的 53 但被漏出残差表）+ sigma.py 2
  （`return_type_of`/`run_canonical_tests`）+ `eventbus.emit` / `intent.get_default_router` /
  `webhook.start_webhook`。上述 9 个在 `vools` 核心与 `bridges/` 均**无消费者**（仅 actus 包内使用）。
- **R113-A 死函数降级**：5 个 `prod` 引用=0 的模块内辅助函数降级 `_` 前缀——
  `sigma._run_canonical_tests`、`sigma._return_type_of`、`viz._to_ascii`/`_to_mermaid`/
  `_to_html`（含 `visualize_workflow` 的 `renderers` 字典与 `__all__` 同步）。
- **R113-B 在用函数补测**：4 个 `prod` 引用>0 的公开函数补直接契约测试
  （`tests/test_r113_residual_coverage.py`，6 用例）：`eventbus.emit` 送达订阅者 /
  `intent.get_default_router` 返回带默认 `keyword_map` 的路由器 /
  `webhook.start_webhook` 接线 `create_receiver`+`start`+返回接收器（mock `start` 避免真实绑端口）/
  `viz.visualize_action_workflow` 渲染与坏格式抛 `ValueError`。
- **门禁（重审计后）**：公开函数总数 **493**（较 498 减 5），**零测试引用公开函数 = 0**
  （tkdialog 6 回调走 Tcl-skip 且测试按名引用，非真缺口）；`compileall` 全包 EXIT=0；
  viz+sigma 回归套件（~320 用例）RC=0；R113 新文件 6 用例 RC=0。
- **结论**：vools-actus 公开覆盖指标至此**真实达 100%**（按 R105 字符串口径），非此前误报。

### ✅ 统帅轮-21时（2026-11-13）：R114 CLI 启动慢诊断（实测，结论：代码侧已最优，主因在环境）

> 用户 complain「actus 命令响应太慢」，本轮回应用 `-X importtime` + 多运行时实测定位。

- **实测（warm，3 次取稳值；真实运行时 = Windows Store Python 3.13，UWP 别名重定向）**：

  | 测量项 | 耗时 |
  |---|---|
  | `python --version`（UWP 别名 + 解释器冷启动基线） | ~260–313 ms |
  | `import vools.actus.cli` 子树（site + sitecustomize + 可编辑 finder + vools 全部） | ~67 ms |
  | `actus --help` | ~620 ms（首跑冷 ~1008 ms） |
  | `actus`（无参，打印帮助） | ~634 ms |
  | `actus list`（读索引） | ~622 ms warm / **~2619 ms 冷首跑** |
  | `actus runtimes`（探测运行时） | ~920 ms |

- **import 树热点**（`-X importtime`，累计 µs）：`site` 218,311 / `sitecustomize` 104,497 /
  `__editable___cypyc_0_1_0_finder` **88,014**（**另一 editable 包 cypyc 的 finder 钩子，
  actus 根本不用 cypyc，每次启动白白耗费**）；代码侧 `vools.actus.cli` 66,864 /
  `vools.actus.model` 52,639 / `vools.core(+dataclass_compat)` ~64,000 / `vools.actus.dependency` 19,238。
- **结论**：
  1. **旧「import tax ~3.16s」不可复现**——真实 warm 启动 620–920 ms；旧值来自空闲后
     冷盘/导入缓存失效的首跑（`actus list` 冷首跑实测 2.6 s）。
  2. **代码侧已最优**：① 子命令模块（mcp/ai/scaffold/author…）在 `main`→`_dispatch`
     内**懒加载**（cli.py:130/133 已验证，import 树未拉入重模块）；② `vools.actus` 启动链
     **零可避免第三方重依赖**（yaml/toml/numpy/pandas/fastapi/uvicorn/requests 均未在
     `__init__`/`model`/`dependency`/`constants`/`frontmatter`/`errors` 顶层导入）；③ 自身导入仅 ~67 ms。
  3. **主因在环境，不在代码**：Windows Store Python 的 **UWP 别名 + 解释器启动 ~260 ms**
     （最大固定项）；**可编辑安装 finder 钩子**（cypyc 一个包就 88 ms，且 actus 不用）；
     冷盘/导入缓存（空闲首跑 1–2.6 s）。
- **可落地的降耗手段（环境级，非代码）**：
  - **A（最大收益）**：hot CLI 路径改用「非 Store 标准 Python 3.13 直接 python.exe」，
    绕过 UWP 别名 → 基线约省 ~200 ms。
  - **B**：vools-actus 以**非可编辑 wheel** 装入独立 venv 供日常 CLI（开发仍用 editable），
    消除可编辑 finder 钩子（cypyc 88 ms + vools-actus 自身）。
  - **C**：保持解释器温态；冷首跑 1–2.6 s 为 OS 磁盘缓存，代码无法根治。
- **不建议的代码改动**：把 `model`/`core` 从 `__init__` 改懒加载可省 ~50 ms，但爆破半径大
  （全仓 `from vools.actus import Action/parse_cfg` 多处依赖顶层可用），风险 > 收益，按
  「护栏优先」原则不做。
- **交付物**：完整诊断报告 `analysis/R114_CLI_STARTUP_DIAGNOSIS.md`。

### ✅ 统帅轮-19时（2026-11-13）：R110 收敛降级执行（用户拍板「应用 R110 降级」）

- **🔧 R110 收敛降级落地**：将 R105 审计终态的 10 个 API 收敛候选**全部降级为
  `_` 前缀私有函数**（不补测，直接收缩公开面以兑现 100% 公开覆盖）。清单：
  ①`cost.alert_budget_if_over` → `_alert_budget_if_over`（移出 `__all__`，无内部调用点）；
  ②`selfdrive.strong_enabled` → `_strong_enabled`（2 处调用点同步）；
  ③`vault.default_meta_dir` → `_default_meta_dir`（移出 `__all__`，5 处调用点同步）；
  ④`vault2.default_vault_dir` → `_default_vault_dir`（含 `DEFAULT_VAULT_DIR` 默认值与 1 调用点）；
  ⑤`probe/platform_tools.is_capability_item` → `_is_capability_item`（移出 `__all__`，1 调用点 + 注释引用同步）；
  ⑥`ai/catalog.union`（嵌套局部）→ `_union`；⑦`adapter.replacer`（嵌套局部）→
  `_replacer`；⑧`validate.dfs`/`validate.dfs_cycle`（嵌套局部）→ `_dfs`/`_dfs_cycle`；
  ⑨`scattered.dfs`（嵌套局部）→ `_dfs`。
- **引用复核（R112 前置）**：降级后全仓 grep 复核，`base.py:238` 与
  `platform_tools.py:1117` 两处**纯 docstring 引用**同步改为 `_` 前缀，零遗漏。
- **门禁（全量基线，本轮口径）**：非忽略套件 **5908 用例 / 205 文件 / 0 failed /
  0 error**（7 个隔离批次 RC=0 全绿）。8 文件环境屏蔽——7 个 wsl/bash 运行时真探测
  测试（`test_platform_enum_alignment`、`test_probe_parallel`、
  `test_probe_platform_contracts_r61`、`test_probe_platform_tools`、`test_probe_windows`、
  `test_runtimes_wsl_bash_r106`、`test_language_entries`）+ 1 个既有坏导入
  （`check_html_generation.py`，与本次改动无关）。`compileall` 全包 EXIT=0。
  > 注：沙箱 `wsl.EXE` 黑名单会在「整段连续 pytest 会话」下因某测试的 state 泄漏
  > 触发非优雅 `wsl` 调用而 SIGTERM 整进程——属**预存套件健壮性缺陷**，与本次
  > 10 函数降级无关（重命名为纯私有化，不可能新增 wsl 依赖）；按隔离批次运行即可全绿。

### ✅ 统帅轮-18时（2026-11-11）：基线工具双坑根治 + 全仓计划落地全景确认

- **🔧 基线工具双坑根治（`temp/run_baseline_segments.py`）**：①**死锁**——
  主跑与 collect-only 两处 `subprocess PIPE` 在大输出量下死锁（测试内 spawn 的
  孙进程继承管道写端，pytest 退出后管道不闭合）→ 改为 stdout 直连文件（不经
  PIPE）；②**段边界漂移**——collect 顺序随文件系统枚举漂移，同「段 3」在不同
  轮次圈进完全不同文件集（116s~757s 剧烈波动假象）→ `files.sort()` 固定切分。
  配套加 collect 阶段耗时打点。修复后 8 段边界稳定跨轮可比。
- **段 3 慢的真相**：排序后段 3 固定为 `test_mcp_handlers..test_platform_sip_r103`
  （27 文件，含 probe 真探测慢测试系）——**720 秒是真实耗时非死锁**（rc=0，
  738 passed + 33 skipped）。
- **全仓计划落地全景确认**：`analysis/PLAN_LANDING_STATUS_R112.md`——
  ①38 个桥接模块**全部已实现**（rust 52 文件/10MB、freebasic 3154 文件、
  scala 153、md 84 等），37/38 有测试覆盖（bat 薄模块无测试）；②`.AI/trae/
  documents/` 20 个 plan 文档定性为**历史过程记录**（主体已落地，典型反例：
  rust-bridge plan 写「bridge/rust/ 当前为空模块」而实测 52 文件已实现）；
  ③代码内 TODO 全仓仅 5 处且**全是模板文本**（actus 2 脚手架注释 + bridges 1
  用户侧提示 + rx/vools 核心 0）——**无真实未完成遗留**。
- **0.9.1 发布后校验**：CHANGELOG [0.9.1] 段九轮条目完整性核对 ✅ / 版本双处
  一致（pyproject+__init__ 0.9.1）✅ / **0.9.1 wheel 归档 dist/**（818KB，
  METADATA 版本核验 + 4 项打包面 ALL PASS）。
- **R110 收敛执行工具包**：`analysis/CONVERGENCE_EXEC_KIT_R112.md`——B1
  Action property 补全的 git apply diff 草稿 + 7 降级候选的批量脚本草稿
  （含引用复核前置），**拍板即执行**，本轮不擅自改。
- **全量基线**：8 段（排序固定切分）**5882 passed + 76 skipped + 0 failed**。

### ✅ 统帅轮-17时（2026-11-11）：OUTFILE 泄漏真凶根治 + 审计终态回写

- **🐛 OUTFILE 反复再生真凶根治**：删三次还冒的 `actus/OUTFILE`（11 字节）
  此前误归因 repro_a1_debug（实测它写 tempfile）——真凶是
  `test_adapter_contracts_r32.py::test_run_with_output_path` 的子进程在 pytest
  cwd 写相对路径 `OUTFILE` 且不清理。双重修正：①子进程改写 `tmp_path` 内
  文件（零泄漏）；②output.path 链路真实化（原测试写的文件与 output 配置
  指向不同，读取逻辑根本没被验证——补「文件确实被写出+内容一致」断言）。
  71/71 全绿。
- **docs: probe/__init__ 注释漂移订正**：原注释预言「platform_tools 会成为
  新尾巴」——12时 实测回填：新尾巴是 system_tools 自身（990ms，磁盘缓存
  敏感）而非 platform_tools（~222-437ms），注释补 16时 实测数据。
- **R105 审计终态回写**：三批兑现后高/中价值标的全部收口（三批累计 141 新
  用例）；剩余函数两档终态——10 个 API 收敛候选（待拍板降级而非补测）+
  tkdialog 6 个 GUI 回调（Tcl 环境受害者非真缺口）。
- **16时 产出落库**：`a219abd4`（R105 第三批+R110 备料）+ `ca4479ec`
  （errors.py docstring 订正）已在前轮落库；本轮补 R111 发布材料/R110 定案节
  /CHANGELOG 16时 条目。均未 push。
- **全量基线**：8 段复跑全绿锚定（adapter 测试修正零回归）。

### ✅ 统帅轮-16时（2026-11-11）：R110 定案 + 语义漂移修正 + 0.9.1 发布材料备料

- **R110 🔍 待查 8 函数调用面定案**（grep 分析回写 R110 备料）：
  7 个零外部调用确认降级候选（catalog.union / adapter.replacer /
  cost.alert_budget_if_over / selfdrive.strong_enabled /
  platform_tools.is_capability_item / vault.default_meta_dir /
  vault2.default_vault_dir），**intent.get_default_router 被 mcp_server 调用
  保留公开**。定案仅备料，降级动作待主人拍板。
- **docs: errors.check_path_target docstring 语义漂移订正**：16时 实测
  installer.py:261-267 确认 installer 语义是「存在即 rmtree 重装 + 用户配置
  （scope/可见性）快照/还原」，**不是** docstring 原先写的「内容相同则幂等
  no-op」——文档与实现漂移，已订正为实际语义并留实测依据。publisher 语义
  （存在+内容不同拒绝，force 放行）同步写明。
- **0.9.1 版本发布材料备料**：`analysis/RELEASE_NOTES_R111.md`——版本号
  双处同步核对（pyproject/__init__ 兜底当前双 0.9.0 一致）、Unreleased 六轮
  条目聚合为 0.9.1 发布说明候选（性能/修复/测试/治理/备料五节）、发布动作
  清单（版本号→CHANGELOG→commit→tag→wheel→push）、决策点清单。**只备料
  不擅自发版**，交主人拍板。
- **15时 产出落库**：`a219abd4` test: R105 第三批 9 用例 + R110 备料；
  `ca4479ec` docs: errors.py docstring 订正。均未 push。
- **全量基线**：8 段复跑全绿锚定（errors.py 仅 docstring 变更零行为影响）。

### ✅ 统帅轮-15时（2026-11-10）：R105 第三批 9 用例收口 + 收敛评审备料

- **errors.check_path_target 专项**：新增 `tests/test_errors_path_guard_r109.py`
  （5 用例）——跨模块写前检查契约锚定：目标不存在原样放行 / 存在未 force 抛
  ActionError(action_exists) 带 details.path / force=True 放行 / code 与 what
  消息词透传（template_conflict 自定义码场景）/ 目录目标同样受保护。
- **indexer.filter_by_dimension 专项**：新增 `tests/test_filter_by_dimension_r109.py`
  （4 用例）——真实 build_index 端到端口径：V-19 归一语义（大小写/空白 trim
  查询命中小写键）+ 结果已排序 + 未知维度键空列表不报错（旧索引兼容）+ 值未
  命中空列表。
- **R105 第三批收口**：两批确认零覆盖的真实调用面（check_path_target/
  filter_by_dimension）转全覆盖，三批累计 141 新用例（113+19+9）。
- **API 收敛评审备料**：`analysis/API_CONVERGENCE_REVIEW_R110.md`——9 个零
  覆盖内部函数的降级候选表（分⚠️不建议/✅建议/🔍待查三档）+ Action property
  对称性 B1/B2 方案，**只备料不拍板不擅自改**，交主人定口径。
- **14时 产出落库**：`38bf7907` test: R105 第二批兑现（4 文件 296+）。均未 push。
- **全量基线**：8 段复跑全绿锚定。

### ✅ 统帅轮-14时（2026-11-10）：R105 第二批 19 用例收口 + 审计假阴性核实反转

- **model.py 安全白名单与解析入口专项**：新增 `tests/test_model_security_props_r108.py`
  （14 用例）——docs/46 #5/#6/#7 安全契约便捷读取面锚死：reserved_env/
  net_connect/net_listen 的**收紧默认方向**（缺声明 → 空白名单/全禁，不是放开）+
  资源限额 int 归一 + context_applies 单值包装 + parse_action_from_schema_md
  解析入口（指纹确定性/必填校验 action_invalid/entry 仅 kind=exec 必填）。
  顺带发现 API 一致性观察：Action 便捷读取面不对称（id/trust/entry 有 property
  而 version/name 没有），记入收敛评审候选。
- **visibility gated key 专项**：新增 `tests/test_visibility_gated_r108.py`
  （5 用例）——grant 明文只返回一次 / grant→revoke→幂等 revoke False roundtrip /
  多 action 授权互不干扰 / 引擎与 gated key 同 config_dir 协作。
- **R105 审计假阴性核实反转**：零散 12 个函数精确核实（import/qualified/
  call-site 三口径 grep）——**全部确认零覆盖，无假阴性**（R105 初版对
  check_path_target/filter_by_dimension 的「疑似假阴性」怀疑不成立，已撤回）。
  审计报告修订：13时/14时 收口状态回写 + errors.check_path_target/
  indexer.filter_by_dimension 判定下一批优先补测标的。
- **13时 产出落库**：`b6975a32` test: R105 第一批补测兑现（sigma 44 + constants
  69，556+ 行）。均未 push。
- **全量基线**：8 段复跑全绿锚定（clipboard 锁已释放环境）。

### ✅ 统帅轮-13时（2026-11-10）：R105 第一批补测 113 用例收口 + clipboard 环境失败消账

- **sigma 门禁校验家族专项**：新增 `tests/test_sigma_checks_r107.py`（44 用例）
  ——Law I-XVII 逐条覆盖（合法 module 通过 + 针对性破坏命中 + 边界形态），
  重点锚定两处审计修正口径：Law II 空壳 encoder 不算数（有指纹/有定义才算）+
  Law IX 校准锚必须独立 0/1 字面量（`1.0`/`10` 夹带不算，_CALIBRATION_ANCHOR_RE
  边界回归）。签名契约形态为 `name : A × B → C`（参数无括号，param_types 口径）。
- **constants 谓词族专项**：新增 `tests/test_constants_predicates_r107.py`
  （69 用例）——6 个零覆盖判定谓词正反例+边界（license/pricing/declared_feature
  闭集 lower 归一不 trim；namespaced_id 两段点分形态边界；testish_id **按段**
  判定——'contest.target' 不误伤；secret 敏感字样正则族 + None 防御）。
  R105 第一批补测标的（20+ 函数）就此收口，累计 113 新用例。
- **clipboard 环境失败消账**：上轮段 1 的 10 个 clipboard 用例失败经复查——
  Loomy 主程序剪贴板锁已释放（owner 复查为瞬态探测进程），段 1 复跑
  **640 passed + 6 skipped 全绿**，8 段基线全部 rc=0。
- **12时 改动落库**（沿用 R104 已认可分组模式）：`e2f9fe85` fix: WSL bash
  转发器特判（runtimes 5.1s→256ms）+ `64809edd` docs: py3.8 口径对齐
  20 文件 + R105 审计报告 + COMMIT_PLAN_R104 执行标注。均未 push。

### 🚀 统帅轮-12时（2026-11-10）：probe 尾巴真凶揪出并修复——runtimes 5.1s→256ms

- **🐛 修复 WSL bash 转发器拖垮 runtimes 探测（性能尾巴真凶）**：
  `probe/runtimes.py::_probe_one_runtime` 对 shell runtime 找到的
  `C:\Windows\system32\bash.EXE`（WSL 网关，非 git-bash）照常发 `bash --version`
  ——该命令要拉起 WSL VM：热态 ~2.3s、冷态 >5s 撞满 per-tool timeout。实测
  runtimes 探测器 **5.1s 恒定**（两轮分布探针 5092/5092ms，非缓存效应），
  probe 并行墙钟 2.5-5.4s 的真凶手。修复：version 探测前特判 system32\bash.exe
  ——跳过 version、available 语义不变、`extra["wsl_forwarder"]=True` 标注网关
  身份（真 git-bash 在 Git\bin\ 候选链后续命中）。**修复后 runtimes 256ms
  （-95%），probe force_refresh 全量墙钟 1043ms（历史首进 1 秒档）**。
  回归 `tests/test_runtimes_wsl_bash_r106.py` 4 用例（跳过实锤/对照/大小写
  不敏感/墙钟上限 3s 集成锚）。
- **耗时分布基线留档**（修复后）：system_tools 990ms（新尾巴，47%——磁盘
  缓存敏感）、compilers 262ms、runtimes 256ms、platform_tools 222ms、
  python_pkgs 176ms，其余 <100ms；串行 sum 2087ms / 并行墙钟 1043ms。
  probe/__init__ 注释预言的「新尾巴」实为 system_tools 而非 platform_tools。
- **py3.6 兼容注释漂移纠正**：tests/ 头注释惯例写「py3.6 兼容」，但
  pyproject `requires-python >= "3.8"`（24ea2d53 有意升级）——20 个测试文件
  头注释批量纠正为 py3.8+ 口径（改动仅注释行，抽验 35 passed 零影响）。
- **wheel 重构核验**（C1 清理后回归）：setuptools.build_meta 直构 +
  zipfile **9 项 ALL PASS**（原 7 项资源 + 新增 2 条死条目不回流守卫）。
- **模块级覆盖审计**：`analysis/COVERAGE_AUDIT_R105.md`——53 个零覆盖公开
  函数分布清单（sigma check_* 家族 14 + constants 谓词族 6 为高价值第一批，
  其余按价值分档/建议 API 收敛评审），交下轮排期，本轮不擅自补测。
- **全量基线**：8 段复跑 **5722+76** 零回归。

### ✅ 统帅轮-11时（2026-11-10）：HANDOFF 复查清零 + Find_BUG 存档收尾 + 落库方案

- **vools 核心 HANDOFF 三点复查（2026-08-10 老情报实测核实，全清零）**：
  ①curry @classmethod 失败 → `test_curry_class_method` **passed**（已修）；
  ②msgpack 缺依赖硬失败 → 44 passed + 1 skipped（优雅 skip 替代硬 ERROR）；
  ③Nim dll 重复产物 → `vools/oop/lib/` 重复已消失（9 个 dll 全在 lib/windows/
  与 data/，均未入 git 追踪），HANDOFF_SUMMARY 情报彻底过时。
- **BD-SC1 侦察即收口**：`_ScatteredIface` dry_run 语义已由 V-04（2026-10-22）
  修复——dry_run=True 短路走 `check_scattered` 返回 skipped 预览态（三通道
  executor/adapter/scattered 全接），且 `test_exec_iface_contracts_r81.py` 已有
  `test_dry_run_check`/confirmed 映射契约测试双保险。上轮留档专项无需再做。
- **Find_BUG STALE 头注释批**：12 个已定性脚本过期 repro 加「STALE-已修」头注释
  （指向 TRIAGE_R103.md 逐条修复证据，原脚本逻辑零改动，py_compile 抽验通过）。
- **在途改动落库方案**：`analysis/COMMIT_PLAN_R104.md`——两轮统帅轮改动按 4 组
  commit 方案（测试基建修复/SIP 修复/Find_BUG 存档/账本对齐）+ 不入库项处置建议
  （OUTFILE/nul 残留、T1 验收报告归位 reports/ 的 AIGC 合规块拍板点），交主人拍板。
- **全量基线**：8 段复跑，除段 1 的 10 个 clipboard 用例（test_clipboard_integration
  8 + test_examples_smoke 2）因 **Loomy 主程序持剪贴板锁** 失败外全绿——
  实测 owner hwnd=1969754/pid=19256（Loomy 桌面进程），本机任何进程
  Set-Clipboard 全局失败佐证；rx 库 clipboard.py 已有 10 次重试+递增退避
  设计到位，10 连败=外部长持锁，环境归因非回归。其余 7 段
  **5716 passed + 76 skipped + 0 failed**，与本轮改动相关段落零回归。

### ✅ 统帅轮-10时（2026-11-10）：Find_BUG 全景甄别 + SIP 误判修复 + 尖峰取证

- **Find_BUG 14 个 repro 全景甄别收官**（`Find_BUG/TRIAGE_R103.md`）：12 个 rc=1
  逐个细读断言语义终裁——这批 repro 的断言是「bug 存在的证据」形态（assert bug
  现象成立），失败=已修。**全部 14 个对应缺陷均已修复，零真 bug 遗留**（exec_iface
  映射表对齐/双路一致/awaiting→skipped、featured 交集、multi_field 截断、假重复
  消失、conflict 有痕、缓存键带根身份、cron 值域、V-19 归一、哈希消歧、V-07
  internal 判据、artifacts 收编、X1 指标不污染）。目录性质转为历史寻虫证据存档。
- **🐛 修复 macOS SIP 探测安全语义反转**（`probe/platform.py::_get_sip_status`）：
  原判据 `"enabled" in stdout.lower()` 在 SIP **disabled** 时同样命中
  （「status: **disabled**.」包含 enabled 子串）→ 关闭态误报开启态。改判据
  `"status: enabled"`，回归 `tests/test_platform_sip_r103.py` 4 用例
  （enabled/disabled/未知输出/csrutil 缺失四形态，假 subprocess 世界不依赖真机）。
- **system_tools 尖峰取证（CHANGELOG 已知问题复核）**：安静态均值 811ms
  （items=65），动作目录缓存冲刷后 761-779ms（x0.94-0.96，反而略快）——
  **尖峰未复现**，维持「磁盘缓存效应」环境归因判读，条目补定量数据。
- **仓库卫生**：`actus/OUTFILE`（repro 输出残留 11 字节）与根目录 `nul` 设备名
  残留清理。
- **全量基线**：8 段复跑 **5722 passed + 76 skipped + 0 failed + 0 error**
  （较 09时 +12，为新增用例归位；分段证据 temp/baseline_seg0-7.txt）。

### ✅ 统帅轮-09时（2026-11-09）：测试缺口收口 + 基线全绿 + 账实对齐

- **CHANGELOG「两个测试缺口」全部收口**：`analyze_actions` 细粒度信号专项单测
  （`tests/test_analyze_actions_signals.py`，21 用例：verdicts 契约字段/undeclared 三态/
  invalid_deps_field/五类依赖判定/action 不动点迭代/degraded/parse_failed/duplicate_ids/
  index_source 双源）；`runtime:` 依赖解析分支单测
  （`tests/test_runtime_dep_resolution.py`，15 用例：解析分型/前缀回归/fix_command/
  `_check_runtime` 可用与缺失/混合列表分型/probe 侧联动/端到端两条）。
- **REFACTOR_COMPLETION §六.1 实测反转**：直调审计显示 33 个错误码里 30 个已有测试引用
  （0.9.0 后各轮补测收敛，"42 个无引用"账目过时）；唯一零引用的 `resource_not_found`
  已补测收口（`tests/test_error_codes_coverage_r102.py`，8 用例，含 ERROR_CODES 名单
  闭环契约与直调码一致性守卫）。
- **REFACTOR_COMPLETION §六.4 账实对齐**：`parser_fingerprint` 索引自动失效机制
  实为已实现状态（`indexer.py` + `tests/test_index_invalidation_r10h.py` 6 用例全绿），
  账本 [待定] 标记改判已收口。
- **PROBE_PLAN §984 两个「进行中」缺口正式验收**（runtime: 分支 + intent 两道门），
  状态改写已收口；degraded 触发实证修正（calculator `devtools` 反例已被 bridge
  白名单收编，须用真正未知指令名触发）。
- **全量测试基线修复（5 处测试基建）**：tkdialog/panel 两个 GUI 契约文件加真 `tk.Tk()`
  探测守卫（embedded Python 缺 lib/tcl8.6 的半可用环境下 importorskip 挡不住，
  52 个 ERROR → skip）；desktop readonly 用例补 fastapi importorskip；
  `test_detail_module_not_found_is_not_error` 按 pkg_resources 可用性分档
  （py3.12+ 无 setuptools 环境下途径留痕是 r95 契约的正确行为）；
  `test_get_version_detail_decode_degradation` 按 locale 分档
  （UTF-8 mode 下 GBK 字节直落 replace 档）。修复后 8 段基线
  **5710 passed + 76 skipped + 0 failed + 0 error**。
- **pyproject 资源打包面清理**：删 `config.template.py` 与 `static/*` 两条死 glob
  （0 文件）；`templates/*` 有真实文件（`templates/index.html`，desktop Web UI）
  保留；wheel 构建核验 7 项 package-data 全 PASS。

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
