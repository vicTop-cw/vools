# vault2 KEK 轮换设计（**本轮不实现**）

> 状态：**设计稿，未实施** · 第 17 轮审计产出（`cmd-polish`），2026-10-29
> 关联代码：`vools/actus/vault2.py`（`_kek_for` / `_encrypt_seed_hex` /
> `_reencrypt_seed_envelope` / `_decode_seed_hex` / `_migrate_key_protection` /
> `rotate_seed_key`）；关联文档：`docs/vault2-hardening.md`（三种保护方式）、
> `docs/vault-v1-v2-merge.md`（v1/v2 合并背景）。
> **本轮只写设计，不改代码** —— 原因见 §10。

---

## 1. 现状：KEK 是什么、保护什么

vault2 的密钥层级（编号与代码一致）：

```
KEK（32B 随机密钥 / 口令派生）            ← 存在哪里由 key_protection 决定
 └─ 信封加密 seed_key（identities.seed_key，前缀 enc:v1:）
     └─ seed_key → master_key（derive_master_key，recover 不变）
         └─ 每个 secret 的 row_key（per-row salt + KDF）
             └─ secrets.value / rotated_backups.value
```

- **KEK 只保护 `seed_key` 的信封**，不直接加密业务密文；但它是整条链的**入口**：
  拿到 KEK 就能解开 seed → 派生 master → 解开该身份全部 secrets。
- KEK 的落点（`vault2.py:537 _kek_for`）：

| `key_protection` | KEK 实际存放 | 代码 |
|---|---|---|
| `keyring` | OS 凭据库，`service=vools-actus-vault2`、`username=identity_id`，值为 base64(32B) | `:134 KEYRING_SERVICE`、`:540` |
| `passphrase` | **不落盘**：KEK = PBKDF2(`ACTUS_VAULT2_PASSPHRASE`, salt=DB 内 `identities.key_meta.salt`, 200000 迭代) | `:567-570`、`:140 PASSPHRASE_ITERS` |
| `file-key` | 随库文件 `<vault_dir>/.vault2.key`（0600，base64 32B） | `:138 FILE_KEY_NAME`、`:505 _file_key` |

- **KEK 的生命周期完全没有轮换入口**：`_encrypt_seed_hex()` 只在注册/明文迁移时
  生成 KEK（keyring 模式每次调用 `set_password` 覆盖同一 username）；之后永不改变。
- `rotate_seed_key()`（`:1330-1464`）**刻意不换 KEK**，代码注释写得很明确：
  `_reencrypt_seed_envelope()`（`:598-606`）
  > 为什么不调 `_encrypt_seed_hex`：那个会为 keyring 模式**生成新 KEK 并写 keyring
  > 条目** —— 那是 DB 事务之外的写，一旦 DB 提交失败就出现"keyring 换了、DB 还是
  > 旧 seed"，旧 seed 再也解不开（不可逆）。
- 已有"外部写 + DB 事务 + 失败补偿"的先例，但**只适用于"增量写"**，不适用于
  "覆盖已有 KEK"：
  * `register()`：先写 keyring 条目，再 INSERT；失败时 `delete_password` 回滚
    （`:851-858`）；
  * `_migrate_key_protection()`：先把明文 seed 加密并写 keyring，全成功后单事务
    UPDATE；异常时删除刚写的 keyring 条目（`:651-672`）；
  * 这两处**不覆盖任何既有 KEK**，所以"先写后删"的补偿是安全的；而 KEK 轮换要
    **替换**正在使用的 KEK，先写会**毁掉旧 KEK** —— 这是本质区别。
- `recover()`（`:999-`）先用 KEK 解 `seed_key`（`:1015 _decode_seed_hex`）再校验
  恢复密钥 ⇒ **KEK 丢失时连恢复密钥也救不回来**（恢复密钥只绑定 seed，不保护 KEK）。

---

## 2. 风险：为什么不能在 DB 事务里简单换

`sqlite3` 事务只覆盖 `vault2.db`；keyring / `.vault2.key` 是**另一个 store**，
没有 XA/两阶段提交，DB 回滚**无法撤销**已经写过的外部条目。把"覆盖同一 KEK 条目"
放进现有流程，两个方向都会产生**永久不可解**的状态：

### 方向 I：先写外部（覆盖同一 keyring item），再提交 DB（当前 `_encrypt_seed_hex` 风格）

