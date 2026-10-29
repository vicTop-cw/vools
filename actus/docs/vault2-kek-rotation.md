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
| **0 ✅ 已完成（第 19 轮）** | `key_meta` 兼容字段 + `kek_retired` 表 + `status()` 诊断（**不改任何 KEK**） | 旧库打开/注册/轮换 seed 全部回归绿；旧行 `kek_gen` **按 0 视为**（见 §4.4.1，不迁移不回填） |
| **1 ✅ 已完成（第 20 轮）** | **passphrase 模式**轮换（单事务，`rotate_kek(new_passphrase=None)`） | 换 salt 后旧数据可读、旧信封无法再解；故障注入：UPDATE 抛错 → 全回滚 |
| **2 ✅ 已完成（第 22 轮）** | **keyring 模式**：双代 + 日志 + GC（CLI/MCP 入口仍待第 4 步） | 6 个崩溃点注入（step1 前/后、commit 前/后、GC 前/后）均可恢复；孤儿条目不阻塞 |
| 3 | **file-key 模式**（同骨架；`O_EXCL`/0600；GC 扫目录回收孤儿） | 同上；目录里旧 key 文件按日志删除 |
| 4 | CLI `actus vault rotate-kek [--dry-run] [--all]` + MCP `actus_vault_rotate_kek` + 文档 | `--dry-run` 零写；失败 `failed_names` 不静默 |

#### 4.4.1 第 0 步已完成的内容（第 19 轮实测）

**① `key_meta.kek_gen`（`int`，缺省 0，**不新增 DB 列**）**
- 读：`vault2.kek_gen_of_meta(key_meta)` —— 缺失/JSON 损坏/非整数 一律回落到 `0`。
- **为什么放 `key_meta` 而不是加列**：`key_meta` 本来就是"这个身份的 seed 信封由什么保护"
  的元数据（passphrase 的 salt/iters 就在里面），代数标记同属这一语义；加列需要第二条
  `ALTER TABLE` 迁移路径（已有 `_ensure_identity_key_columns`），为一个整数不值得。
- **兼容**：现有库没有该字段 ⇒ `kek_gen = 0`，**不迁移、不回填、不告警**。
  （注：本节早先版本写"按 1 回填"，与 lead 本轮要求冲突；已统一为 **0**，代码与文档一致。）
- **本轮只读**：没有任何代码写 `kek_gen`（只有将来的轮换步骤会写）。

**② `kek_retired` 表（纯增量 schema，`_init_schema()` 里 `CREATE TABLE IF NOT EXISTS`）**
```sql
CREATE TABLE IF NOT EXISTS kek_retired (
    identity_id TEXT NOT NULL,
    kek_gen     INTEGER NOT NULL,
    locator     TEXT NOT NULL,      -- keyring user / file 路径 / 'passphrase'
    retired_at  TEXT NOT NULL,
    cleaned     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (identity_id, kek_gen)
);
```
- 现有库**首次以写路径打开**时自动补建（幂等；连跑 3 次无变化）。
- **本轮不写入任何行**（`SELECT COUNT(*)` 实测为 0）。

**③ `status()` 三个只读诊断字段**
| 字段 | 含义 |
|---|---|
| `kek_gen` | 该库所有身份代数**最小值**（有身份停在旧代就报旧代）；空库/库不存在 → 0 |
| `kek_gen_max` | 最大值（多身份时用来看"轮换是否完成一致"） |
| `kek_retired_count` | `kek_retired` 中 `cleaned=0` 的行数（未清理旧代数量，应为 0） |
| `kek_rotation_supported` | 当前保护模式是否可轮换 KEK（keyring / passphrase / file-key = true；unavailable / legacy-plaintext = false） |

**`status()` 仍然零写**：对**不存在**的库只做 `stat` 判断，不建目录/库/表（实测目录树快照前后相同）。

**④ 后续步骤现在能观测到什么**：代数（`kek_gen`/`kek_gen_max`）、未清理旧代（`kek_retired_count`）、
本模式是否支持轮换（`kek_rotation_supported`）—— 阶段 1-3 的"轮换后计数归零""旧代出现在
`kek_retired` 且 GC 后 `cleaned=1`"都可用这三个字段断言。

验收脚本：`actus/tools/audit/verify_vault2_kek_step0.py`（22 项：旧库兼容 / 新库三字段 /
表 0 行 / `status()` 零写 / register-auth-set-get-rotate 全照旧 / `_init_schema` 幂等 3 次）。

#### 4.4.2 第 1 步已完成的内容（第 20 轮实测）

**API**：`Vault2.rotate_kek(token, new_passphrase=None, caller=None)`（模块级 `vault2.rotate_kek(...)` 同签名）。

**为什么 passphrase 能单事务**：KEK = `PBKDF2(passphrase, key_meta.salt)`，**salt 就在 DB 里**。
"换 KEK" = 换 salt + 用新 KEK 重包 seed 信封 + `kek_gen += 1` —— 三件事是**同一个 UPDATE**。
keyring / file-key 的 KEK 在**外部 store**，因此必须双代并存 + 日志 + GC（第 2/3 步）。

**单事务实现**
```
读：_decode_seed_hex(identity_id, seed_key, protection, key_meta)      # 旧 KEK 解信封
算：new_salt = random(16)；new_kek = PBKDF2(passphrase, new_salt)
    new_meta = {kdf, salt:new_salt, iters, kek_gen: old+1}
    new_envelope = ENC_V1 + Fernet(new_kek).encrypt(seed_hex)
验：用新 KEK 解 new_envelope，必须 == seed_hex（否则**不写**）
写：with self._db(): UPDATE identities SET seed_key=?, key_meta=? WHERE id=?   ← 单事务
audit: rotate_kek（成功/失败都记）
```
失败语义：任何一步抛错 → 事务不 commit（`_db()` finally close ⇒ 回滚）⇒ 信封 / key_meta /
`kek_gen` **全不变**，数据照旧可读（已用 `_apply_kek_rotation` 注入点实测）。

