# 边界语料库（bugfind 产出）

> 由 Round 3 `bugfind` 模式生成。定位：**语料 + 复现器**，不是产品源码，也不进 pytest 收集范围
> （文件名刻意不叫 `test_*.py`；按 bugfind 模式约束「不把新测试 case 合并进正式测试文件，交由后续环节」）。
> 这里每条都给出可复核的复现步骤与证据，供后续 `polish`/`fix_and_merge` 轮直接据此修复。

## 运行

```bash
cd rhop && python tests/boundary/r3_boundary_probes.py
```

- 每条输出 `[CONFIRMED]` / `[NOT-CONFIRMED]` + 证据；退出码 = 确认条数。
- 环境全部建在系统 TEMP，不落产品目录、不改产品源码。
- `issue_scan` 只收 `.mbt`（本仓是 Python）→ 静态轨 0 命中；`ocr_scan` 真跑返回 `ocr_available=false`
  （dry_run 却报 true —— 一处工具口径不一致），按 bugfind 模板显式降级为「自造边界 case 兜底」。

## 语料与判定（2026-10-22 实测）

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| P1 | 并发交错 | 两个**真实进程**并发领取共享库 40 条会重复/漏单/锁崩 | **未成立（安全实锤）** | claimed=40/40，dup=[]，missing=[]，errors=[]。`claim_next` 的 `BEGIN IMMEDIATE` + 状态守卫 UPDATE 有效 |
| P2 | 权限等价性 | `exec.allow=["cli:python"]` 只放行"解释器"，不代表能跑任意代码 | **成立（设计性质，已审计+文档化）** | B 端被指示执行 `open(flag,'w').write(...)` → flag 文件生成（`outcome=completed`）；对照组 `allow=["action:*","handler:*"]` 被拒（`outcome=failed`）。即：放行任何解释器都等于把 B 的代码执行权交给 A。**处置**：BUG-281 已收口——cli 执行前打审计行（task/argv/allow_hit/shell），文档 §10 给出分级建议；该设计性质不会消失，语料仍会判 CONFIRMED（这是对"风险存在"的断言，不是对缺陷的断言） |
| P3 | 时间精度截断 | 心跳只写秒精度，A 读到的 age 含最多 ~1s 截断误差，小阈值下误判死 | **成立（边界缺陷）** | 写入 `.900`、读取 `+5ms`（仍在同一秒）→ 读到 `age=0.905s`、真实 0.005s，`stale_after_sec=0.5` 时判 `stale`；阈值 15s 时 `alive`。默认配置不受影响，但**无任何配置校验**阻止把 `stale_after_sec` 设成 <1s |
| P4 | 状态机发散 | 本地库模式下 A 端 `requeue` 一条 B 已完成的任务，双方是否收敛 | **成立（高危：静默停滞）** | `before=(COMPLETED, COMPLETED)`；A 端 `requeue` 后 `after=(A:PENDING, B:COMPLETED, verA=5, verB=4)`。A 端 `apply_state` 要求版本严格递增 → B 的状态包被永久丢弃，A 永远 `is_all_done()==False` 而 B 已空闲 |
| P5 | 超长输入截断 | `result_max_bytes` 是落库结果的硬上限 | **成立（名实不符）** | 上限 1000B，构造 20KB 的非 stdout/stderr 结果 → 落库 20215B、`truncated=True`。截断只裁 `stdout/stderr` 两个键，其它大字段原样入库 |

## 建议的后续工作（按严重度排序，供下一轮排序）

1. **P4（高）**：本地库模式下给 A 端 `requeue`/`retry_failed` 增加「跨库收敛」语义，
   或显式禁止 A 端重置已被 B 推进过的任务（并在文档 §15 里把现有限制写准 + 补回归用例）。
2. **P2（中，安全）**：~~把「放行解释器＝放行任意代码」写进文档与告警~~ → **已完成（BUG-281 收口）**：
   cli 执行前审计行 + 文档 §10 分级建议；剩余可选增强：`cli.allow_args_only` / 命令模板白名单
   这类更细的约束（本轮未做，属新功能面）。
3. **P3（中）**：配置校验 `stale_after_sec >= interval_sec + 1s`（或心跳写毫秒精度），
   并补一条「小阈值 + 秒末写入」的回归用例锁定该窗口。
4. **P5（低）**：要么把 `result_max_bytes` 变成真正的硬上限（统一按 JSON 长度裁），
   要么改名/改文档为「仅裁 stdout/stderr 的软提示」，避免误导。