```
T0  keyring: K_old        DB: envelope = E(K_old, seed_old)
T1  set_password(identity, K_new)     ← 覆盖：K_old 被销毁
T2  BEGIN
T3  UPDATE identities SET seed_key = E(K_new, seed_old)
T4  COMMIT ← 失败 / 进程崩溃 / 断电
⇒ 现状：keyring 里只有 K_new；DB 里仍是 E(K_old, seed_old)
⇒ 旧 seed 永久解不开（旧 KEK 没有任何副本）        ← 灾难级
```

### 方向 II：先提交 DB，再写外部

```
T0  keyring: K_old        DB: envelope = E(K_old, seed_old)
T1  BEGIN
T2  UPDATE identities SET seed_key = E(K_new, seed_old)  ← K_new 尚未写入 keyring
T3  COMMIT 成功
T4  set_password(identity, K_new) ← 失败 / 崩溃
⇒ 现状：DB 指向 K_new 的密文；keyring 仍是 K_old（或根本没有）
⇒ 新 seed 解不开，同样永久不可解
```

### 崩溃窗口清单（不论上面哪种顺序）

| 崩溃点 | keyring | DB | 结果 |
|---|---|---|---|
| 写外部前 | K_old | E(K_old) | 安全 |
| 写外部成功、DB 未提交 | K_new（K_old 已毁） | E(K_old) | **永久不可解** |
| DB 已提交、删旧未做 | K_new（+K_old） | E(K_new) | 安全（多一个孤儿） |
| 删旧中崩溃 | K_new（旧删一半） | E(K_new) | 安全（GC 重试） |

**结论：问题不在"是否用事务"，而在"旧 KEK 在 DB 切换成功前就被销毁"。**
只要遵守两条不变式，就不需要真正的跨 store 事务：
- **I1（先建后引）**：新 KEK 必须先于"DB 引用它"存在；
- **I2（后删）**：旧 KEK 必须在"DB 不再引用它"之后才可删除；
- **I3（不存旧 KEK）**：任何"把旧 KEK 备份到 DB/日志"的方案都会把轮换变成新的
  密钥落盘点（等于没换），禁止。

---

## 3. 候选方案

### A. 双 KEK 并存 + 代数标记（generation）

DB 记录"当前代数 N"，外部 store 同时保留 N 与 N-1 两代；解密按代数选；换完再清旧代。

- **keyring**：新条目 username = `identity_id#g{N+1}`（不覆盖旧的 `identity_id`）；
- **file-key**：新文件 `.vault2.key.g{N+1}`（`O_EXCL`/0600），旧文件保留；
- **DB**：`identities.key_meta`（已是 TEXT JSON）增加 `{"kek_gen": N+1, "kek_locator": "..."}`
  （passphrase 的 salt 同在该字段）。
- 流程：写新一代（外部）→ 单事务改信封+`kek_gen` → 提交 → 删旧代（外部，可重试）。
- **失败态**：上述所有崩溃窗口都落在"两代并存或旧代仍被引用"的安全侧；最坏只剩
  孤儿新条目（未被任何 DB 行引用，不保护任何东西，无泄漏价值）。
- **恢复流程**：启动/`status()` 时按 DB `kek_gen` 找对应条目；孤儿条目无害。
- **复杂度**：中。**需要在 keyring 存多代**：是（N 与 N-1 短暂并存）。
- **短板**：标准 `keyring` **没有 list API** —— 进程崩溃后"孤儿新条目"无法枚举
  清理（file-key 可以扫目录，keyring 不能），需要 C 的 DB 日志补位。

### B. 信封自包含（把 KEK 材料塞进 DB / 让 DB 自解）

- **B1（字面版，把 KEK 也存 DB）**：等价于 seed 明文落库，直接摧毁"单独偷
  `vault2.db` 解不开"的威胁模型（参见 `vault2-hardening.md` §1/§6 的边界），**拒绝**。
- **B2（KEK 由口令派生）**：这正是 `passphrase` 模式的现状；它不是通用方案
  （keyring/file-key 模式没有口令可派生），但**对 passphrase 模式是可行的特例**：
  salt 在 DB 里，换 salt/换口令 = 纯 DB 单事务（见 §4 推荐里的特例）。
- **质量结论**：作为通用方案**不可行**；作为 passphrase 特例**已被现状覆盖**（缺
  的只是一个显式轮换入口，不是协议问题）。

### C. 事务日志 / 两阶段提交（DB 内写"待完成轮换"记录，恢复时补齐）

