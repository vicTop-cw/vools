# vault2 密钥库加固设计决策（L1 无第二因子问题）

> 状态：**已决定**（2026-10-28，第 8 轮安全审计产出）
> 适用模块：`actus/vools/actus/vault2.py`
> 结论先说：**本轮做"最小加固"，长期方案选「外置 passphrase / OS keyring 二选一，以 keyring 为默认候选」。**
> 详见文末 §5。

## 1. 现状与已实测的风险

审计时用隔离目录复现（不碰真实 `~/.actus`），以下三条是**实测**而非推断：

1. **库文件与密钥材料同库**：`identities` 表里 `seed_key`（TEXT）与 `key_salt`（TEXT）都是明文；
   `master_key = PBKDF2(seed_key, dynamic_code, key_salt)`，L1 身份的 `dynamic_code` 为空串。
   ⇒ **只拿到 `vault2.db` 文件、不知道 PIN、不登录**，就能派生出 `master_key` → 行级 `row_key` → 解出明文。
   实测：解密出 `'sk-SUPER-SECRET-123'`。
2. **旧默认目录是进程 cwd**：改前 `DEFAULT_VAULT_DIR = os.getcwd()/_meta/vault`（import 时绑定）——
   在哪个仓库里运行，密钥库就落在那个仓库的 `_meta/vault/`（极易被 git/同步盘/打包带走）。
   本轮已改为 `~/.actus/vault2/`（可用 `ACTUS_VAULT2_DIR` 覆盖）并做旧位置自动迁移。
3. **无文件权限加固**：改前全模块无 `chmod`，实测 db 权限位 `0o666`。
   本轮已加目录 `0700` / 库与审计文件 `0600`（best-effort，POSIX 生效）。

**L1 的真实威胁模型**：L1 = "无动态码的第二层"。PIN 只用于 `auth` 取 session，
**不参与 master_key 派生** —— 所以 PIN 强度（6 位数字）对"库文件泄露"这个威胁**完全无缓解作用**。
L2/L3 多一道 TOTP，但 `seed_key` 也在库里，**拿到库 + 能读时钟就能自算动态码**；
真正的差别只剩"攻击者是否必须在本机/是否触发 used_codes 防重放"。

## 2. 候选方案

| # | 方案 | 做法 | 跨平台可行性 | 迁移成本 | 离线可用 |
|---|---|---|---|---|---|
| A | **OS keyring**（`keyring` 库 → macOS Keychain / Windows Credential Manager / Linux Secret Service） | 把 `seed_key` 用 keyring 封装；库里只留 `keyring_ref` + 密文 | mac/Windows/Linux 桌面均可；**无头 Linux（CI/容器）常无 Secret Service**，需文件后端兜底 | 中：新增可选依赖 + 无 keyring 时的降级策略 + 迁移旧库 | 是（密钥在本地） |
| B | **DPAPI**（Windows Data Protection API，`CryptProtectData`） | `seed_key` 用当前用户 DPAPI 封装后落库/落旁路文件 | **仅 Windows**；对 mac/Linux 需另配方案（等于 A+C 双实现） | 中低（单平台） | 是（绑定当前用户） |
| C | **外置 passphrase**（用户额外输入一个高熵口令，PBKDF2/Argon2 派生 KEK 封装 seed_key） | 库启动时要求 `VAULT2_PASSPHRASE` 或交互输入；无 passphrase 则拒绝解密（fail-closed） | 全平台，零依赖；CI 里可用环境变量/secret 注入 | 中：多一次输入/环境变量约定；忘记 passphrase = 库不可恢复 | 是 |
| D | 硬件（TPM/HSM/安全芯片） | 密钥不出芯片 | 平台差异极大、驱动/权限复杂 | 高 | 视实现 |

## 3. 评估维度（按本项目的实际约束）