## 第二轮语料（并发 / 同步深层语义，2026-10-22）

运行：`cd rhop && python tests/boundary/r10_concurrency_sync.py`（退出码 = 风险成立条数）

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| P6 | 租约生命周期 | 租约续期接口存在且能把租约推到未来（执行时长超过租约会重复执行） | **已闭环（BUG-289）** | 机制演示：无续期时租约过期会被 `clean_stale_locks` 回收重跑（计数器=2，属默认设计行为、可 opt-in）；正向校验：`renew_lock=True`、`expire_time` 被推到 2030。修复=`TaskStore.touch_lock`（基类默认走 `update_fields`，Sqlite 覆盖为版本无关 UPDATE；认 LOCKED/RUNNING + 持有者匹配）+ `TaskQueue.renew_lock` + `run_once` 的后台续期线程（`queue.renew_lock=true` 时开启，默认关闭零回归） |
| P7 | 并发交错 | 4 个真实进程高竞争领取 200 条会重复/漏单/锁崩 | **未成立（安全实锤）** | claimed=200/200，dup=[]，missing=[]，errors=[] |
| P8 | 控制意图交错 | cancel 与 reset 有明确优先级，先到先赢 | **成立（低危：无裁决）** | `reset_then_cancel` 与 `cancel_then_reset` 两种顺序都收敛到 (A:PENDING,B:PENDING,verA:5,verB:5)：reset 恒胜、cancel 在非 RUNNING 状态是本地 no-op；文档未声明该优先级。→ BUG-290 |
| P9 | 幂等 / 依赖 / 版本 | 提交幂等、依赖校验、版本单调的文档口径与实现一致 | **实现与 §10 一致，但 §14 措辞自相矛盾** | 同批重复名 1 行取 v1、skipped=1；跨提交重复跳过且版本不前进；未知依赖抛可读 DagValidationError；同批互依赖允许。§14 写「幂等 upsert」与 §10「不会产生新行」矛盾。→ BUG-291 |
| P10 | 畸形输入 | 异常任务名会被注入/往返不一致；坏 deps 抛底层 TypeError | **未成立（处理得当）** | 5 个异常任务名全部往返一致（含 `a/b`、`a' OR 1=1--`、中文名）；坏 deps 抛可读 DagValidationError（`42`/`""`/`"[1,2"`/`"{not json"` 均被拒） |

第二轮建议（按严重度）：

1. **P6（中）**：~~补租约续期通道~~ → **已完成（BUG-289 收口）**：`TaskStore.touch_lock`（基类默认实现走 `update_fields`，因此 PG 等后端零改动即获续期能力；Sqlite 覆盖为版本无关 UPDATE）+ `TaskQueue.renew_lock` + `run_once` 的后台续期线程（`queue.renew_lock`/`renew_interval_sec`，默认关闭 ⇒ 零回归）。文档 §15 已写明"默认不续期 ⇒ 执行时长必须短于租约"这一硬约束。
2. **P8（低）**：在 §14 显式声明裁决规则，并补「两种顺序各跑一遍、断言与文档一致」的回归用例。
3. **P9（低）**：把 §14 的措辞统一为「按 task_name 幂等合并：已存在的行保持不变并计入 skipped」，
   并在 §10 写明更新已存在任务的路径（cancel 后重新提交）。

## 第三轮语料（停机/看护 / 同步乱序 / 载荷与结果边界，2026-10-22）

运行：`cd rhop && python tests/boundary/r13_daemon_sync.py`（退出码 = 风险成立条数）

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| D1 | 看护轮询边界 | `scheduled_at == now` 可领、未来的被跳过；已取消任务不被领取 | **未成立（行为正确）** | claimed=['past','now']：`scheduled_at` 恰等 now 可领、未来任务被跳过、已取消任务不领取 |
| D1b | 领取顺序 | priority 并列时顺序不确定或重复 | **未成立** | order=['p1','p2']：并列按 task_id 定序且不重复 |
| D2 | 版本单调门 | 旧版本任务包会被 B 接受 | **未成立** | B 端 v1，喂入 v3/version=0 → `apply_task` 返回 `stale`（旧包被拒） |
| D3 | 载荷边界 | 空 payload 解密失败 / sha 不匹配不抛可读错误 | **未成立** | empty → 正常解密；sha 不匹配 → 抛 `PayloadError` 且文案含期望/实际 sha256 |
| D4 | 结果边界 | result=None / 空 dict 被当成失败；已取消任务仍被执行 | **未成立** | result=None → COMPLETED；空 dict → COMPLETED；已取消任务 → CANCELLED（取消优先） |
| D5 | 租约与看护 | worker 死了不会被回收 / 续期后仍被回收 | **未成立** | `clean_stale_locks` 回收=1：dead（未续期）→ PENDING、alive（已续期）→ LOCKED 保活 |