- DB 增加 `kek_rotations(identity_id, from_gen, to_gen, state, created_at, ...)`：
  `prepared → committed → cleaned`；进程启动/下次打开库时扫未完成记录并补齐。
- 若**没有 A 的双代**：日志只能记录"打算换"，却无法在"旧 KEK 已被覆盖"后恢复旧
  KEK（要么把旧 KEK 写进日志 = 违反 I3，要么把旧 KEK 留在原位置 = 就是 A）。
- 若**与 A 组合**：日志解决 A 的"keyring 无 list API、孤儿无法枚举"问题 —— 状态机
  记录每一代 locator，GC 只按日志删，不依赖 keyring 枚举。
- **失败态/恢复**：`prepared` 但 DB 未提交 → 回滚外部新条目（或标记 orphan 待 GC）；
  `committed` 但旧代未删 → 按日志重试删除；全部幂等。
- **复杂度**：中。**需要 keyring 多代**：是。**单独使用不足以解决问题**（见上）。

### 方案对比

| 维度 | A 双代+generation | B 信封自包含 | C 纯 2PC 日志 | **A+C 组合（推荐）** |
|---|---|---|---|---|
| 旧 KEK 在 DB 切换前是否仍可用 | ✅（后删） | ❌（不解决跨 store） | ⚠️ 单独用仍会先覆盖 | ✅ |
| 崩溃后是否可能永久不可解 | ✅ 不会 | ✅ 不会（但威胁模型崩塌/仅 passphrase） | ⚠️ 取决于实现是否保留旧代 | ✅ 不会 |
| keyring 是否需存多代 | 是（N/N-1） | 否 | 是 | 是（短暂） |
| 孤儿条目可否清理 | file-key 可、keyring 不可 | 不适用 | ✅（DB 日志记录 locator） | ✅ |
| 是否要把旧 KEK 落盘 | 否 | B1 会（拒绝） | 实现不当时会（拒绝） | 否 |
| 复杂度 | 中 | 低但方案不可行 | 中（单独不够） | 中 |
| 对现有 `rotate_seed_key` 影响 | 无（两者正交） | — | 无 | 无 |

---

## 4. 推荐：**A + C 组合**（双代并存 + DB 侧轮换日志/GC），passphrase 特例走单事务

**一句话理由**：KEK 轮换不是"一次跨 store 事务"，而是"**先建新、后删旧**"的
**代数切换**；A 保证任何崩溃点都可读，C 让 keyring 的孤儿/旧代可被确定性地清理
（不依赖标准 keyring 没有的 list API）。

### 4.1 分保护模式的实现差异（关键）

| 模式 | 外部 store | 是否需要双代+日志 | 理由 |
|---|---|---|---|
| `keyring` | OS 凭据库 | **需要 A+C** | 覆盖同一 item 会毁旧 KEK；无 list API |
| `file-key` | `<vault>/.vault2.key` | **需要 A+C**（可扫目录辅助） | 跨文件系统；rename 可原子但无法与 DB 同事务 |
| `passphrase` | **无外部 store**（salt 在 DB `key_meta`） | **不需要**：单事务即可 | 换 salt/换口令只改 DB 内信封字段 |

> passphrase 特例：`ALTER` 不需要——`key_meta` 里 `{kdf,salt,iters}` + `seed_key`
> 信封字段都在同一行；"换 KEK"= 用新 salt（或新口令）重算 KEK、重包 seed，然后
> `UPDATE identities SET seed_key=?, key_meta=?`，**同一 `_db()` 事务**完成。
> 换口令需要调用方同时提供旧/新口令（旧口令用于解旧信封）。

### 4.2 数据结构（最小改动）

1. `identities.key_meta`（已有 TEXT JSON，向后兼容）：新增
   `"kek_gen": int`、`"kek_locator": {"kind":"keyring","user":"<id>#g2"}` 或
   `{"kind":"file","name":".vault2.key.g2"}`；旧行为缺省 `kek_gen=1`、locator 兼容
   现有规则（keyring username=identity_id / FILE_KEY_NAME）。
2. 新表（C 的日志，GC 用）：
   `kek_retired(identity_id TEXT, generation INTEGER, protection TEXT, locator TEXT,
   retired_at INTEGER, state TEXT /* pending_delete | deleted */, last_error TEXT,
   PRIMARY KEY(identity_id, generation))`
3. `status()` 暴露 `kek_gen` 与 `kek_retired_pending` 计数（只读诊断，不含密钥）。