**关键安全性质**：KEK 只包裹 `seed_key` 信封，**不包裹 secrets** ⇒ 轮换 KEK
**不需要重新加密任何 secret**（返回体 `secrets_reencrypted: 0`）。因此它比 `rotate_seed_key`
风险低得多：`rotate_seed_key` 要重加密全部 secrets + backups，KEK 轮换只动一行。

**`kek_retired` 仍不写**：passphrase 模式没有外部条目可清理（旧 KEK 从未落盘，
只活在旧 salt 的推导里）⇒ 第 0 步建的表保持 0 行（返回体 `kek_retired_written: false`）。

**三种模式明确区分（不假装成功）**
| 保护方式 | `rotate_kek` 行为 |
|---|---|
| `passphrase` | ✅ 单事务轮换（本步） |
| `keyring` | ❌ `kek_rotation_unsupported` + 说明需要第 2 步（**零写**，实测快照不变） |
| `file-key` | ❌ 同上，指向第 3 步 |
| `unavailable` / `legacy-plaintext` | ❌ 同上 |

**`new_passphrase` 语义**：`None` = 沿用当前口令、只换 salt（最常见）；显式给新口令 →
同时换口令，返回体带 warning「必须同步 `ACTUS_VAULT2_PASSPHRASE`，否则下次打不开」，
并**实测旧口令确实解不开**（明确报错，不静默）。

**`status()` 反映代数**：轮换后 `kek_gen` 从 0 → 1（`kek_gen_max` 同步）；连续两次 → 2。

**验收**：`actus/tools/audit/verify_vault2_kek_step1.py`（29 项：轮换成功 / seed 与 secrets
密文未变 / 新实例重开可解 / status 代数 / 连续两次 / 写阶段故障全回滚 / 非 passphrase 拒绝且
零写 / 换口令后旧口令失效、新口令可用）。

#### 4.4.3 第 2 步已完成的内容（第 22 轮实测）

**实现**：`Vault2._rotate_kek_keyring()`（由 `rotate_kek` 按保护模式委派）。骨架
（§4.4.2 之前）先落地一轮，再搬进产品代码 —— 顺序是"先能验证，再实现"。

**locator 约定（向后兼容）**
```
第 0 代（旧库）：keyring user = identity_id            ← 不迁移、不动旧条目
第 N 代（N≥1） ：keyring user = "{identity_id}#g{N}"
```
`_keyring_locator()` 优先读 `key_meta.kek_locator.user`，否则按 `kek_gen` 推导；
`_kek_for()` 先按 locator 找，找不到再回落到旧规则 `identity_id`。

**算法（双代并存，跨崩溃窗口安全）**
```
old_kek = _get_keyring_kek(locator_old)              # 旧代
seed    = decrypt(old_kek, envelope)
C1  ──────────────────────────────────────────────  写新代之前
_put_keyring_kek(locator_new, new_kek)               # 外部写
C2  ──────────────────────────────────────────────  写后、提交前
readback = _get_keyring_kek(locator_new)             # ★ 回读自检（不能用 new_kek 自证）
if readback != new_kek: abort（不提交）
BEGIN; UPDATE identities SET seed_key=enc(new_kek,seed), key_meta={gen+1, locator_new}
       INSERT kek_retired(gen_old, locator_old, cleaned=0); COMMIT
C3  ──────────────────────────────────────────────  GC 之前
C4  ──────────────────────────────────────────────  删旧代之前
delete_password(locator_old)                         # 可能抛（fail_delete）
still = _get_keyring_kek(locator_old)                # ★ 删后回读确认（delete_lag）
if still is None: UPDATE kek_retired SET cleaned=1   # 只有确认不在才标 1
C5  ──────────────────────────────────────────────  删后、未标 cleaned
C6  ──────────────────────────────────────────────  GC 后
```

**两条硬规则（`kek_retired` 日志可信的全部意义）**
1. **写后回读自检**：`set_password` 没抛 ≠ 后端存对了（`stale_read` 场景）→ 不一致就**不提交**；
2. **删后回读确认**：`delete_password` 没抛 ≠ 条目没了（`delete_lag` 场景）→ 只有回读**确认不在**
   才置 `cleaned=1`，否则保留 `cleaned=0` 等下次重试，并在返回值 `gc` 里如实报告。

**已知局限（诚实记录）**：若 OS 凭据库**丢失了 DB 正在引用的那一代**（`restart_drop`：
凭据库被清 / 云同步回滚），seed 将永久不可解 —— DB 侧任何设计都救不了，只能靠备份/多副本。
骨架矩阵里这条被标为"已记录局限"，断言的是"它确实会失败"，而不是假装通过。

**验收**
- `actus/tools/audit/kek_crash_matrix.py`：6 崩溃点 × 4 不变式矩阵 + 6 类 store 故障模式，
  实跑"正确实现 6/6 通过 / 错误实现被 C1、C2 抓住"。
- `actus/tests/test_kek_rotation_crash_matrix.py`：**24 passed, 0 xfailed**（含真实实现的
  keyring 轮换 / `delete_lag` 不标 cleaned / `stale_read` 中止不提交）。
- 骨架的 `test_wrong_impl_passes_after_danger_window` 与灵敏度自检**保留**（落地后仍守护骨架本身）。

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