> 本轮**没有发现新缺陷**（6/6 未成立，退出码 0）。过程中有 5 条探针自身构造错误（白名单只放了
> `cli:python` 导致 handler 被拒；`lock_ttl_sec` 传给了没用的队列；把旧记录塞进 A 端文档导致测的是
> 文档合并语义而非版本门；`LOCKED` 被回收后是 `PENDING` 而非 `RETRY_PENDING`；按名字取结果的映射错位），
> 全部修正后重跑。这些错误本身说明：**白名单、文档合并、回收状态机这些语义值得在文档里写清楚**，
> 已在第 12 轮（BUG-290/291）与 §15 落笔。

## 第四轮语料（大载荷结果落文件 / 停机路径，2026-10-22）

运行：`cd rhop && python tests/boundary/r14_file_channel.py`（退出码 = 风险成立条数）

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| F1 | 引用失效矩阵 | 引用失效时抛错或静默返回 None | **未成立（处理得当）** | 缺文件→`__file_missing__`；内容被改写→`__file_sha_mismatch__`（含期望/实际 sha）；目录消失→`__file_missing__`。全部可区分、不抛错 |
| F2 | 并发写同名 | 并发写同内容产生多个文件 / `.tmp` 残留 | **未成立** | 落点数=1（文件名含内容 sha ⇒ 同内容同名）、`.tmp` 残留=[]、sha 一致 |
| **F3** | 清理误删 | `cleanup_result_files` 只删结果文件 | **成立（中危：误删运维文件）** | 目录里放一个 30 天前的 `README-ops.txt`，`keep_days=7` → `removed=1` 且该文件被删。清理按「目录内任意文件 + 超期」判定，不认文件身份 |
| **F4** | 目录穿越 | 结果落点不得逃逸出 base_dir | **成立（中危：越界写盘）** | `file_channel.dir="../escaped"` → 落点解析到 `<repo>/escaped/…`（base_dir 之外，甚至写进了仓库根）。`_result_file_dir()` 只 `makedirs`，无路径校验 |
| F5 | 分支组合 | 文件通道与 `result_max_bytes` 互相干扰 | **未成立** | 通道开启 → 走 `file_ref`；通道关闭 → 走紧凑摘要（`result_chars`）。两条分支互不冲突 |

第四轮建议（按严重度）：

1. **F4（中）**：`_result_file_dir()` 对 `file_channel.dir` 做路径校验——解析为绝对路径后必须落在
   `base_dir` / `shared_root` 之内，否则报错并拒绝开启（至少拒绝 `..` 与盘符/跨盘）。
2. **F3（中）**：`cleanup_result_files()` 只删**结果文件**（例如文件名匹配 `*-<sha8>.json` 且能被
   `file_ref` 引用，或按 `keep_days` + 前缀白名单），不删目录里的其它文件。
3. 两条都可在 polish 轮一并修，并补回归用例（语料 F3/F4 可直接转正）。

> 本轮探针自身错误 1 处：直接 `json.loads` 拿到的是 Fernet 信封（`{v,alg,ct}`）而不是明文节点，
> 导致 3 条探针报「探针自身异常」；改为先 `decrypt_verify` 再取节点后正常。

> **F3 / F4 已在 polish 轮（BUG-295/296）收口**：`file_channel.dir` 现在会校验落点必须落在
> `base_dir`/shared 之内（越界抛 `SecretError`），`cleanup_result_files()` 只删匹配
> `<UTC时间戳>-<sha8>.json` 的结果文件。语料已翻转为 NOT-CONFIRMED（5/5 全绿）。

## 第五轮语料（守护停机 / closed 稳定性 / 传输大包 / 依赖门控 / 重启回收，2026-10-22）