### 4.3 轮换算法（keyring / file-key 通用骨架，单身份一个事务）

```
0. 只读预检：_kek_for(current locator) → 解当前 envelope → 校验 seed 可用
1. 生成 K_new；写入新一代外部条目（keyring: set_password(user#g{N+1}, K_new)；
   file: open(O_EXCL,0600) 写 .vault2.key.g{N+1}）—— 不碰旧条目（I1）
2. BEGIN IMMEDIATE（拿写锁）
3. UPDATE identities SET seed_key=E(K_new,seed), key_meta={kek_gen:N+1, locator}
   INSERT INTO kek_retired (old gen, old locator, state='pending_delete')
4. COMMIT
5. GC（幂等，失败留 state=pending_delete 下次重试）：
   按 kek_retired 逐条删旧外部条目 → UPDATE state='deleted'
6. 失效该身份的既有会话（master/seed 已变，等价 rotate_seed_key 的做法）
```

**崩溃点检查**：步骤 1 后崩溃 → DB 仍引用旧代，旧代完好（安全；孤儿新代不保护
任何数据）；步骤 3 回滚 → 同上；步骤 4 后崩溃 → DB 指向新代，旧代仍在（安全，
GC 重试）；步骤 5 中崩溃 → 幂等（安全）。

### 4.4 实施步骤（将来执行时照做）

| 阶段 | 内容 | 出口标准 |
|---|---|---|
| 0 | `key_meta` 兼容字段 + `kek_retired` 表 + `status()` 诊断（**不改任何 KEK**） | 旧库打开/注册/轮换 seed 全部回归绿；旧行 `kek_gen` 按 1 回填 |
| 1 | **passphrase 模式**轮换（单事务，`rotate_kek(new_passphrase=None)`） | 换 salt 后旧数据可读、旧信封无法再解；故障注入：UPDATE 抛错 → 全回滚 |
| 2 | **keyring 模式**：双代 + 日志 + GC；新 CLI/MCP 命令 | 6 个崩溃点注入（step1 前/后、commit 前/后、GC 前/后）均可恢复；孤儿条目不阻塞 |
| 3 | **file-key 模式**（同骨架；`O_EXCL`/0600；GC 扫目录回收孤儿） | 同上；目录里旧 key 文件按日志删除 |
| 4 | CLI `actus vault rotate-kek [--dry-run] [--all]` + MCP `actus_vault_rotate_kek` + 文档 | `--dry-run` 零写；失败 `failed_names` 不静默 |

**测试重点**（对应我们第 18 轮审计的盲区谱系）：每个阶段都必须有"**跨崩溃窗口**"
用例（用故障注入/可 替换的 keyring 替身），不能只测 happy path；`--dry-run` 必须
用快照断言零写。

---

## 5. 与 `rotate_seed_key` 的关系（能合并吗？）

- **密码学上正交**：`rotate_seed_key` 换"信封里的内容"（seed），`rotate_kek`
  换"打开信封的钥匙"；两个操作各自原子即可，不需要合并事务。
- **顺序无关，但建议"先 seed、后 KEK"**：
  * seed 轮换的前提是**当前 KEK 可解旧信封**（旧 KEK 必须仍在）；
  * KEK 轮换的前提是**当前 seed 可解**（解开后重包）；
  * 先 seed 后 KEK：KEK 轮换解的是新信封（新 KEK 不存在前，旧 KEK 仍有效）✓；
  * 先 KEK 后 seed：seed 轮换用新 KEK 重包（`_reencrypt_seed_envelope` 会 `_kek_for`
    取当前 KEK）✓ —— 两种都可，**不要**把两者塞进同一个 DB 事务（KEK 跨 store，
    会让回滚横跨两个 store，正是本设计要避免的）。
- **不建议合并成一个原子操作**：`rotate_seed_key` 已经是"单事务、失败全回滚"，
  把跨 store 的 KEK 阶段并进去会把它也变成"半途可能需补偿"的操作，倒退。
- 将来若做编排命令，应显式两阶段、分别报告：`seed_rotated=true` +
  `kek_rotated=true`，任一失败保留已成功阶段（不假装整体成功）——与本项目
  `split_validation`/`partial` 语义一致。

---

## 6. 不做会怎样（风险）

1. **KEK 是长期唯一入口**：它一旦泄漏（OS 凭据库被拷、云同步、备份、内存转储、
   有管理员权限的恶意进程），攻击者拿到**任一时刻的 `vault2.db` 快照**（当前或
   历史备份）即可解出 seed → master → 全部 secrets。
