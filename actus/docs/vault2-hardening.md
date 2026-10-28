# vault2 密钥库加固（seed_key 不再明文落库）

> 状态：**已实施**（2026-10-28，第 9 轮；第 8 轮的设计决策保留在 §5，实施结果见 §6）
> 适用模块：`actus/vools/actus/vault2.py`
> 结论：`identities.seed_key` 现在**只存密文**（`enc:v1:<fernet>`），
> 默认保护方式是 **OS keyring**；无头环境用 **外置 passphrase**；
> 两者都不可用时 **fail-closed 拒绝打开**（绝不退回明文）。

## 1. 原风险（第 8 轮实测，保留作背景）

1. **库文件与密钥材料同库**：改前 `identities.seed_key`（TEXT）与 `key_salt` 都是明文；
   `master_key = PBKDF2(seed_key, dynamic_code, key_salt)`，L1 身份 `dynamic_code` 为空串。
   ⇒ 只拿到 `vault2.db`、不知道 PIN、不登录，就能派生出 `master_key` → 解出全部 secrets
   （实测解出 `sk-SUPER-SECRET-123`）。
2. **旧默认目录是进程 cwd**：改前 `DEFAULT_VAULT_DIR = os.getcwd()/_meta/vault` —— 已改为
   `~/.actus/vault2/`（可用 `ACTUS_VAULT2_DIR` 覆盖），旧位置首次打开时自动迁移。
3. **无文件权限加固**：改前实测 db 权限位 `0o666` —— 已加目录 `0700` / 库与审计文件 `0600`
   （best-effort，POSIX 生效）。

## 2. 本轮的实现（数据流）

```
register()
  seed_key = 32B 随机
  stored   = "enc:v1:" + Fernet(KEK).encrypt(seed_key.hex())
  db       : identities.seed_key = stored ; key_protection = <方式> ; key_meta = <JSON|null>
  KEK 来源 : keyring 条目 / PBKDF2(passphrase, salt) / 随库密钥文件（0600）

auth() / recover() / rotate() / rollback()
  读 seed_key 列（密文） → _decode_seed_hex() 按 key_protection 取 KEK 解回 hex
  → 后续派生/比较逻辑与改前完全一致（PIN、动态码、master_key、backup_key 均不变）
```

新增列（老库用 `ALTER TABLE ... ADD COLUMN` 自动补，**不动既有列**）：
`identities.key_protection TEXT`、`identities.key_meta TEXT`（passphrase 模式的 salt/iters）。

## 3. 三种保护方式与选择顺序

| 方式 | 适用 | KEK 存放 | `status().key_protection` |
|---|---|---|---|
| **keyring** | 桌面（Windows Credential Manager / macOS Keychain / Linux Secret Service） | OS 凭据库，service=`vools-actus-vault2`，username=`<identity_id>` | `keyring` |
| **passphrase** | 无头/CI/容器（无 keyring 时兜底） | `ACTUS_VAULT2_PASSPHRASE`（或交互式输入）→ PBKDF2-SHA256 200k | `passphrase` |
| **file-key** | 显式传 `vault_dir` 的嵌入式/测试用法 | 随库密钥文件 `.vault2.key`（0600） | `file-key` |

解析顺序（`Vault2.__init__`）：

1. 设了 `ACTUS_VAULT2_PASSPHRASE` → **passphrase**（强制 keyring 时例外，见第 2 条）
2. `ACTUS_VAULT2_KEY_PROTECTION=keyring|passphrase|file-key` → 强制指定
3. 显式 `vault_dir`（嵌入式/测试）→ **file-key**
4. 默认目录 `~/.actus/vault2` → **keyring**；keyring 不可用 → **抛 `Vault2KeyProtectionError`（拒绝打开）**

> `ACTUS_VAULT2_NO_PROMPT=1` 可禁用交互式口令输入（无头环境防挂起）。

### keyring 可用性探测（不是只看 import）

`probe_keyring()` 会：懒导入 → 检查后端不是 `fail`/`null`（无桌面会话/容器常见）→
**实写一条探针凭据并读回**（"能写不能读"的后端也会被识破）→ 删掉探针。
探针失败的原因会原样进 fail-closed 报错，便于排查。

## 4. fail-closed（硬要求）