运行：`cd rhop && python tests/boundary/r15_daemon_transport.py`（退出码 = 风险成立条数）

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| G1 | 停机收尾 | `request_stop()` 会让在途/已完成任务的结果丢失 | **未成立（行为正确）** | `run_once` 内「领取→执行→记录」原子：停机前 COMPLETED 且 `back_info` 非空；停机后 `run_once` 返回 `idle` 且结果仍在 |
| G2 | closed 稳定性 | `closed` 会被后续心跳覆盖 | **未成立** | `write_closed` → 读=closed；随后 `tick` 返回 `stop`，再读仍=closed |
| G3 | 传输层大包 | 大文件写入非原子（残留 `.tmp` / 截断） | **未成立** | 4MB 往返一致、`.tmp` 残留=[]（临时文件 + rename） |
| G4 | 依赖门控 | 上游被取消后下游会被误领 | **未成立** | `claimed=[]`：上游 CANCELLED ⇒ 依赖无法满足 ⇒ 下游不被领取 |
| G5 | 重启回收 | 遗留 LOCKED 任务回收后立即可重领 | **未成立（设计如此）** | TTL 内 `clean_stale_locks` 不回收（回收=0、状态=LOCKED）；租约到期后才回收，与 BUG-289 的续期语义一致 |

> 本轮**没有发现新缺陷**（5/5 未成立，退出码 0）。G1 首轮 CONFIRMED 是探针构造错误：我人为制造了
> 「已领取未执行」的 LOCKED 状态（真实守护进程不会这样，`run_once` 内领取与执行是原子的），
> 改为真实序列后正常。
> **运维提示（G4 的推论）**：上游被取消后下游**永远**不会被领取（依赖无法满足）——这不是缺陷，
> 但要释放下游需要显式 requeue，已在 §10/§15 的措辞范围内。

## 第六轮语料（敏感信息明文/密文双支持，2026-10-22）

运行：`cd rhop && python tests/boundary/r16_secrets.py`（退出码 = 风险成立条数）

本轮第一次把**用户原始需求里的核心配置语义**做成边界实证（此前五轮语料只覆盖队列语义）：

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| S1 | 明文优先 | 同一字段同时给明文与密文时用明文 | **未成立（行为正确）** | 解析结果=`plain-secret`（明文胜出），且触发 1 条告警 |
| S2 | 空串回落 | 明文为空串时回落到密文 | **未成立** | 解析结果=`cipher-secret`（空明文不当作"有明文"） |
| S3 | 告警文案 | 明文告警要告知"运行什么命令可以得到密文" | **未成立（满足用户要求）** | 告警=`⚠ 配置字段 'queue.sftp.password' 使用了明文。生成密文：python -m vools.rhop.secret enc "<你的明文>"。然后把输出填到 'queue.sftp.password_cipher'（密文区），并清空 'queue.sftp.password_plain'（明文区）。` |
| S4 | 严格模式 | `--strict-secrets` 时明文直接报错 | **未成立** | 抛 `SecretError`，文案可读 |
| S5 | 日志打码 | 秘密值在输出里被打码 | **未成立** | `mask_value('super-secret-value')='su***ue'` |
| S6 | 回填一致性 | `secret enc` 产出的密文能被配置直接加载 | **未成立** | CLI 生成 → 配置加载 → 解出 `cli-secret`，与原文一致 |

> 本轮**没有发现新缺陷**（6/6 未成立，退出码 0）。过程中有 2 处探针自身错误：① `SecretResolver` 没有
> `encrypt_plain`（改用 `secret enc` CLI 生成密文）；② 告警走 **stderr**（`_default_warner`）而非 logging，
> 直接注入 `warner` 或用 `redirect_stderr` 捕获才拿得到；③ 取值路径写错（秘密在 `queue.sftp` 下，
> 不是顶层 `sftp`）。全部修正后重跑。

## 第七轮语料（双方共享介质 local/http/sftp，2026-10-22）

运行：`cd rhop && python tests/boundary/r17_shared_medium.py`（退出码 = 风险成立条数）

用户第二条要求是「数据库需要双方都能读写」——共享介质就是这条要求的核心。此前六件语料只碰过
`LocalSharedPath` 一次（G3 的大包原子写），本轮把**介质层**做成边界实证。

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| T1 | 介质类型识别 | `http://` 会被当成本地目录 | **未成立（行为正确）** | `make_shared_path('http://example.invalid/shared')` 的内层路径就是 `http://example.invalid/shared/`，且没有尝试建本地目录（历史上 `build_shared` 曾把 http 的 abspath 当目录，已修） |
| **T2** | 路径穿越 | `shared.write` 不得逃逸出 base_dir | **成立（中危：共享库落点跑偏）** | `shared.write=<base>/../escaped-dir` → `build_store()` 产出的库路径是 `<cwd>/tasks.db`（base_dir 之外，本例写进了仓库根）。根因：`shared.write` 只有视图解析，没有像 `file_channel.dir` 那样的落点校验（BUG-295 只覆盖了文件通道） |
| T3 | 介质不可达 | 不存在的路径会崩或报错不可读 | **未成立** | 自动建目录，write→read 往返一致 |
| T4 | 并发读写 | 两个进程同时写共享介质会互相破坏 | **未成立** | 两个子进程各写 3 个文件、读回 6 条内容一致、无错误 |
| T5 | 写读删一致 | 删除后仍能读到 / 读不到已写的 | **未成立** | write→read 一致；remove 后 `exists=False` |

