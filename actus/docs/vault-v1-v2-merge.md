# vault v1 / v2 现状与合并建议

> 第 10 轮审计产出（`cmd-polish`）；**第 12 轮已实施第 3 步（统一 secret resolver）**，
> 实施细节见 §0。

## 0. 第 3 步实施记录（第 12 轮，2026-10-29）

已在 `vault.py` 落地统一 resolver（无新模块）：
`resolve_secret(name, scope, meta_dir, lazy_migrate=None)` /
`write_secret(...)` / `resolve_vault_refs(config, meta_dir)` / `resolver_status()`。

- **读**：v2 优先（凭据 `VAULT_IDENTITY_ID/VAULT_MACHINE_ID/VAULT_PIN`，与 executor 旧口径一致）；
  v2 不可用或没有该密钥 → 回退 v1（`Vault.last_read_source` 记来源）；
  **两边都有且值不同 → `status='conflict'`，不自动选择**（消息里给两个值的 sha256 短指纹，
  不打印明文）。
- **写**：默认写 v2；v2 不可用 → **拒绝**（`code='vault2_unavailable'`），
  仅显式 `allow_v1_write=True` 才写 v1 并 warning（避免"写到 resolver 将来读不到的地方"）。
- **懒迁移**：**默认关闭**，opt-in `ACTUS_VAULT_LAZY_MIGRATE=1`。原因：本轮 CLI 仍直连 v1
  写入（`cli.py` 在并行改动，禁改），若读时自动把 v1 复制到 v2，CLI 之后再改 v1 的值
  就会与 v2 旧副本"值不同" → 每次读都变冲突。等 CLI 切到 resolver（下一步）后再打开默认迁移。
- **executor 的 `vault://`** 已改走 resolver：冲突/读取失败 → `ActionError`
  （`vault_secret_conflict` / `vault_read_failed`）显式拒绝执行，不再静默跳过。
- **CLI 兼容读**：v1 `Vault.get()` 在 v1 缺失时按需回退读 v2（`ACTUS_VAULT_RESOLVER=0` 可关），
  因此 resolver/v2 写入的密钥，现有 `actus vault get` 也能读到 —— **CLI 写入路径不变**，
  切换 CLI 写入口（让它也写 v2）仍需 cmd-engine 协调（`cli.py` 禁改）。


## 1. 现状：两套并存，入口各自为政

| 维度 | `vault.py`（v1） | `vault2.py`（v2） |
|---|---|---|
| 谁在用 | **CLI `actus vault`**（`cli.py:1181`）、**MCP vault 工具**（`mcp_server.py:1617/1632/1647/1659`）、`executor` 的 gated 密钥查找（`executor.py:865` 走 `vault.get_key`） | **仅 `executor`** 的 `vault://` 引用解析：`executor.py:1068-1076` 调 `vault2.auth()` + `vault2.resolve_vault_refs()` |
| 存储 | `_meta/vault/keys.json` + `meta.json`（JSON 文件；`_save()` 直接 `open(...,'w')` 覆盖写） | `<vault_dir>/vault2.db`（SQLite）+ `audit.log`；默认目录已从 cwd 迁到 `~/.actus/vault2`（第 9 轮） |
| 密钥保护 | `ACTUS_VAULT_KEY` 环境变量；**未设置时自动生成一次性随机密钥**（`secrets.token_hex`，写回 `os.environ`，标记 `ephemeral_key`） | 每身份 PIN + TOTP（L2/L3），`seed_key` 经 keyring / passphrase / file-key 派生 KEK 后**加密落库**（第 9 轮实施），无明文 |
| 能力 | scope 分区、get/set/delete/list、`resolve_secrets` | 身份 + 机器绑定、失败锁定、动态码防重放、行级算法敏捷、轮换 + 回滚备份、审计日志、异常检测 |
| 风险 | **临时密钥陷阱**：未配 `ACTUS_VAULT_KEY` 时进程重启即解不开旧密文（`ephemeral_key` 有标记但没有产品路径在写盘前阻断/告警）；`_save` 非原子，半截 JSON 会让整库不可读 | 需要身份/PIN 流程，CLI/MCP 无入口；`cleanup_rotated_backups` / `audit_log` 无产品调用（死方法） |

## 2. 核心问题（为什么必须合并）

1. **同一份配置存在两套语义**：动作 `secrets:` 里 `vault://` 引用走 v2（要身份 auth），而 gated 密钥和 CLI/MCP 的 `vault get/set` 走 v1（要 `ACTUS_VAULT_KEY`）—— 用户面对的"vault"其实是两个库，密钥不互通，错误提示也不一致。
2. **v1 的临时密钥是静默数据丢失**：当 `ACTUS_VAULT_KEY` 未设置时，写进去的密文只在该进程内可解；MCP server 重启后 `get` 返回 None（被当作"没有这个密钥"），用户没有任何"你的密钥是临时的"的强提示。
3. **v2 的能力没有被用户看见**：keyring 硬化、轮换/备份、审计日志都只有 `executor` 的 vault-ref 路径能用；`actus vault rotate` 之类命令不存在。
4. v1 的非原子 `_save` 与 v2 的原子写（tmp + `os.replace`）是两套可靠性标准，前者在崩溃时可能留下半截 `keys.json`。

## 3. 合并建议（分三步，不一次性切换）

**步骤 1（✅ 已实施：低风险，先收口"错误语义"）**
- v1 在 `Vault.__init__` 生成临时密钥时**打 warning 并返回结构化提示**（或直接拒绝写，除非显式 `ACTUS_VAULT_ALLOW_EPHEMERAL=1`）；
- v1 的 `_save` 改为 tmp + `os.replace`（与 v2 同一标准）。

**步骤 2（✅ 已实施：统一读路径，保留写兼容）**
- `executor` 的 gated 密钥查找（`vault.get_key`）与 `vault://`（`vault2.auth/resolve`）**统一到同一个"secret resolver"**：优先 v2（有身份/审计），v1 仅作兼容读；读不到时给出**统一错误码**（`secret_not_found` / `vault_locked` 区分）。
- CLI/MCP 的 `vault get/set` 先保留 v1 行为，但输出里标明当前读的是 v1 库（迁移期可见）。

**步骤 3（⏳ 读侧统一已实施；CLI 写入口切换待 cmd-engine 协调）**
- 提供 `actus vault migrate-v2`：读 v1 `keys.json` → 用 v2 的身份密钥重新加密写入 `vault2.db`（**逐条、可回滚**，迁移失败不改动原库）；迁移后 v1 只读保留一个版本周期。
- 切换后 CLI/MCP vault 命令直连 v2；删除 v1（或降级为"legacy import 模块"）。
- 在此之前，**不要再往 v1 增加能力**（避免合并面继续扩大）。

## 4. 不建议的做法

- 不要"复制 v2 代码到 v1"或反之：两套加密/存储语义会永久分叉；
- 不要在没有迁移工具的情况下直接让 CLI/MCP 切 v2：现有 v1 用户数据会瞬间"消失"（读不到）；
- 不要删除 v1 的 `ephemeral_key` 标记逻辑而不加告警：那正是当前静默丢数据的来源。

## 5. 与预期收益

合并后：一个库、一套错误码、一套密钥保护（keyring/passphrase）、CLI/MCP/executor 同源；
v2 的审计和轮换能力对用户可见；v1 的临时密钥陷阱被消除。
代价：需要一个迁移命令和一个只读过渡周期（约 1-2 个迭代）。