- 默认目录 + keyring 不可用 + 无口令 → `Vault2(...)` **直接抛错**，消息里给出 3 条解决路径
  （装 keyring / 设 passphrase / 显式指定保护方式），并说明现有库不会丢（配好后首次打开自动迁移）。
- 库已用某种方式保护，但本次解析到别的方式（例如换机器没带走 keyring 条目、忘了设口令）→
  抛 "该密钥库用 X 保护，但本次解析到 Y —— 拒绝以错误方式打开"，**绝不猜测/降级**。
- keyring 条目丢失 → `auth()` 返回可读错误（`vault_key_protection_unavailable`），不返回空值。
- 迁移（明文 → 密文）**要么全成、要么不改**：keyring 条目先写，任一失败则删除已写条目并抛错；
  db 侧用单事务 UPDATE。

## 5. 设计决策（第 8 轮结论，仍然有效）

1. 上一轮只做最小加固（目录/权限/告警/文档）；**本轮实施 keyring + passphrase**。
2. 首选 OS keyring（A），passphrase（C）作无头兜底；**不选 DPAPI**（仅 Windows，会逼出三套实现）、
   TPM 仅作未来高安全档位。
3. **禁止静默降级**：keyring 与 passphrase 都不可用 → 拒绝打开，绝不回退明文或弱封装。
4. L1 定位：本机可用性优先、无第二因子；高价值凭据用 L2/L3。

## 6. 实施后的边界与已知取舍（诚实记录）

- **file-key 模式的边界**：显式传 `vault_dir`（嵌入式/测试）时用随库密钥文件（0600）。
  攻击者只拿到 `vault2.db` 文件解不出 secrets；但**能同时读该目录的用户**可以解密。
  需要 OS 级隔离（凭据库按登录用户隔离）请用默认目录或设置 passphrase / 强制 keyring。
  `status().key_protection_warning` 会说明这一点，不静默。
- **没有做 keyring 的跨机器同步**：库文件拷到另一台机器后，keyring 条目不存在 → 拒绝解密（符合预期）。
  迁移/备份场景请显式用 passphrase 模式。
- **L2/L3 的第二因子**：`seed_key` 仍是 TOTP 种子。本轮解决的是"库文件泄露"场景；
  若要防御"能读 keyring 的本机用户"，需要硬件因子（TPM/HSM，未来档位）。
- **`key_meta` 里存 passphrase 的 salt/iters（明文）**：salt 本来不需要保密，iters 固定 200k。
- **密钥轮换（`seed_key` 生命周期）：暂缓 —— 原被一个 P0 阻塞，该 P0 已在第 16 轮修复（§6.1）。**
  现有 `recover()` 不改变 `seed_key`，因此 KEK 也无需轮换；而真正的 `seed_key` 轮换
  必须以「`master_key` 可稳定重算」为前提 —— 该前提**现已满足**（见 §6.1），
  轮换可作为后续独立一轮实现（原地重加密，不需要 PIN、不需要导出重录）。

### 6.1 P0（第 15 轮发现，**第 16 轮已修**）：L2/L3 的 `master_key` 曾绑定 60s 动态码

> **已修**：`master_key` 现在只由 `seed_key + key_salt` 决定（`derive_master_key_stable`），
> 动态码退回本职 —— **只做认证挑战**（TOTP 校验 + `used_codes` 防重放），不再参与 KDF。
> 旧数据由 `Vault2.migrate_master_derivation()` 迁移（登录成功时自动触发一次；
> 单事务、全成或全不改、幂等；`rotated_backups` **无需迁移**，它由 `_derive_backup_key(seed)` 派生）。
> 验收：`tools/audit/verify_vault2_master_migration.py`（16 项全过：P0 复现 / 迁移后跨窗口可读 /
> 中途失败整体回滚 / 幂等 / L1 行为不变 / 读路径零写），
> A/B 对照：`tools/audit/prove_vault2_window_master.py`。
> **轮换不能追溯保护已被拷走的密文** —— 它只缩短"泄漏快照"的有效期，这点别给人错误的安全感。
> 以下保留事故记录，作为「为什么不能把动态码掺进 KDF」的案例。


派生链（`vault2.auth()`）：
```
dynamic_code   = TOTP(seed_key, 当前时间窗口)          # 每 60s 变一次
master_key     = PBKDF2(seed_key_hex + dynamic_code, key_salt)
row_key        = PBKDF2(master_key, row_salt)
```
⇒ **`master_key` 每分钟都不一样**。于是在窗口 A 写入的 secrets，在窗口 B 重新 `auth`
之后就用新 `master_key` 去解 —— **解不开**。