第七轮建议：**T2（中）**：给 `shared.write` 加与 `file_channel.dir` 相同的落点校验（解析为绝对路径 +
realpath，必须落在 `base_dir` 或显式声明的共享根之内，否则抛配置错误），至少拒绝 `..` 上跳与跨盘符；
补一条「逃逸 ⇒ 配置报错」的回归用例（语料 T2 可直接转正）；§4/§15 同步写明校验规则。

> 本轮探针自身错误 1 处：T1 首轮 CONFIRMED 是**我看错了属性**——网络介质的标识在 `SharedPathView`
> 的内层 `path` 上，不是视图的 `kind`；改为检查内层路径后正常。T2 的调试与语料运行都曾把共享库写到
> 仓库根，已全部删除并核对 `git status` 干净。
>
> **T2 根因更正（BUG-302 收口时）**：初报把成因写成「`shared.write` 没有落点校验」，实测后修正为
> 「**相对 `store.path` 被按进程 cwd 解析**」——`shared.write` 指向 base_dir 之外**本身不是缺陷**
> （共享介质本就该在双方约定的位置，如 `/mnt/shared`），真正的缺陷是库没有落在介质里
> （A/B 会读写不同的库）。已修：相对路径一律相对共享根解析 + 落点必须在共享根之内。

## 第八轮语料（重试与退避状态机，2026-10-23）

运行：`cd rhop && python tests/boundary/r18_retry_backoff.py`（退出码 = 风险成立条数）

| id | 边界类型 | 假设 | 判定 | 证据 / 复现要点 |
|---|---|---|---|---|
| R1 | 退避窗口 | `RETRY_PENDING` 在 `retry_delay_min` 内不可重领 | **未成立（行为正确）** | 失败后状态=RETRY_PENDING；窗口内 `claim_next=None` |
| R2 | 计数累加 | 重试计数跨周期累加，到 `max_retries` 转 FAILED | **未成立** | `max_retries=2`：状态序列 `[RETRY_PENDING, RETRY_PENDING, FAILED]` |
| R3 | 零重试 | `max_retries=0` 失败即终态 | **未成立** | 首次执行后=FAILED、不再可领 |
| R4 | 零退避 | `retry_delay_min=0` 立即可重领 | **未成立** | 失败后立刻 `claim_next` 可领 |
| **R5** | 超时约束 | `timeout_min` 必须真正约束命令执行时长 | **成立（高危：超时未生效）** | `timeout_min=0.05`（3s）、命令睡 5s → 实际耗时 **5.29s**、状态 COMPLETED。根因：`run_payload` 没接 `timeout_min`，命令超时只受 `exec.timeout_sec`（默认 3600s）约束。**连带**：租约按 `timeout_min×60` 算 ⇒ 租约先过期、命令还在跑 ⇒ 被别的 worker 重复领取执行 |
| R6 | 重置连带 | `retry_failed` 把 FAILED 重置为可重领 | **未成立** | 第1次=RETRY_PENDING、第2次=FAILED、reset 后=PENDING、可领=True |

> 本轮探针自身错误 2 处：① `exec` 是**顶层**配置键，我一开始把它塞进 `queue` 里，导致 `allow_any`
> 从未生效、命令被白名单挡下（测到的是白名单而非重试）；② R2 里手动 `claim_next` 后又调 `run_once`，
> 造成双重领取。两处都修正后重跑，重试/退避语义本身全部符合 §6 文档。

## 已知不报为 bug 的项

- P1 / P7：都是**期望行为成立**的证明（并发安全），不是缺陷；按 bugfind「宁缺毋滥」的红线只留作安全证据。
- P9 / P10：实现行为正确且与 §10 口径一致，本身不构成缺陷（P9 的文档措辞矛盾已单列 BUG-291）。
- `fist-mbt` 侧的 `mode_templates`（BUG-375）、`run_check/verify` 的命名空间路由（BUG-374/378）、
  `ocr_scan` 的 dry_run 可用性口径等属工具缺陷，已分别入账到 FIST-Mbt 台账，不记在本语料。