- **本项目要跑在**：Windows 桌面（主）、Linux（WSL/CI）、macOS（少量）；MCP server / CLI / 动作执行都可能**无交互**运行。
- **无交互场景**（AI 调用、CI、MCP tool）决定了：
  - 方案 C（passphrase）在无人值守时必须靠环境变量注入 → 与"库文件泄露"的威胁模型只差一步（环境变量也会进日志/进程表）；
  - 方案 A 的 keyring 在无头 Linux 上不可用 → 必须有降级；
  - 方案 B 只覆盖 Windows。
- **迁移成本**：现有库 `_meta/vault` → 新位置已经在本轮做了目录级迁移；若再加"密钥再封装"，需要
  一次性把 `seed_key` 用新 KEK 重封装（读旧库 → 解 seed_key → 封装 → 写回），属于**可控的一次性迁移**。

## 4. 推荐执行路径（分两步，不一次做完）

**步骤 1（本轮已做，最小加固）**
- 默认目录迁到 `~/.actus/vault2/` + `0700/0600` 权限；
- `status()` 在存在 L1 身份时给出明确告警（"L1 无第二因子：拿到 db 即可解出全部 secrets，建议升级 L2/L3"）；
- 文档（本文件）把风险与决策写清；
- **不改密钥派生算法**（避免破坏现有库可解性）。

**步骤 2（下一轮设计落地，推荐 A 为主 + C 为无头兜底）**
1. 抽象 `KeyUnwrap` 接口：`wrap(seed_key) -> envelope` / `unwrap(envelope) -> seed_key`。
2. **默认实现 = OS keyring**（`keyring` 作为可选依赖）：
   - Windows → Credential Manager；macOS → Keychain；Linux 桌面 → Secret Service；
   - **keyring 不可用时**（无头 CI/容器/无 DBus）→ 要求 `ACTUS_VAULT2_PASSPHRASE`（方案 C），
     两者都不可用 → **拒绝打开库并明确报错**（fail-closed，不降级成明文/弱封装）。
3. 库结构加 `key_envelope`（JSON：`{"kind":"keyring","ref":...}` 或 `{"kind":"passphrase","salt":...,"kdf":"argon2id",...}`），
   `seed_key` 字段在迁移后只存密文。
4. 迁移：读到旧格式（`seed_key` 明文）→ 成功 auth 一次时用当前 KEK 封装并写回（与既有 lazy migrate 同策略），
   迁移失败必须**显式报错**（不能静默保留明文；应提示用户手动执行 `vault2 migrate-key`）。
5. 兼容：`status()` 增 `key_protection` 字段（`none` / `keyring` / `passphrase`），让消费方知道当前保护等级。

## 5. 结论（决策）

1. **本轮不做** keyring/DPAPI/TPM 封装 —— 它们跨平台差异大、需要无头降级策略，
   属于独立设计项目；本轮只做"目录/权限/告警/文档"这四项最小加固。
2. **下一轮首选方案 A（OS keyring）+ 方案 C（外置 passphrase）作为无头兜底**，理由：
   - A 是唯一"密钥不落在用户可见文件系统里"的跨平台主流方案，且无需用户每次输入；
   - C 是唯一"零依赖、全平台、CI 可用"的方案，正好补 A 在无头环境的缺口；
   - B（DPAPI）只在 Windows 可用，会迫使同一功能有三套实现，**不选**；
   - D（TPM/HSM）成本过高，作为未来高安全档位预留，**不作为默认**。
3. **不做"静默降级"**：keyring 与 passphrase 都不可用时必须拒绝打开库（fail-closed），
   绝不回退到"明文 seed_key"或"固定密钥"。
4. **L1 的定位要在文档与告警里说清**：L1 = "本机可用性优先、不含第二因子"，
   只适合低价值凭据；高价值密钥必须用 L2/L3。

## 6. 验收口径（步骤 2 完成后应满足）

- `vault2.db` 泄露给其他用户/被提交进仓库时，**无法**在没有 keyring/passphrase 的情况下解出任何 secret；
- 无头 CI 用 `ACTUS_VAULT2_PASSPHRASE` 可正常 auth/读写（有自动化测试）；
- 两种 KEK 都不可用时，`Vault2()` 拒绝打开并给出可操作的错误信息；
- `status()` 的 `key_protection` 字段能反映当前保护等级。