- **L1 身份不受影响**：`effective_dynamic = ""`（空串），`master_key` 稳定。
- **L2/L3 受影响，而 `register()` 的默认级别正是 L2。**
- 复现脚本（可复跑）：`tools/audit/prove_vault2_window_master.py`
  ```
  [窗口1] auth=ok code=557394
           set_secret(K)=ok
           get(K)='TOP-SECRET'
  [窗口2 +300s] auth=ok code=116931
                get(K)=error | message=凭证解密失败（密钥错误？）
  ```
- **为什么现有测试没发现**：所有用例都在**同一个 60s 窗口内**完成
  "register → auth → set → get"；而真实用法（今天 `vault set`、明天 `vault get`）
  必然跨窗口。这也是为什么 `pytest -k vault` 全绿却掩盖了它。
- **好消息：旧数据可救**。每条 secret 都有 `created_at`，用它反推写入时的窗口计数器，
  就能重建当时的 `master_key`：
  ```
  [可迁移性] 用 created_at 反推窗口 29886925 重建 master → 解密旧密文 = 'TOP-SECRET'
  ```

**正确的修复顺序（三轮，本轮只做判断不动产品代码）：**
1. **修派生**：`master_key = PBKDF2(seed_key_hex, key_salt)`（**只由 seed 决定、与时间无关**），
   动态码退回它本来的职责 —— **只做认证挑战**（TOTP 校验 + 防重放），不再参与 KDF；
2. **迁移旧数据**：对每条 secret，用 `created_at` 反推窗口重建旧 master，解密后用新派生重加密
   （同一事务、全成或全不改；迁移脚本可复用 §6.1 的探针逻辑）；
3. **最后再做 `seed_key` 轮换**：派生稳定后，轮换 = 换 seed + 用新 master 重加密全部行 + 换
   `seed_key` 信封，全部落在**一个 SQLite 事务**里（`_db()` 已保证 commit/close 语义），
   失败即回滚；此时才有意义。

**轮换本身的价值（修完 P0 后仍值得做，但优先级低于 P0）**：`master_key` 不含 PIN，
所以 `seed_key` 是**唯一的密码学根** —— 只要同时拿到 `vault2.db` 与 seed 信封的 KEK
（keyring/口令），就能解出全部 secrets。轮换缩短"泄漏快照"的有效期（cryptoperiod），
并让历史 TOTP 失效；但它**不能**追溯保护已经被拷走的密文。

## 7. 验收（第 9 轮实测）

| 验收项 | 结果 |
|---|---|
| 新库（keyring 模式）：db 里 `seed_key` = `enc:v1:…`，keyring 有条目，`get_secret` 正常 | ✅ |
| 删除 keyring 条目 → `auth` 返回明确错误（不返回空值） | ✅ |
| 旧库（明文 seed_key）→ 首次打开自动迁移；迁移后明文消失、**旧 secrets 仍可读** | ✅（file-key 与 keyring 两种方式都验过） |
| fail-closed：模拟无 keyring 后端 + 无口令 → 拒绝打开 + 可读指引 | ✅（默认目录与显式目录都验过） |
| passphrase 模式：可读写；换环境无口令 → 明确拒绝（不猜明文） | ✅ |
| `status()` 三种方式都如实报告 | ✅（`keyring` / `passphrase` / `file-key`） |

测试隔离：所有验证都在 `HOME` 指向临时目录的进程里跑；验证写入的真实 keyring 条目在脚本末尾删除。

## 8. 运维提示

- 桌面用户：`pip install vools-actus[keyring]`（Windows/macOS 系统自带凭据库，无需额外服务）。
- 无头/CI：`export ACTUS_VAULT2_PASSPHRASE='<口令>'`（口令丢失 = 库不可恢复，请与备份一起保管）。
- 只想在受控目录里试用/测试：显式传 `vault_dir`（file-key 模式，`status()` 会标注边界）。
- 升级已有库：**先配好 keyring 或 passphrase，再让任意入口打开一次**；打开时自动迁移并清掉明文。
  若暂时无法配置，库仍保持原样（打开会被拒绝，数据不丢）。