2. **`rotate_seed_key` 不能弥补**：seed 轮换只缩短"只有 DB 泄漏（无 KEK）"的窗口；
   KEK 泄漏后，攻击者对当前库仍可直接解新 seed，对历史备份可解旧 seed ——
   **KEK 不轮换 = 泄漏永久有效**。
3. **无合规退路**：需要"密钥材料定期轮换/事件后轮换"的场景（凭据库疑似泄漏、
   人员/机器变更、审计要求）目前只能重新注册身份（= 所有 secrets 重新录入），
   代价与风险都很高。
4. **`recover()` 也依赖 KEK**：KEK 条目丢失/损坏时，恢复密钥无法救回 seed
   （`recover` 先解信封，见 `:1015`），这是"不换"之外的另一个脆弱点；本设计让
   "换 KEK 时不丢旧代"成为可验证的不变式，同时也为将来做 KEK 备份/recover 打基础。

---

## 7. 明确不做的部分（诚实边界）

- 本设计**不提供**"已被拷走的旧 KEK 重新生效防护"：轮换只能缩短未来泄漏窗口，
  不能追溯撤销已泄漏的 KEK/seed（与 `rotate_seed_key` 的 docstring 同一定位）。
- 不改变默认保护方式，不自动 migrate；不把 KEK 备份到 DB（I3 禁止）。
- **keyring 无 list API** ⇒ 孤儿"新代"条目无法枚举清理（只能靠 C 的日志记录我们
  主动写过的 locator）；这是接受的边界，会在文档/`status()` 里写明。
- 多身份轮换按身份逐个提交（避免长事务锁库）；命令层报告每个身份的
  `rotated/failed`，不做跨身份原子性。

---

## 8. 结论摘要

- **推荐 A+C**：keyring/file-key 模式用"双代并存 + DB 代数标记 + `kek_retired`
  日志 + 提交后 GC"；passphrase 模式用**单事务**（salt 在 DB）即可。
- **核心不变式**：新 KEK 先建（I1）、旧 KEK 后删（I2）、旧 KEK 绝不落盘（I3）。
- **与 `rotate_seed_key` 正交**，可分别执行，建议 seed 先、KEK 后；不合并事务。
- **本轮不实现的原因**：需要 schema 迁移（`key_meta` 兼容字段 + 新表）、跨 store
  协议、按保护方式三套实现、以及 6 个崩溃窗口的故障注入测试；属于"独立课题"，
  值得单独排期与评审，避免在只读路径/轮换热路径上引入新的半途状态。

## 9. 本轮不实现的声明

本文档**只做设计与结论**，`vault2.py` 未做任何修改；`rotate_seed_key` 继续
"只换 seed、复用现有 KEK"（其返回值 `note` 已明示 KEK 未轮换，`:1463-1464`）。
若批准实施，按 §4.4 阶段 0→4 执行，先落 schema 与诊断，再逐模式实现并逐模式
做崩溃注入；每阶段独立可回滚。

---

## 10. 附：现状事实与代码索引（便于实施时核对）

| 事实 | 位置 |
|---|---|
| keyring 服务名/username 规则 | `vault2.py:134 KEYRING_SERVICE`、`:540-554` |
| keyring 探针（写/读/删） | `vault2.py:159-200` |
| passphrase KDF（salt/iters 在 `key_meta`） | `vault2.py:555-570`、`:140` |
| file-key 路径/权限/创建 | `vault2.py:505-534`、`:138` |
| 信封前缀 | `vault2.py:139 ENVELOPE_PREFIX` |
| KEK 选择 | `vault2.py:537 _kek_for` |
| 生成 KEK（注册/迁移用） | `vault2.py:573 _encrypt_seed_hex` |
| 复用 KEK 重包（seed 轮换用） | `vault2.py:598 _reencrypt_seed_envelope` |
| 解信封 | `vault2.py:616 _decode_seed_hex` |
| 明文迁移 + 失败补偿先例 | `vault2.py:638-676` |
| register 失败补偿先例 | `vault2.py:851-858` |
| seed 轮换（不换 KEK） | `vault2.py:1330-1464`（note 在 `:1463`） |
| recover 依赖 KEK | `vault2.py:999-1035`（解信封 `:1015`） |
| key_protection 一致性检查 | `vault2.py:492 _check_existing_key_protection` |
