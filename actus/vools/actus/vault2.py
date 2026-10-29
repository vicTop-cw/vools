"""vools/actus/vault2.py —— Vault 安全凭证管理引擎（Phase 1.5：行级算法敏捷 + 密钥隔离）。

基于 vools.security.otp 动态码算法 + SQLite 存储 + 多级密钥派生。

存储位置: _meta/vault/vault2.db
审计日志: _meta/vault/audit.log（JSON Lines）

API:
    Vault2.register(...)   → 注册身份+机器
    Vault2.auth(...)       → 认证，返回 session_token（含 master_key）
    Vault2.get_secret(...) → 读取凭证（需 token）
    Vault2.set_secret(...) → 写入凭证（需 token）
    Vault2.list_secrets(...) → 列凭证名（脱敏）
    Vault2.audit_log(...)  → 查审计日志

便捷函数:
    from vools.actus.vault2 import get_secret, set_secret

> 2026-10-13（docs/39 §9 / docs/45 S2）：本模块从 `engine/actuscore/vault2.py`
> 上移到 vools 成为单一真源，Actus 侧改为 re-export shim。
> 它只依赖标准库 + `vools.security.otp`，没有反向依赖 Actus，所以能安全上移。
"""

import base64
import contextlib
import getpass
import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import struct
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# ── 复用 vools 动态码算法（带本地回退） ──
try:
    from vools.security.otp import (
        generate_dynamic_code,
        verify_dynamic_code,
        derive_master_key,
        generate_seed_key,
    )
except ImportError:
    import struct as _struct

    def generate_dynamic_code(seed_key: bytes, time_step: int = 60, digits: int = 6) -> str:
        counter = int(time.time()) // time_step
        msg = _struct.pack(">Q", counter)
        digest = hmac.new(seed_key, msg, hashlib.sha256).digest()
        offset = digest[-1] & 0x0F
        code = _struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(code % (10 ** digits)).zfill(digits)

    def verify_dynamic_code(code, seed_key, time_step=60, window=1, used_codes=None):
        if not code or not code.isdigit() or len(code) != 6:
            return False
        current = int(time.time()) // time_step
        for off in range(-window, window + 1):
            msg = _struct.pack(">Q", current + off)
            digest = hmac.new(seed_key, msg, hashlib.sha256).digest()
            offset = digest[-1] & 0x0F
            expected = str(
                (_struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF)
                % (10 ** len(code))
            ).zfill(len(code))
            if hmac.compare_digest(code, expected):
                if used_codes is not None:
                    used_codes.add(code)
                return True
        return False

    def derive_master_key(pin, dynamic_code, salt, iterations=100000, dklen=32):
        return hashlib.pbkdf2_hmac(
            "sha256", (pin + dynamic_code).encode("utf-8"), salt, iterations, dklen
        )

    def generate_seed_key(length=32):
        return secrets.token_bytes(length)


# ── 常量 ──
#
# 审计修复（P1）：改前 `DEFAULT_VAULT_DIR = os.path.join(os.getcwd(), "_meta", "vault")`
# —— **import 时绑定进程 cwd**，于是"在哪个目录跑 actus，密钥库就落在哪个目录的
# `_meta/vault/`"，实测干净子进程里 db 直接创建在 cwd 下（0o666，无 chmod）。
# 后果：密钥库 + `seed_key` 进当前项目目录（极易被 git 提交 / 同步盘 / 打包带走）。
# 现在默认与 vault.py 对齐到 `~/.actus/vault2/`，可用 ACTUS_VAULT2_DIR 覆盖；
# 旧位置的库由 `_maybe_migrate_legacy()` 自动迁移（见下）。DEFAULT_VAULT_DIR 仍保留
# 作为"默认值快照"，运行时一律走 `default_vault_dir()`（让 env 覆盖与 cwd 无关）。
def default_vault_dir() -> str:
    """默认密钥库目录：`~/.actus/vault2`（可用 ACTUS_VAULT2_DIR 覆盖）。"""
    override = (os.environ.get("ACTUS_VAULT2_DIR") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser("~"), ".actus", "vault2")


DEFAULT_VAULT_DIR = default_vault_dir()      # 兼容旧引用（常量仅是快照）
LEGACY_VAULT_SUBDIR = os.path.join("_meta", "vault")   # 旧位置：<cwd>/_meta/vault
DEFAULT_TIME_STEP = 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 900
SESSION_TTL = {"L1": 900, "L2": 600, "L3": 300}

# 行级密钥派生默认参数（master_key 已是高熵，无需 10 万轮）
DEFAULT_ROW_ITERS = 1000
DEFAULT_ROW_DKLEN = 32
DEFAULT_CIPHER_ALG = "fernet"
CIPHER_ALG_WHITELIST = {"fernet", "xor-hmac"}  # aes-gcm 后续加入


# ── 密钥保护：seed_key 不再明文落库（docs/vault2-hardening.md 的实施）────────
#
# 无论哪种保护方式，`identities.seed_key` 列里都只存 `enc:v1:<fernet 密文>`
# （Fernet KEK 来自 keyring / passphrase / 随库密钥文件），因此**攻击者只拿到
# vault2.db 文件解不出任何 secrets**。
#
# 三种保护方式（可用 ACTUS_VAULT2_KEY_PROTECTION 强制指定）：
#   keyring     OS 凭据库：Windows Credential Manager / macOS Keychain /
#               Linux Secret Service（可选依赖 `pip install vools-actus[keyring]`）
#   passphrase  外置口令：ACTUS_VAULT2_PASSPHRASE 或交互式输入（无头环境兜底）
#   file-key    随库密钥文件（0600）：显式传 vault_dir 的嵌入式/测试用法
#
# 保护方式解析顺序（fail-closed，**绝不退回明文**）：
#   1) 设置了 ACTUS_VAULT2_PASSPHRASE → passphrase
#   2) 强制 ACTUS_VAULT2_KEY_PROTECTION=keyring|passphrase|file-key
#   3) 显式 vault_dir（嵌入式）→ file-key（并会在 status() 里说明其边界）
#   4) 默认目录（~/.actus/vault2）→ keyring；keyring 不可用 → 拒绝打开并给排查指引
KEYRING_SERVICE = "vools-actus-vault2"
PASSPHRASE_ENV = "ACTUS_VAULT2_PASSPHRASE"
PROTECTION_ENV = "ACTUS_VAULT2_KEY_PROTECTION"
NO_PROMPT_ENV = "ACTUS_VAULT2_NO_PROMPT"
FILE_KEY_NAME = ".vault2.key"
ENVELOPE_PREFIX = "enc:v1:"
PASSPHRASE_ITERS = 200000
PROTECTION_KEYRING = "keyring"
PROTECTION_PASSPHRASE = "passphrase"
PROTECTION_FILE = "file-key"
PROTECTION_LEGACY = "legacy-plaintext"
PROTECTION_UNAVAILABLE = "unavailable"
PROTECTION_KINDS = (PROTECTION_KEYRING, PROTECTION_PASSPHRASE, PROTECTION_FILE)


class Vault2KeyProtectionError(RuntimeError):
    """密钥保护不可用 / 迁移失败。**fail-closed**：绝不退回明文存储。"""

    code = "vault_key_protection_unavailable"


#: keyring 探测结果缓存：(module_or_None, reason_or_None)。进程内只探一次。
_KEYRING_PROBE_CACHE = None


def probe_keyring():
    """探测 OS keyring 是否**真的可用**（懒导入 + 写/读/删探针）。

    只看 `import keyring` 不够：无桌面会话 / 容器 / 无 Secret Service 时，
    keyring 会装出一个 `fail`（或 `null`）后端，任何读写都抛 NoKeyringError；
    还有"能写不能读"的异常后端。所以这里实打实写一条探针再读回。

    Returns:
        (module_or_None, reason_or_None)。不可用时 reason 是给人看的原因。
    """
    global _KEYRING_PROBE_CACHE
    if _KEYRING_PROBE_CACHE is not None:
        return _KEYRING_PROBE_CACHE
    try:
        import keyring
    except Exception as exc:      # ImportError / 依赖损坏
        _KEYRING_PROBE_CACHE = (None, "未安装 keyring（pip install keyring）：%s" % exc)
        return _KEYRING_PROBE_CACHE
    try:
        backend = keyring.get_keyring()
        module_name = type(backend).__module__
        if module_name.endswith(".fail") or module_name.endswith(".null"):
            _KEYRING_PROBE_CACHE = (
                None,
                "系统没有可用的 keyring 后端（无桌面会话/容器/未装 Secret Service？）：%s"
                % type(backend).__name__)
            return _KEYRING_PROBE_CACHE
        probe_user = "__probe__" + uuid.uuid4().hex
        probe_value = secrets.token_urlsafe(8)
        keyring.set_password(KEYRING_SERVICE, probe_user, probe_value)
        ok = keyring.get_password(KEYRING_SERVICE, probe_user) == probe_value
        try:
            keyring.delete_password(KEYRING_SERVICE, probe_user)
        except Exception:
            pass
        if not ok:
            _KEYRING_PROBE_CACHE = (None, "keyring 写入后读不回（后端异常），不能作为可信存储")
            return _KEYRING_PROBE_CACHE
        _KEYRING_PROBE_CACHE = (keyring, None)
    except Exception as exc:
        _KEYRING_PROBE_CACHE = (
            None, "keyring 不可用（%s: %s）" % (type(exc).__name__, exc))
    return _KEYRING_PROBE_CACHE


def _key_protection_unavailable_message(reason):
    """fail-closed 时的可读报错（含三种可操作的解决路径）。"""
    return (
        "vault2 无法安全保护 seed_key，已拒绝打开密钥库（fail-closed，绝不退回明文）\n"
        "原因：%s\n"
        "任选其一后重试：\n"
        "  1) 安装/启用 OS keyring：pip install keyring（桌面会话自动使用 "
        "Credential Manager / Keychain / Secret Service）\n"
        "  2) 无头环境设置外置口令：export %s='<你的口令>'\n"
        "  3) 显式指定保护方式：%s=keyring|passphrase|file-key\n"
        "现有库不会丢：配置好保护方式后首次打开会自动迁移（seed_key 明文会被清除）。"
        % (reason, PASSPHRASE_ENV, PROTECTION_ENV))


# ── 加密后端 ──
class _FernetBackend:
    alg_name = "fernet"

    def __init__(self, row_key: bytes):
        from cryptography.fernet import Fernet
        import base64
        fernet_key = base64.urlsafe_b64encode(row_key)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


class _XorHmacBackend:
    alg_name = "xor-hmac"

    def __init__(self, row_key: bytes):
        self._key = row_key

    def encrypt(self, plaintext: str) -> str:
        data = plaintext.encode("utf-8")
        nonce = secrets.token_bytes(16)
        key_stream = self._generate_key_stream(nonce, len(data))
        encrypted = bytes(a ^ b for a, b in zip(data, key_stream))
        mac = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        packed = nonce + mac + encrypted
        import base64
        return "xor:" + base64.b64encode(packed).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        import base64
        if ciphertext.startswith("xor:"):
            ciphertext = ciphertext[4:]
        packed = base64.b64decode(ciphertext)
        nonce, mac, encrypted = packed[:16], packed[16:48], packed[48:]
        expected_mac = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("Vault2 解密失败：HMAC 不匹配")
        key_stream = self._generate_key_stream(nonce, len(encrypted))
        decrypted = bytes(a ^ b for a, b in zip(encrypted, key_stream))
        return decrypted.decode("utf-8")

    def _generate_key_stream(self, nonce: bytes, length: int) -> bytes:
        stream = b""
        counter = 0
        while len(stream) < length:
            block = hashlib.sha256(self._key + nonce + struct.pack(">I", counter)).digest()
            stream += block
            counter += 1
        return stream[:length]


_BACKENDS = {
    "fernet": _FernetBackend,
    "xor-hmac": _XorHmacBackend,
}


def _derive_row_key(
    master_key: bytes,
    row_salt: bytes,
    iters: int = DEFAULT_ROW_ITERS,
    dklen: int = DEFAULT_ROW_DKLEN,
) -> bytes:
    """从身份级 master_key 派生出行级 row_key。

    master_key 本身已是高熵（PBKDF2 100k 轮 + PIN + dynamic_code），
    所以行级派生只需 1000 轮，兼顾安全与性能。
    """
    return hashlib.pbkdf2_hmac("sha256", master_key, row_salt, iters, dklen)


def _make_backend(cipher_alg: str, row_key: bytes):
    if cipher_alg not in CIPHER_ALG_WHITELIST:
        raise ValueError(f"不支持的加密算法: {cipher_alg}（白名单: {CIPHER_ALG_WHITELIST}）")
    cls = _BACKENDS[cipher_alg]
    return cls(row_key)


# ── 主密钥派生（P0 修复，第 15 轮）────────────────────────────────────────
#
# 事故：改前 `master_key = PBKDF2(seed_key_hex + dynamic_code, key_salt)`，而
# `dynamic_code` 是**每 60 秒变一次**的 TOTP ⇒ master_key 每分钟都不一样 ⇒
# 在窗口 A 写入的 secrets，到窗口 B 重新 auth 后用新 master 解 = **解不开**。
# L1 因为 effective_dynamic 本来就是空串而幸免；**L2/L3 全中**，而 register()
# 的默认级别正是 L2。所有测试都在同一个 60s 窗口内跑完，所以 14 轮全绿。
#
# 修复：master 只由 `seed_key + key_salt` 决定（与时间无关）；动态码退回本职 ——
# **只做认证挑战**（TOTP 校验 + used_codes 防重放），不再参与 KDF。
# 旧数据用 `created_at` 反推写入窗口 → 重建当时的 master 解密 → 用新派生重加密。

def derive_master_key_stable(seed_or_pin: str, salt: bytes) -> bytes:
    """稳定派生：**不掺时间**。动态码不再参与 KDF（P0 修复）。"""
    return derive_master_key(seed_or_pin, "", salt)


def derive_master_key_windowed(seed_or_pin: str, window_counter: int, salt: bytes) -> bytes:
    """旧派生：把**指定时间窗口**的 TOTP 掺进 KDF。

    仅用于**迁移旧密文**：每条 secret 有 `created_at`，`created_at // 60` 就是它
    被写入时的窗口计数器 —— 用它就能重建当时的 master_key。
    """
    import struct as _struct
    counter = int(window_counter)
    digest = hmac.new(bytes.fromhex(seed_or_pin) if _is_hex(seed_or_pin)
                      else seed_or_pin.encode('utf-8'),
                      _struct.pack(">Q", counter), hashlib.sha256).digest()
    offset = digest[-1] & 0x0F
    code = (_struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** 6)
    return derive_master_key(seed_or_pin, str(code).zfill(6), salt)


def _is_hex(value) -> bool:
    try:
        bytes.fromhex(value)
        return True
    except (TypeError, ValueError):
        return False


# ── KEK 代数（docs/vault2-kek-rotation.md §4.4 第 0 步）───────────────────
#
# 为什么放 `key_meta` JSON 而不新增 DB 列：
#   * `key_meta` 本来就是"这个身份的 seed 信封由什么保护"的元数据（passphrase 的
#     salt/iters 就在这里），代数标记同属该语义，放一起不用第二套迁移机制；
#   * 加列要 ALTER TABLE + 兼容旧库（我们已经有 `_ensure_identity_key_columns`
#     一条迁移路径，不再为"一个整数"开第二条）；
#   * 三种保护模式（keyring/file-key 目前 key_meta 为 NULL）都自然落到"缺省 0"，
#     将来轮换时各自把 `kek_gen` 写进去即可。
#
# **向后兼容**：现有库没有这个字段 → 一律视为 `kek_gen = 0`（不迁移、不回填）。
# 注意 dissent：设计文档 §4.2/§4.4 曾写"旧行按 1 回填"，与 lead 本轮要求（0）冲突，
# 按 lead 要求统一为 0，文档已同步改写。

KEK_GEN_FIELD = "kek_gen"
KEK_GEN_DEFAULT = 0


def kek_gen_of_meta(key_meta) -> int:
    """从 `key_meta` JSON 读出 `kek_gen`；缺失/损坏/非整数 → 0（向后兼容）。"""
    if not key_meta:
        return KEK_GEN_DEFAULT
    try:
        meta = json.loads(key_meta)
    except (TypeError, ValueError):
        return KEK_GEN_DEFAULT
    if not isinstance(meta, dict):
        return KEK_GEN_DEFAULT
    value = meta.get(KEK_GEN_FIELD, KEK_GEN_DEFAULT)
    try:
        return int(value)
    except (TypeError, ValueError):
        return KEK_GEN_DEFAULT


# ── Vault2 ──
class Vault2:
    def __init__(self, vault_dir: str = None, migrate_legacy: bool = None):
        """**懒创建**：构造只算路径 + 默认值，**零文件系统操作**。

        改前 `__init__` 做四件写事（迁移旧库/`makedirs`/chmod/建库建表 + 密钥保护三连），
        于是"看一眼密钥库"（`status()`、只读诊断、`resolver_status()`、甚至只是
        `Vault2()` 拿路径）都会**凭空建库** —— 真实事故里 3 次把空
        `~/.actus/vault2/vault2.db` 写进用户目录。

        现在：所有写动作收敛到 `_ensure_ready()`（幂等），只有**写路径**调它；
        读路径遇到"库不存在"按「**库不存在 = 没有密钥**」处理，绝不建库。
        """
        explicit = vault_dir is not None
        self._explicit_dir = explicit
        self.vault_dir = os.path.abspath(vault_dir or default_vault_dir())
        self.db_path = os.path.join(self.vault_dir, "vault2.db")
        self.audit_path = os.path.join(self.vault_dir, "audit.log")
        # 迁移状态（status() 会如实回报；None = 无需迁移）
        self.migrated_from: Optional[str] = None
        self.migration_conflict: Optional[str] = None
        # migrate_legacy: None=自动（写路径首次 ready 时尝试）/ True=允许 / False=禁止
        self.migrate_legacy = migrate_legacy
        self._sessions: Dict[str, dict] = {}
        self._audit_mode_set = False
        # ── seed_key 保护（docs/vault2-hardening.md）──
        self.key_protection: str = PROTECTION_UNAVAILABLE
        self.key_protection_warning: Optional[str] = None
        self.migrated_key_protection: int = 0
        self._passphrase: Optional[str] = None
        self._keyring = None
        self._file_key_cached: Optional[bytes] = None
        self._ready = False

    # ── 懒创建 ────────────────────────────────────────────────────────
    def _exists(self) -> bool:
        """库文件是否存在（纯 stat，不建任何东西）。"""
        return os.path.isfile(self.db_path)

    def _ensure_ready(self) -> "Vault2":
        """幂等地完成所有**写侧**初始化（迁移 → makedirs → chmod → 建库 → 密钥保护）。

        **只有写路径可以调它**。读路径一律走 `_exists()` 判断，不调本方法 ——
        否则"读一下就建库"的历史问题会回来。
        """
        if self._ready:
            return self
        if not self._explicit_dir and self.migrate_legacy is not False:
            self._maybe_migrate_legacy()
        os.makedirs(self.vault_dir, exist_ok=True)
        self._harden_permissions()
        self._init_schema()
        self._harden_permissions()
        self._ensure_identity_key_columns()
        self._resolve_key_protection()
        self._check_existing_key_protection()
        self._migrate_key_protection()
        self._ready = True
        return self

    def _maybe_migrate_legacy(self) -> None:
        """把旧位置（`<cwd>/_meta/vault`）的库迁到新位置（**移动**，不复制）。

        规则（lead 裁决）：
          * 旧有 / 新无（或新目录为空）→ 自动迁移（shutil.move），记 `migrated_from`；
          * 两边都有 → **不合并**，记 `migration_conflict`（ambiguous），让人处理；
          * 显式传了 vault_dir → 完全不做迁移（调用方自己负责）。
        迁移失败不静默：写进 `migration_conflict`，status() 可见。
        """
        legacy = os.path.abspath(os.path.join(os.getcwd(), LEGACY_VAULT_SUBDIR))
        if not os.path.isdir(legacy):
            return
        if legacy == self.vault_dir:
            return
        new_exists = os.path.isdir(self.vault_dir) and bool(os.listdir(self.vault_dir))
        if new_exists:
            self.migration_conflict = (
                "ambiguous: 新旧密钥库同时存在，未自动合并"
                "（旧=%s，新=%s）—— 请人工确认保留哪一份" % (legacy, self.vault_dir))
            return
        try:
            parent = os.path.dirname(self.vault_dir)
            if parent:
                os.makedirs(parent, exist_ok=True)
            if os.path.isdir(self.vault_dir):
                os.rmdir(self.vault_dir)          # 空目录：让 move 直接落位
            shutil.move(legacy, self.vault_dir)    # 移动（不是复制）
            self.migrated_from = legacy
        except OSError as exc:
            self.migration_conflict = (
                "move_failed: 旧密钥库迁移失败（%s: %s），仍使用新位置 %s"
                % (type(exc).__name__, exc, self.vault_dir))

    def _harden_permissions(self) -> None:
        """密钥库目录 0700 / 库与审计文件 0600（POSIX 生效；Windows 尽力而为）。

        审计修复（L1 加固配套）：改前全模块无任何 chmod，实测 db 权限位 0o666。
        这里对目录/已知文件做 best-effort chmod；失败不抛（可能是 Windows/smb）。
        """
        targets = ((self.vault_dir, 0o700), (self.db_path, 0o600),
                   (self.audit_path, 0o600))
        for path, mode in targets:
            if not os.path.exists(path):
                continue
            try:
                os.chmod(path, mode)
            except OSError:
                pass

    # ── seed_key 保护（keyring / passphrase / file-key）────────────────────

    def _ensure_identity_key_columns(self) -> None:
        """老库补列 `key_protection` / `key_meta`（不动既有列，向后兼容）。"""
        with self._db() as conn:
            columns = {row[1] for row in
                       conn.execute("PRAGMA table_info(identities)").fetchall()}
            for name in ("key_protection", "key_meta"):
                if name not in columns:
                    conn.execute("ALTER TABLE identities ADD COLUMN %s TEXT" % name)

    def _prompt_passphrase(self) -> Optional[str]:
        """交互式取口令（仅在真终端；`ACTUS_VAULT2_NO_PROMPT` 可禁用）。"""
        if os.environ.get(NO_PROMPT_ENV):
            return None
        try:
            if not sys.stdin or not sys.stdin.isatty():
                return None
        except Exception:
            return None
        try:
            value = getpass.getpass("vault2 口令（%s）: " % PASSPHRASE_ENV)
        except (EOFError, KeyboardInterrupt):
            return None
        return value.strip() or None

    def _resolve_key_protection(self) -> None:
        """决定本次会话用哪种方式保护 seed_key（fail-closed）。"""
        forced = (os.environ.get(PROTECTION_ENV) or "").strip().lower()
        if forced and forced not in PROTECTION_KINDS:
            raise Vault2KeyProtectionError(
                "%s=%r 非法（可选：%s）"
                % (PROTECTION_ENV, forced, ", ".join(PROTECTION_KINDS)))
        passphrase = (os.environ.get(PASSPHRASE_ENV) or "").strip() or None
        if not passphrase and forced in (None, PROTECTION_PASSPHRASE):
            # 无头环境只认环境变量；有真终端时允许交互输入（仅 passphrase 模式）
            passphrase = self._prompt_passphrase()
        if passphrase and forced != PROTECTION_KEYRING:
            self.key_protection = PROTECTION_PASSPHRASE
            self._passphrase = passphrase
            return
        if forced == PROTECTION_PASSPHRASE:
            raise Vault2KeyProtectionError(
                "要求 passphrase 保护但没有口令：请设置 %s（或交互式运行）" % PASSPHRASE_ENV)
        if forced == PROTECTION_KEYRING:
            module, reason = probe_keyring()
            if module is None:
                raise Vault2KeyProtectionError(_key_protection_unavailable_message(reason))
            self.key_protection = PROTECTION_KEYRING
            self._keyring = module
            return
        if forced == PROTECTION_FILE:
            self.key_protection = PROTECTION_FILE
            return
        if self._explicit_dir:
            # 调用方自管目录（嵌入式/测试）：用随库密钥文件，避免污染 OS 凭据库，
            # 也避免 CI 里"没有 keyring 就全红"。边界写进 status().key_protection_warning。
            self.key_protection = PROTECTION_FILE
            self.key_protection_warning = (
                "file-key 模式（显式 vault_dir）：密钥文件与库同目录（0600）。"
                "单独泄露 vault2.db 不足以解密，但能同时读到该目录的用户仍可解密；"
                "需要 OS 级隔离请用默认目录（~/.actus/vault2）、设置 %s 或 %s=keyring"
                % (PASSPHRASE_ENV, PROTECTION_ENV))
            return
        module, reason = probe_keyring()
        if module is None:
            raise Vault2KeyProtectionError(_key_protection_unavailable_message(reason))
        self.key_protection = PROTECTION_KEYRING
        self._keyring = module

    def _check_existing_key_protection(self) -> None:
        """库里已有受保护身份时，本次解析到的保护方式必须一致（否则解不开）。"""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT key_protection FROM identities "
                "WHERE key_protection IS NOT NULL AND key_protection != ''").fetchall()
        existing = sorted({row[0] for row in rows if row[0] in PROTECTION_KINDS})
        if existing and self.key_protection not in existing:
            raise Vault2KeyProtectionError(
                "该密钥库用 %s 保护 seed_key，但本次解析到 %s —— 拒绝以错误方式打开。\n"
                "请设置 %s（口令）或卸载/恢复对应 keyring 条目后重试。"
                % ("/".join(existing), self.key_protection, PASSPHRASE_ENV))

    def _file_key(self) -> bytes:
        """随库密钥文件（0600）；首次调用时创建。"""
        if self._file_key_cached is not None:
            return self._file_key_cached
        path = os.path.join(self.vault_dir, FILE_KEY_NAME)
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                raw = handle.read().strip()
            try:
                key = base64.b64decode(raw)
            except Exception:
                raise Vault2KeyProtectionError(
                    "随库密钥文件损坏（base64 解码失败）：%s" % path)
            if len(key) != 32:
                raise Vault2KeyProtectionError(
                    "随库密钥文件长度异常（%d != 32）：%s" % (len(key), path))
            self._file_key_cached = key
            return key
        key = secrets.token_bytes(32)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:      # 并发创建：重读已有文件
            return self._file_key()
        with os.fdopen(fd, "wb") as handle:
            handle.write(base64.b64encode(key))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        self._file_key_cached = key
        return key

    def _kek_for(self, identity_id: str, key_meta: Optional[str]) -> bytes:
        """取该身份的 KEK（keyring 条目 / passphrase 派生 / 随库密钥文件）。"""
        if self.key_protection == PROTECTION_KEYRING:
            stored = self._keyring.get_password(KEYRING_SERVICE, identity_id)
            if not stored:
                raise Vault2KeyProtectionError(
                    "keyring 中找不到身份 %s 的密钥条目（service=%s）—— 换机器/换用户/"
                    "凭据被删除都会这样；请从备份恢复该库或重新注册身份"
                    % (identity_id, KEYRING_SERVICE))
            try:
                kek = base64.b64decode(stored)
            except Exception as exc:
                raise Vault2KeyProtectionError(
                    "keyring 条目损坏（身份 %s）：%s" % (identity_id, exc))
            if len(kek) != 32:
                raise Vault2KeyProtectionError(
                    "keyring 条目长度异常（身份 %s，%d != 32）" % (identity_id, len(kek)))
            return kek
        if self.key_protection == PROTECTION_PASSPHRASE:
            meta = {}
            if key_meta:
                try:
                    meta = json.loads(key_meta)
                except ValueError:
                    raise Vault2KeyProtectionError(
                        "身份 %s 的 key_meta 不是合法 JSON" % identity_id)
            salt_hex = meta.get("salt") or ""
            if not salt_hex:
                raise Vault2KeyProtectionError(
                    "身份 %s 缺少 passphrase 派生盐（key_meta.salt）" % identity_id)
            iters = int(meta.get("iters") or PASSPHRASE_ITERS)
            return hashlib.pbkdf2_hmac(
                "sha256", self._passphrase.encode("utf-8"),
                bytes.fromhex(salt_hex), iters, 32)
        return self._file_key()

    def _encrypt_seed_hex(self, identity_id: str, seed_hex: str):
        """加密 seed_key（hex 字符串），返回 (stored, protection, key_meta)。

        keyring 模式会顺带写入一条 keyring 条目；
        返回的 stored 一定带 `enc:v1:` 前缀（库里永不落明文）。
        """
        if self.key_protection == PROTECTION_KEYRING:
            kek = secrets.token_bytes(32)
            self._keyring.set_password(
                KEYRING_SERVICE, identity_id,
                base64.b64encode(kek).decode("ascii"))
            return (ENVELOPE_PREFIX + _FernetBackend(kek).encrypt(seed_hex),
                    PROTECTION_KEYRING, None)
        if self.key_protection == PROTECTION_PASSPHRASE:
            salt = secrets.token_bytes(16)
            kek = hashlib.pbkdf2_hmac(
                "sha256", self._passphrase.encode("utf-8"), salt, PASSPHRASE_ITERS, 32)
            meta = json.dumps({"kdf": "pbkdf2-sha256", "salt": salt.hex(),
                               "iters": PASSPHRASE_ITERS})
            return (ENVELOPE_PREFIX + _FernetBackend(kek).encrypt(seed_hex),
                    PROTECTION_PASSPHRASE, meta)
        kek = self._file_key()
        return (ENVELOPE_PREFIX + _FernetBackend(kek).encrypt(seed_hex),
                PROTECTION_FILE, None)

    def _reencrypt_seed_envelope(self, identity_id: str, seed_hex: str,
                                 protection: Optional[str],
                                 key_meta: Optional[str], stored_old: str) -> str:
        """把新 seed 用**现有 KEK** 重新封装成信封（不写 keyring / 不换 KEK）。

        为什么不调 `_encrypt_seed_hex`：那个会为 keyring 模式**生成新 KEK 并写 keyring
        条目** —— 那是 DB 事务之外的写，一旦 DB 提交失败就出现"keyring 换了、DB 还是旧
        seed"，旧 seed 再也解不开（不可逆）。轮换只换 seed，KEK 保持原样 ⇒ **全程 DB 内，
        可单事务回滚**。KEK 轮换是另一件事（需要跨 store 的两阶段提交），不在本轮。
        """
        if self.key_protection == PROTECTION_KEYRING:
            kek = self._kek_for(identity_id, key_meta)
        elif self.key_protection == PROTECTION_PASSPHRASE:
            kek = self._kek_for(identity_id, key_meta)
        else:
            kek = self._file_key()
        return ENVELOPE_PREFIX + _FernetBackend(kek).encrypt(seed_hex)

    def _decode_seed_hex(self, identity_id: str, stored: str,
                         protection: Optional[str], key_meta: Optional[str]) -> str:
        """把库里的 seed_key 字段解回 hex 明文（仅在内存中使用）。"""
        stored = stored or ""
        if not stored.startswith(ENVELOPE_PREFIX):
            if protection in (None, "", PROTECTION_LEGACY):
                raise Vault2KeyProtectionError(
                    "身份 %s 的 seed_key 仍是旧库明文、且本次未能自动迁移 —— "
                    "请配置 keyring 或 %s 后重新打开（fail-closed，不使用明文）"
                    % (identity_id, PASSPHRASE_ENV))
            raise Vault2KeyProtectionError(
                "身份 %s 的 seed_key 格式未知（protection=%r）" % (identity_id, protection))
        token = stored[len(ENVELOPE_PREFIX):]
        kek = self._kek_for(identity_id, key_meta)
        try:
            return _FernetBackend(kek).decrypt(token)
        except Exception as exc:
            raise Vault2KeyProtectionError(
                "seed_key 解密失败（身份 %s，保护方式 %s）：%s —— "
                "请确认 keyring 条目/口令与建库时一致"
                % (identity_id, self.key_protection, exc))

    def _migrate_key_protection(self) -> None:
        """把旧库里的**明文** seed_key 迁到当前保护方式（要么全成、要么不改）。"""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT id, seed_key, key_protection FROM identities").fetchall()
        pending = [(ident, stored) for (ident, stored, protection) in rows
                   if stored and not str(stored).startswith(ENVELOPE_PREFIX)
                   and protection in (None, "", PROTECTION_LEGACY)]
        if not pending:
            return
        if self.key_protection not in PROTECTION_KINDS:
            raise Vault2KeyProtectionError(
                _key_protection_unavailable_message("当前没有可用的密钥保护方式"))
        prepared = []
        keyring_written = []
        try:
            for ident, plain_hex in pending:
                stored, protection, meta = self._encrypt_seed_hex(ident, plain_hex)
                prepared.append((stored, protection, meta, ident))
                if protection == PROTECTION_KEYRING:
                    keyring_written.append(ident)
            with self._db() as conn:      # 单事务：全部 UPDATE 或全部回滚
                for stored, protection, meta, ident in prepared:
                    conn.execute(
                        "UPDATE identities SET seed_key=?, key_protection=?, key_meta=? "
                        "WHERE id=?", (stored, protection, meta, ident))
        except Exception as exc:
            for ident in keyring_written:     # 回滚已写入的 keyring 条目
                try:
                    self._keyring.delete_password(KEYRING_SERVICE, ident)
                except Exception:
                    pass
            raise Vault2KeyProtectionError(
                "seed_key 明文迁移失败，库未改动（fail-closed）：%s: %s"
                % (type(exc).__name__, exc))
        self.migrated_key_protection = len(prepared)
        self._audit("key_migrate", None, None, target=PROTECTION_LEGACY,
                    success=True, reason="%d 个身份迁移到 %s"
                    % (len(prepared), self.key_protection))

    @contextlib.contextmanager
    def _db(self):
        """打开库连接并**保证关闭**（审计修复：句柄泄漏）。

        改前 14 处都写成 `with sqlite3.connect(...) as conn:` —— sqlite3 的
        连接上下文管理器只在退出时 commit/rollback，**不会 close**。实测后果：
        Windows 上 vault2.db 的文件句柄悬留，迁移/备份/删除时报
        `PermissionError: [WinError 32] 另一个程序正在使用此文件`
        （本轮迁移功能首次实测就撞上它）；长驻进程还会持续泄漏句柄。
        现在统一走本 helper：yield 后 commit，finally 一定 close。
        """
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS identities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pin_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    seed_key TEXT NOT NULL,
                    security_level TEXT NOT NULL DEFAULT 'L2',
                    recovery_key_hash TEXT,    -- HMAC-SHA256(recovery_key, server_secret)，NULL = 未启用
                    key_salt TEXT,             -- 主密钥派生盐（recover 不变，保证重置 PIN 后数据可解）
                    created_at INTEGER,
                    last_auth_at INTEGER,
                    failed_attempts INTEGER DEFAULT 0,
                    locked_until INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS machines (
                    id TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    name TEXT,
                    registered_at INTEGER,
                    last_seen_at INTEGER,
                    FOREIGN KEY (identity_id) REFERENCES identities(id)
                );
                CREATE TABLE IF NOT EXISTS secrets (
                    id TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    secret_type TEXT NOT NULL,
                    security_level TEXT NOT NULL,
                    created_at INTEGER,
                    expires_at INTEGER,
                    last_rotated_at INTEGER,
                    rotate_interval_days INTEGER,
                    metadata TEXT,
                    -- Phase 1.5：行级算法敏捷 + 密钥隔离
                    cipher_alg TEXT DEFAULT 'fernet',
                    key_salt TEXT,           -- 16 bytes hex，NULL = 旧格式（向后兼容）
                    key_iters INTEGER DEFAULT 1000,
                    key_dklen INTEGER DEFAULT 32,
                    FOREIGN KEY (identity_id) REFERENCES identities(id)
                );
                CREATE TABLE IF NOT EXISTS used_codes (
                    identity_id TEXT,
                    machine_id TEXT,
                    code TEXT,
                    used_at INTEGER,
                    PRIMARY KEY (identity_id, machine_id, code)
                );
                CREATE INDEX IF NOT EXISTS idx_secrets_identity ON secrets(identity_id);
                CREATE INDEX IF NOT EXISTS idx_secrets_name ON secrets(identity_id, name);
                CREATE TABLE IF NOT EXISTS rotated_backups (
                    id TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    secret_type TEXT NOT NULL,
                    security_level TEXT NOT NULL,
                    rotated_at INTEGER,
                    expires_at INTEGER,
                    FOREIGN KEY (identity_id) REFERENCES identities(id)
                );
                CREATE INDEX IF NOT EXISTS idx_rotated_identity ON rotated_backups(identity_id);
                CREATE INDEX IF NOT EXISTS idx_rotated_expires ON rotated_backups(expires_at);
                -- KEK 轮换日志（docs/vault2-kek-rotation.md §4.4 第 0 步）
                -- 纯增量：本步只建表、不写行；后续步骤用它记录"待清理的旧代 KEK"。
                -- cleaned=0 表示旧代外部条目还在（keyring item / key 文件），
                -- GC 成功后置 1。主键 (identity_id, kek_gen) 保证同一代只登记一次。
                CREATE TABLE IF NOT EXISTS kek_retired (
                    identity_id TEXT NOT NULL,
                    kek_gen     INTEGER NOT NULL,
                    locator     TEXT NOT NULL,
                    retired_at  TEXT NOT NULL,
                    cleaned     INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (identity_id, kek_gen)
                );
                """
            )

    def _audit(self, action: str, identity_id: str = None, machine_id: str = None,
               target: str = None, success: bool = True, reason: str = None, caller: str = None):
        record = {"ts": int(time.time()), "action": action, "identity_id": identity_id,
                  "machine_id": machine_id, "target": target, "success": success,
                  "reason": reason, "caller": caller}
        existed = os.path.exists(self.audit_path)
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if not existed:
            # 审计日志可能含 caller/identity 元数据 → 首次创建后收紧权限（best-effort）
            try:
                os.chmod(self.audit_path, 0o600)
            except OSError:
                pass
            self._audit_mode_set = True

    def _machine_fingerprint(self) -> str:
        import platform
        parts = [platform.node(), platform.system(), platform.machine()]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]

    def _derive_backup_key(self, seed_key: bytes) -> bytes:
        """从身份级 seed_key 派生备份密钥。

        seed_key 注册时生成、不随 recover 变化，因此 recover 重置 PIN 后
        历史 rotated_backups 备份仍可解密回滚。使用独立派生域 'vault-backup'
        避免与 master_key / row_key 复用同一密钥。
        """
        return hashlib.pbkdf2_hmac(
            "sha256", seed_key, b"vault-backup", 1000, 32
        )

    def _generate_recovery_key(self) -> str:
        """生成 32 字符随机恢复密钥，按 4-4-4-4-4-4-4-4 分组。"""
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(32))
        return "-".join(raw[i:i+4] for i in range(0, 32, 4))

    def _hash_recovery_key(self, recovery_key: str, seed_key_hex: str) -> str:
        """用身份级 seed_key 做 HMAC-SHA256，不存明文恢复密钥。"""
        return hmac.new(
            bytes.fromhex(seed_key_hex),
            recovery_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # ── register ──
    def register(self, identity_name: str, pin: str, machine_name: str = None,
                 security_level: str = "L2") -> dict:
        if not (pin and pin.isdigit() and len(pin) == 6):
            return {"status": "error", "message": "PIN 必须是 6 位数字"}
        if security_level not in ("L1", "L2", "L3"):
            return {"status": "error", "message": "security_level 必须是 L1/L2/L3"}
        # **唯一**允许建库的入口：注册就是要新建密钥库
        self._ensure_ready()

        identity_id = str(uuid.uuid4())
        machine_id = str(uuid.uuid4())
        salt = secrets.token_bytes(16)
        pin_hash = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100000)
        seed_key = generate_seed_key(32)
        seed_hex = seed_key.hex()
        key_salt = secrets.token_bytes(16)  # 主密钥派生盐，recover 不变
        fingerprint = self._machine_fingerprint()
        recovery_key = self._generate_recovery_key()
        recovery_key_hash = self._hash_recovery_key(recovery_key, seed_hex)
        # seed_key **不再明文入库**：加密后落库（keyring / passphrase / file-key）
        stored_seed, seed_protection, seed_meta = self._encrypt_seed_hex(
            identity_id, seed_hex)

        try:
            with self._db() as conn:
                conn.execute(
                    "INSERT INTO identities (id, name, pin_hash, salt, seed_key, "
                    "security_level, recovery_key_hash, key_salt, created_at, "
                    "key_protection, key_meta) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (identity_id, identity_name, pin_hash.hex(), salt.hex(), stored_seed,
                     security_level, recovery_key_hash, key_salt.hex(), int(time.time()),
                     seed_protection, seed_meta),
                )
                conn.execute(
                    "INSERT INTO machines (id, identity_id, fingerprint, name, registered_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (machine_id, identity_id, fingerprint, machine_name or "default", int(time.time())),
                )
        except Exception:
            # 入库失败 → 回滚刚写的 keyring 条目，避免留下孤儿密钥
            if seed_protection == PROTECTION_KEYRING and self._keyring is not None:
                try:
                    self._keyring.delete_password(KEYRING_SERVICE, identity_id)
                except Exception:
                    pass
            raise
        self._audit("register", identity_id, machine_id, success=True)
        return {
            "status": "ok",
            "identity_id": identity_id,
            "machine_id": machine_id,
            "security_level": security_level,
            "recovery_key": recovery_key,
            "warning": "PIN 不可找回！请务必牢记。恢复密钥仅在此刻展示一次，请抄写到安全位置。若两者皆遗忘，只能重新注册身份，所有凭证将永久丢失。",
            "message": "注册成功，请妥善保管 PIN 和恢复密钥",
        }

    # ── auth ──
    def auth(self, identity_id: str, machine_id: str, pin: str,
             hardware_token: str = None) -> dict:
        if not self._exists():
            # 库不存在 = 没有身份（**绝不建库**：改前构造就建）
            return {"status": "error", "message": "身份不存在"}
        # 库存在 → 补齐 schema + 解析密钥保护（改前由 __init__ 做；现在懒加载）。
        # 对已存在的库 _ensure_ready() 是幂等的：不新建目录、不新建表。
        self._ensure_ready()
        now = int(time.time())
        with self._db() as conn:
            row = conn.execute(
                "SELECT pin_hash, salt, seed_key, security_level, failed_attempts, "
                "locked_until, key_salt, key_protection, key_meta "
                "FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            if not row:
                self._audit("auth", identity_id, machine_id, success=False, reason="identity_not_found")
                return {"status": "error", "message": "身份不存在"}

            (pin_hash_hex, salt_hex, seed_key_stored, level, failed, locked,
             key_salt_hex, seed_protection, seed_meta) = row
            # seed_key 在库里是密文，按保护方式（keyring/passphrase/file-key）现场解回
            try:
                seed_key_hex = self._decode_seed_hex(
                    identity_id, seed_key_stored, seed_protection, seed_meta)
            except Vault2KeyProtectionError as exc:
                self._audit("auth", identity_id, machine_id, success=False,
                            reason="key_protection_failed: %s" % exc)
                return {"status": "error", "message": str(exc),
                        "error": {"code": exc.code, "message": str(exc)}}
            if locked and now < locked:
                self._audit("auth", identity_id, machine_id, success=False, reason="locked")
                return {"status": "error", "message": f"账户已锁定，请 {locked - now} 秒后重试"}

            expected_hash = hashlib.pbkdf2_hmac(
                "sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), 100000
            )
            if not hmac.compare_digest(expected_hash.hex(), pin_hash_hex):
                failed += 1
                locked_until = now + LOCKOUT_SECONDS if failed >= MAX_FAILED_ATTEMPTS else 0
                if failed >= MAX_FAILED_ATTEMPTS:
                    failed = 0
                conn.execute(
                    "UPDATE identities SET failed_attempts=?, locked_until=? WHERE id=?",
                    (failed, locked_until, identity_id),
                )
                self._audit("auth", identity_id, machine_id, success=False, reason="wrong_pin")
                return {"status": "error", "message": "PIN 错误"}

            conn.execute(
                "UPDATE identities SET failed_attempts=0, locked_until=0, last_auth_at=? WHERE id=?",
                (now, identity_id),
            )

            machine = conn.execute(
                "SELECT fingerprint FROM machines WHERE id=? AND identity_id=?",
                (machine_id, identity_id),
            ).fetchone()
            if not machine:
                self._audit("auth", identity_id, machine_id, success=False, reason="machine_not_found")
                return {"status": "error", "message": "机器未注册"}
            if machine[0] != self._machine_fingerprint():
                self._audit("auth", identity_id, machine_id, success=False, reason="fingerprint_mismatch")
                return {"status": "error", "message": "机器指纹不匹配"}

            # L3 硬件绑定预留：当前仅校验参数存在性，未来对接 HSM/TPM
            if level == "L3" and hardware_token is None:
                self._audit("auth", identity_id, machine_id, success=False, reason="l3_hardware_token_missing")
                return {"status": "error", "message": "L3 级别需要提供 hardware_token"}

            seed_key = bytes.fromhex(seed_key_hex)
            dynamic_code = generate_dynamic_code(seed_key, DEFAULT_TIME_STEP)

            # L1 跳过动态码校验；L2/L3 需要
            if level != "L1":
                # 防重放：必须先查该动态码是否已被本身份+机器用过。
                # used_codes 主键是 (identity_id, machine_id, code)，单靠
                # INSERT OR IGNORE 无法拦截——重复时 rowcount=0 但这里原先不看
                # 返回值，等于动态码在 60s+window TTL 内可被无限重放（窃到一次
                # TOTP 即可重复换 token；与 security/otp BUG-147 同型）。
                reused = conn.execute(
                    "SELECT 1 FROM used_codes WHERE identity_id=? AND machine_id=? AND code=?",
                    (identity_id, machine_id, dynamic_code),
                ).fetchone()
                if reused:
                    self._audit("auth", identity_id, machine_id,
                                success=False, reason="dynamic_code_replay")
                    return {"status": "error", "message": "动态码已被使用，请使用最新动态码"}
                conn.execute(
                    "INSERT OR IGNORE INTO used_codes (identity_id, machine_id, code, used_at) VALUES (?, ?, ?, ?)",
                    (identity_id, machine_id, dynamic_code, now),
                )
                # 顺手清理过期 used_codes（保留 1 天窗口，动态码 60s + 容错足够）
                conn.execute(
                    "DELETE FROM used_codes WHERE used_at < ?", (now - 86400,)
                )

            # P0 修复（第 15 轮）：**动态码不再参与 KDF**。
            # 改前这里把 effective_dynamic（L2/L3 的 60s TOTP）掺进 PBKDF2 ⇒ master
            # 每分钟变一次 ⇒ 上个窗口写的密文下个窗口解不开。动态码的职责只剩
            # 「认证挑战」—— 上面已经做过 TOTP 校验 + used_codes 防重放。
            # L1 改前 effective_dynamic 就是空串 ⇒ 行为**逐字不变**（有断言）。
            if key_salt_hex:
                master_key = derive_master_key_stable(
                    seed_key_hex, bytes.fromhex(key_salt_hex))
            else:
                # 旧身份（无 key_salt）：回退为 pin 派生（向后兼容）；同样不掺时间
                master_key = derive_master_key_stable(pin, bytes.fromhex(salt_hex))

            token = secrets.token_urlsafe(32)
            ttl = SESSION_TTL.get(level, 600)
            self._sessions[token] = {
                "identity_id": identity_id,
                "machine_id": machine_id,
                "security_level": level,
                "expires_at": now + ttl,
                "master_key": master_key,
            }

            self._audit("auth", identity_id, machine_id, success=True)
            result = {"status": "ok", "dynamic_code": dynamic_code if level != "L1" else "",
                      "expires_in": DEFAULT_TIME_STEP, "session_token": token,
                      "security_level": level}
        # 登录是天然的升级点（本来就是写路径）：把该身份在"旧派生时期"写入的密文
        # 迁到稳定派生。失败不阻断登录，但**如实回传**（不静默）。
        try:
            result["master_migration"] = self.migrate_master_derivation(identity_id)
        except Exception as exc:                       # noqa: BLE001
            result["master_migration"] = {
                "status": "error", "code": "migration_failed",
                "message": "%s: %s" % (type(exc).__name__, exc)}
        return result

    # ── recover（恢复密钥重置 PIN） ──
    def recover(self, identity_id: str, recovery_key: str, new_pin: str) -> dict:
        if not (new_pin and new_pin.isdigit() and len(new_pin) == 6):
            return {"status": "error", "message": "新 PIN 必须是 6 位数字"}

        with self._db() as conn:
            row = conn.execute(
                "SELECT salt, seed_key, recovery_key_hash, security_level, "
                "key_protection, key_meta "
                "FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            if not row:
                self._audit("recover", identity_id, success=False, reason="identity_not_found")
                return {"status": "error", "message": "身份不存在"}

            salt_hex, seed_key_stored, rk_hash, level, seed_protection, seed_meta = row
            try:
                seed_key_hex = self._decode_seed_hex(
                    identity_id, seed_key_stored, seed_protection, seed_meta)
            except Vault2KeyProtectionError as exc:
                self._audit("recover", identity_id, success=False,
                            reason="key_protection_failed: %s" % exc)
                return {"status": "error", "message": str(exc),
                        "error": {"code": exc.code, "message": str(exc)}}
            if not rk_hash:
                self._audit("recover", identity_id, success=False, reason="no_recovery_key")
                return {"status": "error", "message": "该身份未启用恢复密钥"}

            expected = self._hash_recovery_key(recovery_key, seed_key_hex)
            if not hmac.compare_digest(expected, rk_hash):
                self._audit("recover", identity_id, success=False, reason="wrong_recovery_key")
                return {"status": "error", "message": "恢复密钥错误"}

            # 重置 PIN
            new_salt = secrets.token_bytes(16)
            new_pin_hash = hashlib.pbkdf2_hmac(
                "sha256", new_pin.encode("utf-8"), new_salt, 100000
            )

            # 生成新恢复密钥并作废旧的
            new_recovery_key = self._generate_recovery_key()
            new_rk_hash = self._hash_recovery_key(new_recovery_key, seed_key_hex)

            conn.execute(
                "UPDATE identities SET pin_hash=?, salt=?, recovery_key_hash=?, "
                "failed_attempts=0, locked_until=0 WHERE id=?",
                (new_pin_hash.hex(), new_salt.hex(), new_rk_hash, identity_id),
            )

            # BUG-42: 清理该身份的历史 used_codes——recover 是凭据整体重置，
            # 旧 PIN 时代的动态码已失效；不清则 auth 防重放会误判合法重新认证为 replay。
            conn.execute("DELETE FROM used_codes WHERE identity_id=?", (identity_id,))

        self._audit("recover", identity_id, success=True, reason="pin_reset")
        return {
            "status": "ok",
            "message": "PIN 已重置，请使用新 PIN 登录",
            "recovery_key": new_recovery_key,
            "warning": "恢复密钥已更新，旧密钥作废。请抄写新的恢复密钥到安全位置。",
        }

    # ── token 校验 ──
    def _verify_token(self, token: str) -> Tuple[bool, Optional[dict]]:
        sess = self._sessions.get(token)
        if not sess:
            return False, None
        if int(time.time()) > sess["expires_at"]:
            del self._sessions[token]
            return False, None
        return True, sess

    # ── get_secret ──
    def get_secret(self, token: str, name: str, caller: str = None,
                   read_only: bool = False) -> dict:
        """读取解密一个密钥。

        第 14 轮审计修复（D 类「名实不符的只读」）：本函数名字是 get，但此前：
          * 每次读都 `_audit(...)` → **追加 audit.log**（读也写盘）；
          * 读到 legacy 行（`key_salt IS NULL`）会 `UPDATE secrets ...` **懒迁移**，
            等于"读密钥"改了权威数据 —— 只读文件系统上直接失败。
        现在 `read_only=True` 时：**不写 audit.log、不做懒迁移**，返回值里带
        `legacy: true` 让上层自行决定（显式迁移走 `migrate_legacy_rows()` 或写路径）。
        默认 `read_only=False` 完全保持旧行为（审计 + 懒迁移），兼容既有调用方。
        """
        if not self._exists():
            # 库不存在 = 没有密钥（与"查不到"同形，且**不建库**）
            return {"status": "error", "message": "凭证不存在"}
        self._ensure_ready()          # 已存在的库：补齐 schema / 解析密钥保护（幂等）
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]

        with self._db() as conn:
            row = conn.execute(
                "SELECT value, secret_type, security_level, expires_at, metadata, "
                "cipher_alg, key_salt, key_iters, key_dklen "
                "FROM secrets WHERE identity_id=? AND name=?",
                (identity_id, name),
            ).fetchone()
            if not row:
                if not read_only:
                    self._audit("get", identity_id, sess["machine_id"], target=name,
                                success=False, reason="not_found", caller=caller)
                return {"status": "error", "message": "凭证不存在"}

            (value_enc, stype, level, expires, meta_json,
             cipher_alg, key_salt_hex, key_iters, key_dklen) = row

            if expires and int(time.time()) > expires:
                if not read_only:
                    self._audit("get", identity_id, sess["machine_id"], target=name,
                                success=False, reason="expired", caller=caller)
                return {"status": "error", "message": "凭证已过期"}

            # ── 密钥派生：向后兼容 + 懒迁移 ──
            if key_salt_hex is None:
                # 旧格式：直接用 master_key，算法视为 fernet
                row_key = master_key
                effective_alg = "fernet"
                is_legacy = True
            else:
                row_salt = bytes.fromhex(key_salt_hex)
                row_key = _derive_row_key(master_key, row_salt, key_iters or DEFAULT_ROW_ITERS,
                                          key_dklen or DEFAULT_ROW_DKLEN)
                effective_alg = cipher_alg or DEFAULT_CIPHER_ALG
                is_legacy = False

            try:
                backend = _make_backend(effective_alg, row_key)
                value = backend.decrypt(value_enc)
            except Exception as e:
                if not read_only:
                    self._audit("get", identity_id, sess["machine_id"], target=name,
                                success=False, reason=f"decrypt_error: {e}", caller=caller)
                return {"status": "error", "message": "凭证解密失败（密钥错误？）"}

            # 懒迁移：旧格式读取成功后自动升级为行级加密。
            # read_only=True 时**绝不迁移**（只把 legacy 标记回给上层，由显式
            # migrate_legacy_rows()/写路径决定）——"读"不能改权威数据。
            if is_legacy and not read_only:
                try:
                    new_salt = secrets.token_bytes(16)
                    new_row_key = _derive_row_key(master_key, new_salt)
                    new_backend = _make_backend(DEFAULT_CIPHER_ALG, new_row_key)
                    new_encrypted = new_backend.encrypt(value)
                    conn.execute(
                        "UPDATE secrets SET value=?, cipher_alg=?, key_salt=?, "
                        "key_iters=?, key_dklen=? WHERE identity_id=? AND name=?",
                        (new_encrypted, DEFAULT_CIPHER_ALG, new_salt.hex(),
                         DEFAULT_ROW_ITERS, DEFAULT_ROW_DKLEN, identity_id, name),
                    )
                    conn.commit()
                except Exception:
                    # 懒迁移失败不阻塞读取，下次再试
                    pass

            metadata = json.loads(meta_json) if meta_json else {}
            if not read_only:
                self._audit("get", identity_id, sess["machine_id"], target=name,
                            success=True, caller=caller)
            return {"status": "ok", "name": name, "value": value,
                    "type": stype, "security_level": level,
                    "expires_at": expires, "metadata": metadata,
                    # 第 14 轮：读路径不再自动迁移旧行，把标记透出给上层
                    "legacy": bool(is_legacy)}

    def migrate_legacy_rows(self, token: str) -> dict:
        """显式迁移该身份下的 legacy 行（key_salt 为空 → 行级加密）。

        返回 {'status','checked','migrated','failed'}。
        只在**显式**操作/写路径调用；读路径（read_only=True）绝不自动迁移。
        """
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}
        identity_id = sess["identity_id"]
        with self._db() as conn:
            rows = [r[0] for r in conn.execute(
                "SELECT name FROM secrets WHERE identity_id=? AND key_salt IS NULL",
                (identity_id,)).fetchall()]
        migrated, failed = 0, []
        for name in rows:
            result = self.get_secret(token, name, caller="vault.migrate",
                                     read_only=False)
            if result.get("status") == "ok":
                migrated += 1
            else:
                failed.append({"name": name,
                               "reason": result.get("message")})
        return {"status": "ok", "checked": len(rows),
                "migrated": migrated, "failed": failed}

    # ── set_secret ──
    def set_secret(self, token: str, name: str, value: str, secret_type: str = "api_key",
                   security_level: str = None, expires_at: int = None,
                   rotate_interval_days: int = None, metadata: dict = None,
                   caller: str = None, cipher_alg: str = None) -> dict:
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]
        level = security_level or sess["security_level"]

        # 算法选择
        effective_alg = (cipher_alg or DEFAULT_CIPHER_ALG).lower()
        if effective_alg not in CIPHER_ALG_WHITELIST:
            return {"status": "error",
                    "message": f"不支持的加密算法: {effective_alg}（白名单: {CIPHER_ALG_WHITELIST}）"}

        # 行级密钥派生
        row_salt = secrets.token_bytes(16)
        row_key = _derive_row_key(master_key, row_salt)
        backend = _make_backend(effective_alg, row_key)
        encrypted = backend.encrypt(value)

        now = int(time.time())
        sid = str(uuid.uuid4())

        with self._db() as conn:
            existing = conn.execute(
                "SELECT id FROM secrets WHERE identity_id=? AND name=?",
                (identity_id, name),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE secrets SET value=?, secret_type=?, security_level=?, "
                    "expires_at=?, last_rotated_at=?, rotate_interval_days=?, metadata=?, "
                    "cipher_alg=?, key_salt=?, key_iters=?, key_dklen=? "
                    "WHERE identity_id=? AND name=?",
                    (encrypted, secret_type, level, expires_at, now, rotate_interval_days,
                     json.dumps(metadata or {}), effective_alg, row_salt.hex(),
                     DEFAULT_ROW_ITERS, DEFAULT_ROW_DKLEN, identity_id, name),
                )
                action = "update"
            else:
                conn.execute(
                    "INSERT INTO secrets (id, identity_id, name, value, secret_type, "
                    "security_level, created_at, expires_at, last_rotated_at, rotate_interval_days, "
                    "metadata, cipher_alg, key_salt, key_iters, key_dklen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (sid, identity_id, name, encrypted, secret_type, level, now, expires_at,
                     now, rotate_interval_days, json.dumps(metadata or {}), effective_alg,
                     row_salt.hex(), DEFAULT_ROW_ITERS, DEFAULT_ROW_DKLEN),
                )
                action = "set"

        self._audit(action, identity_id, sess["machine_id"], target=name, success=True, caller=caller)
        return {"status": "ok", "name": name, "action": action, "security_level": level,
                "cipher_alg": effective_alg}

    # ── list_secrets ──
    def list_secrets(self, token: str) -> dict:
        if not self._exists():
            # 库不存在 = 一个密钥都没有（空列表，**不建库**）
            return {"status": "ok", "count": 0, "secrets": [], "vault_exists": False}
        self._ensure_ready()
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期"}

        identity_id = sess["identity_id"]
        with self._db() as conn:
            rows = conn.execute(
                "SELECT name, secret_type, security_level, created_at, expires_at, metadata, "
                "cipher_alg, key_salt IS NULL as is_legacy "
                "FROM secrets WHERE identity_id=?",
                (identity_id,),
            ).fetchall()

        results = []
        for name, stype, level, created, expires, meta, alg, is_legacy in rows:
            results.append({
                "name": name,
                "type": stype,
                "security_level": level,
                "created_at": created,
                "expires_at": expires,
                "metadata": json.loads(meta) if meta else {},
                "cipher_alg": alg,
                "legacy": bool(is_legacy),
            })
        return {"status": "ok", "count": len(results), "secrets": results}

    # ── delete_secret ──
    def delete_secret(self, token: str, name: str, caller: str = None) -> dict:
        if not self._exists():
            return {"status": "error", "message": "凭证不存在"}
        self._ensure_ready()
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        with self._db() as conn:
            row = conn.execute(
                "SELECT id FROM secrets WHERE identity_id=? AND name=?",
                (identity_id, name),
            ).fetchone()
            if not row:
                self._audit("delete", identity_id, sess["machine_id"], target=name,
                           success=False, reason="not_found", caller=caller)
                return {"status": "error", "message": "凭证不存在"}

            conn.execute(
                "DELETE FROM secrets WHERE identity_id=? AND name=?",
                (identity_id, name),
            )

        self._audit("delete", identity_id, sess["machine_id"], target=name, success=True, caller=caller)
        return {"status": "ok", "name": name, "action": "delete"}

    # ── rotate_secret ──
    # ── P0 迁移：把「动态码参与 KDF」时期写入的密文迁到稳定派生 ──

    def _reencrypt_rows(self, conn, updates) -> None:
        """把收集好的行更新一次性写进去（单独成方法便于测试注入失败）。"""
        for row_id, new_value in updates:
            conn.execute("UPDATE secrets SET value=? WHERE id=?", (new_value, row_id))

    # ── seed_key 轮换（第 16 轮；P0 修复后才安全）──────────────────────

    def _apply_seed_rotation(self, conn, identity_id: str, new_envelope: str,
                             secret_updates, backup_updates) -> None:
        """轮换的**写阶段**（单独成方法：便于注入失败测试事务回滚）。

        调用方保证在 `with self._db()` 里执行 —— 本方法抛错时，`_db()` 不会 commit，
        close 即回滚，磁盘保持轮换前状态。
        """
        for sid, new_enc in secret_updates:
            conn.execute("UPDATE secrets SET value=? WHERE id=?", (new_enc, sid))
        for bid, new_enc in backup_updates:
            conn.execute("UPDATE rotated_backups SET value=? WHERE id=?", (new_enc, bid))
        conn.execute(
            "UPDATE identities SET seed_key=?, recovery_key_hash=NULL WHERE id=?",
            (new_envelope, identity_id))
        # 旧 TOTP 随 seed 失效；留着只会在极小概率下与新码撞上而误判"重放"
        conn.execute("DELETE FROM used_codes WHERE identity_id=?", (identity_id,))

    def rotate_seed_key(self, token: str, caller: str = None, apply: bool = True) -> dict:
        """轮换身份的 `seed_key`：换新 seed + 用新 master 重加密**所有**相关密文。

        为什么值得做：`master_key` 不含 PIN ⇒ `seed_key` 是**唯一的密码学根**。轮换
        缩短"泄漏快照"的有效期，并让历史 TOTP 全部失效。它**不能**追溯保护已经被
        拷走的密文（这点必须写清，别给人错误的安全感）。

        覆盖范围（**一个事务，失败全回滚**）：
          1. `secrets.value` —— row_key 由 master 派生（master 由 seed 派生）；
          2. `rotated_backups.value` —— 由 `_derive_backup_key(seed)` 派生，**也依赖 seed**
             （这是最容易漏的一条：不迁的话 seed 换了、旧备份就再也解不开）；
          3. `identities.seed_key` —— 用**现有 KEK** 重新封装（不写 keyring，见
             `_reencrypt_seed_envelope` 的注释）；
          4. `used_codes` —— 清掉该身份的记录（旧 TOTP 随 seed 失效；留着只会在
             极小概率下与新码撞上而误判"重放"）；
          5. `identities.recovery_key_hash` —— 它是 `HMAC(recovery_key, seed_hex)`，
             seed 一变就**必然失效**；且我们没有 recovery_key 无法重算 ⇒ 置 NULL 并
             在返回值里明确 warning（**不静默**，用户需重新生成恢复密钥）。

        失败语义（lead 裁决）：**任一条解不开就中止**，绝不"跳过坏的继续" ——
        轮换是重大操作，半途状态比失败更糟。
        """
        if not self._exists():
            return {"status": "error", "code": "vault_not_found",
                    "message": "密钥库不存在，没有可轮换的数据（本方法绝不建库）"}
        self._ensure_ready()
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}
        identity_id = sess["identity_id"]
        master_old = sess["master_key"]

        # ── 读阶段（零写）：先把需要改的东西全部算出来并逐条验证 ──
        with self._db() as conn:
            row = conn.execute(
                "SELECT seed_key, key_protection, key_meta, key_salt, recovery_key_hash "
                "FROM identities WHERE id=?", (identity_id,)).fetchone()
        if not row:
            return {"status": "error", "message": "身份不存在"}
        stored_old, protection, key_meta, key_salt_hex, recovery_hash_old = row
        if not key_salt_hex:
            return {"status": "error", "code": "rotate_unsupported",
                    "message": ("该身份是旧格式（无 key_salt，master 由 PIN 派生），"
                                "轮换需要 PIN 且与本轮设计不兼容；请重新注册身份以启用轮换")}

        try:
            seed_hex_old = self._decode_seed_hex(identity_id, stored_old, protection, key_meta)
        except Exception as exc:                       # noqa: BLE001
            return {"status": "error", "code": "seed_unreadable",
                    "message": "无法解开当前 seed_key：%s" % exc}

        new_seed_hex = generate_seed_key(32).hex()
        new_master = derive_master_key_stable(new_seed_hex, bytes.fromhex(key_salt_hex))
        backup_key_old = self._derive_backup_key(bytes.fromhex(seed_hex_old))
        backup_key_new = self._derive_backup_key(bytes.fromhex(new_seed_hex))
        new_envelope = self._reencrypt_seed_envelope(
            identity_id, new_seed_hex, protection, key_meta, stored_old)

        secret_updates = []
        backup_updates = []
        try:
            # ① secrets：master_old → master_new（保留每行自己的 salt/alg/迭代参数）
            with self._db() as conn:
                cursor = conn.execute(
                    "SELECT id, name, value, cipher_alg, key_salt, key_iters, key_dklen "
                    "FROM secrets WHERE identity_id=?", (identity_id,))
                while True:
                    chunk = cursor.fetchmany(200)      # 分页：备份/密钥多时不吃满内存
                    if not chunk:
                        break
                    for (sid, name, enc, alg, rsalt, iters, dklen) in chunk:
                        iters = iters or DEFAULT_ROW_ITERS
                        dklen = dklen or DEFAULT_ROW_DKLEN
                        alg = alg or DEFAULT_CIPHER_ALG

                        def _rk(master):
                            return (_derive_row_key(master, bytes.fromhex(rsalt), iters, dklen)
                                    if rsalt else master)

                        old_plain = _make_backend(alg, _rk(master_old)).decrypt(enc)
                        new_enc = _make_backend(alg, _rk(new_master)).encrypt(old_plain)
                        if _make_backend(alg, _rk(new_master)).decrypt(new_enc) != old_plain:
                            raise ValueError("重加密回读不一致: %s" % name)
                        secret_updates.append((sid, new_enc))
            # ② rotated_backups：backup_key_old → backup_key_new
            with self._db() as conn:
                cursor = conn.execute(
                    "SELECT id, original_name, value FROM rotated_backups WHERE identity_id=?",
                    (identity_id,))
                while True:
                    chunk = cursor.fetchmany(200)
                    if not chunk:
                        break
                    for (bid, bname, enc) in chunk:
                        old_plain = _FernetBackend(backup_key_old).decrypt(enc)
                        new_enc = _FernetBackend(backup_key_new).encrypt(old_plain)
                        if _FernetBackend(backup_key_new).decrypt(new_enc) != old_plain:
                            raise ValueError("备份重加密回读不一致: %s" % bname)
                        backup_updates.append((bid, new_enc))
        except Exception as exc:                       # noqa: BLE001
            self._audit("rotate_seed_key", identity_id, success=False,
                        reason="%s: %s" % (type(exc).__name__, exc), caller=caller)
            return {"status": "error", "code": "rotate_failed",
                    "message": ("轮换中止（磁盘未改动，旧 seed 与全部密文保持原样）：%s: %s"
                                % (type(exc).__name__, exc))}

        # ── 干跑（apply=False）：读阶段已经把"能解开/能重加密/回读一致"全验证过了，
        #    到这里直接返回统计 —— **不进写阶段、也不调 _ensure_ready()**（绝不建库）。
        if not apply:
            return {"status": "ok", "dry_run": True,
                    "identity_id": identity_id,
                    "would_rotate_secrets": len(secret_updates),
                    "would_rotate_backups": len(backup_updates),
                    "recovery_key_would_be_invalidated": bool(recovery_hash_old),
                    "note": ("干跑：读阶段已完成解密 + 重加密 + 回读验证，"
                             "但**未写入任何数据**；正式执行请传 apply=True")}

        # ── 写阶段（零写直到这里；单事务，抛错即整体回滚）──
        try:
            with self._db() as conn:
                self._apply_seed_rotation(conn, identity_id, new_envelope,
                                          secret_updates, backup_updates)
        except Exception as exc:                       # noqa: BLE001
            self._audit("rotate_seed_key", identity_id, success=False,
                        reason="write_phase: %s" % exc, caller=caller)
            return {"status": "error", "code": "rotate_write_failed",
                    "message": "轮换写阶段失败（事务已回滚）：%s: %s" % (type(exc).__name__, exc)}

        # ── 提交后：旧会话的 master_key 已过期，必须失效 ──
        stale = [t for t, s in self._sessions.items() if s.get("identity_id") == identity_id]
        for t in stale:
            self._sessions.pop(t, None)

        warnings = []
        if recovery_hash_old:
            warnings.append("恢复密钥已失效（recovery_key_hash 绑定旧 seed，无法在新 seed 下重算）"
                            "—— 请尽快重新生成恢复密钥")
        self._audit("rotate_seed_key", identity_id, success=True,
                    target="secrets=%d backups=%d" % (len(secret_updates), len(backup_updates)),
                    caller=caller)
        return {"status": "ok", "dry_run": False,
                "identity_id": identity_id,
                "rotated_secrets": len(secret_updates),
                "rotated_backups": len(backup_updates),
                "seed_fingerprint": hashlib.sha256(new_seed_hex.encode('utf-8')).hexdigest()[:12],
                "sessions_invalidated": len(stale),
                "recovery_key_invalidated": bool(recovery_hash_old),
                "warnings": warnings,
                "note": ("KEK 未轮换（轮换只换 seed，复用现有 KEK 以保证单事务原子性）；"
                         "已被拷走的旧密文不受保护 —— 轮换只缩短泄漏快照的有效期")}

    def migrate_master_derivation(self, identity_id: str = None) -> dict:
        """迁移某身份（或全部身份）的 secrets 到**稳定派生**（master 不掺时间）。

        设计要点（lead 硬要求）：
          * **全成或全不改**：先全部"试解密/试重加密"到内存，**任何一条失败就整批放弃**
            （此时磁盘一个字节都没写）；写阶段放在一个 `_db()` 事务里，抛错即回滚。
          * **幂等**：每行先试**新派生**能否解开 —— 能解开说明它已经是新格式，跳过。
            所以跑第二遍是 `migrated=0, already=N`，不报错。
          * **旧数据可救**：旧格式用该行 `created_at // 60` 反推 TOTP 窗口重建旧 master。
          * **不迁 `rotated_backups`**：它用 `_derive_backup_key(seed)`，只依赖 seed、
            与 master/时间无关（seed 不变 ⇒ 备份仍可解密）。
          * 无 `key_salt` 的旧身份需要 PIN 才能派生旧 master ⇒ 跳过并如实报告。
        """
        if not self._exists():
            return {"status": "ok", "migrated": 0, "already": 0,
                    "skipped_legacy": [], "vault_exists": False,
                    "note": "密钥库不存在，没有可迁移的数据（本方法绝不建库）"}
        self._ensure_ready()
        identities = []
        with self._db() as conn:
            if identity_id:
                rows = conn.execute(
                    "SELECT id, seed_key, key_protection, key_meta, key_salt, security_level "
                    "FROM identities WHERE id=?", (identity_id,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, seed_key, key_protection, key_meta, key_salt, security_level "
                    "FROM identities").fetchall()
            identities = list(rows)

        migrated, already, skipped_legacy, failures = 0, 0, [], []
        per_identity = {}
        updates = []
        for (ident, stored, protection, key_meta, key_salt_hex, level) in identities:
            if not key_salt_hex:
                skipped_legacy.append(ident)
                continue
            try:
                seed_hex = self._decode_seed_hex(ident, stored, protection, key_meta)
            except Exception as exc:                   # noqa: BLE001
                failures.append({"identity": ident, "name": None,
                                 "reason": "seed 解不开：%s" % exc})
                continue
            new_master = derive_master_key_stable(seed_hex, bytes.fromhex(key_salt_hex))
            ident_migrated = ident_already = 0

            with self._db() as conn:
                secret_rows = conn.execute(
                    "SELECT id, name, value, created_at, cipher_alg, key_salt, "
                    "key_iters, key_dklen FROM secrets WHERE identity_id=?",
                    (ident,)).fetchall()
            for (row_id, name, enc_value, created_at, cipher_alg,
                 row_salt_hex, key_iters, key_dklen) in secret_rows:
                iters = key_iters or DEFAULT_ROW_ITERS
                dklen = key_dklen or DEFAULT_ROW_DKLEN
                alg = cipher_alg or DEFAULT_CIPHER_ALG

                def _row_key(master):
                    if row_salt_hex:
                        return _derive_row_key(master, bytes.fromhex(row_salt_hex), iters, dklen)
                    return master

                # ① 先试新派生：能解开 = 已经是新格式（幂等）
                try:
                    plaintext = _make_backend(alg, _row_key(new_master)).decrypt(enc_value)
                    ident_already += 1
                    continue
                except Exception:                      # noqa: BLE001
                    pass
                # ② 旧派生：用 created_at 反推窗口
                window = int(created_at or 0) // DEFAULT_TIME_STEP
                try:
                    old_master = derive_master_key_windowed(seed_hex, window,
                                                            bytes.fromhex(key_salt_hex))
                    plaintext = _make_backend(alg, _row_key(old_master)).decrypt(enc_value)
                except Exception as exc:               # noqa: BLE001
                    failures.append({"identity": ident, "name": name,
                                     "reason": "新旧派生都解不开（created_at 窗口=%d）：%s"
                                               % (window, exc)})
                    continue
                # ③ 用新派生重加密，并**立刻验证**
                try:
                    new_enc = _make_backend(alg, _row_key(new_master)).encrypt(plaintext)
                    if _make_backend(alg, _row_key(new_master)).decrypt(new_enc) != plaintext:
                        raise ValueError("重加密后回读不一致")
                except Exception as exc:               # noqa: BLE001
                    failures.append({"identity": ident, "name": name,
                                     "reason": "重加密失败：%s" % exc})
                    continue
                updates.append((row_id, new_enc))
                ident_migrated += 1

            per_identity[ident] = {"migrated": ident_migrated, "already": ident_already}
            migrated += ident_migrated
            already += ident_already

        # 任何一条失败 → **整批放弃**（此刻磁盘仍未写入）
        if failures:
            self._audit("migrate_master", identity_id, target="failed",
                        success=False, reason=failures[0]["reason"][:200],
                        caller="vault2.migrate")
            return {"status": "error", "code": "migration_failed",
                    "message": ("迁移中止：%d 条无法迁移（其余行未改动）。"
                                "首条失败：identity=%s name=%s —— %s"
                                % (len(failures), failures[0]["identity"],
                                   failures[0]["name"], failures[0]["reason"])),
                    "failed": failures[:10], "migrated": 0, "already": already,
                    "skipped_legacy": skipped_legacy}

        if updates:
            with self._db() as conn:                   # 单事务：抛错即整体回滚
                self._reencrypt_rows(conn, updates)
        if migrated:
            self._audit("migrate_master", identity_id, target="migrated=%d" % migrated,
                        success=True, caller="vault2.migrate")
        return {"status": "ok", "migrated": migrated, "already": already,
                "per_identity": per_identity, "skipped_legacy": skipped_legacy,
                "note": ("rotated_backups 不迁移：它由 _derive_backup_key(seed) 加密，"
                         "只依赖 seed（本次 seed 不变）")}

    def rotate_secret(self, token: str, name: str, new_value: str = None,
                      caller: str = None) -> dict:
        if not self._exists():
            return {"status": "error", "message": "凭证不存在"}
        self._ensure_ready()
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]

        with self._db() as conn:
            row = conn.execute(
                "SELECT value, secret_type, security_level, expires_at, metadata, "
                "cipher_alg, key_salt, key_iters, key_dklen "
                "FROM secrets WHERE identity_id=? AND name=?",
                (identity_id, name),
            ).fetchone()
            if not row:
                self._audit("rotate", identity_id, sess["machine_id"], target=name,
                           success=False, reason="not_found", caller=caller)
                return {"status": "error", "message": "凭证不存在"}

            (value_enc, stype, level, expires, meta_json,
             cipher_alg, key_salt_hex, key_iters, key_dklen) = row

            # 解密旧值
            if key_salt_hex is None:
                row_key = master_key
                effective_alg = "fernet"
            else:
                row_salt = bytes.fromhex(key_salt_hex)
                row_key = _derive_row_key(master_key, row_salt, key_iters or DEFAULT_ROW_ITERS,
                                          key_dklen or DEFAULT_ROW_DKLEN)
                effective_alg = cipher_alg or DEFAULT_CIPHER_ALG

            try:
                backend = _make_backend(effective_alg, row_key)
                old_plaintext = backend.decrypt(value_enc)
            except Exception as e:
                self._audit("rotate", identity_id, sess["machine_id"], target=name,
                           success=False, reason=f"decrypt_error: {e}", caller=caller)
                return {"status": "error", "message": "凭证解密失败，无法轮换"}

            # 若未提供新值，按类型自动生成
            if new_value is None:
                if stype == "api_key":
                    new_value = "sk-" + secrets.token_urlsafe(24)
                elif stype == "token":
                    new_value = secrets.token_urlsafe(32)
                else:
                    return {"status": "error",
                            "message": f"类型 '{stype}' 不支持自动轮换，请显式提供 new_value"}

            # 备份旧值（保留 7 天），用 seed_key 派生备份密钥加密。
            # 注意：不能用 master_key —— recover 重置 PIN 后 master_key 会变，
            # 旧备份将无法解密。seed_key 注册时生成且不随 recover 变化，保证备份可回滚。
            now = int(time.time())
            backup_id = str(uuid.uuid4())
            seed_row = conn.execute(
                "SELECT seed_key, key_protection, key_meta FROM identities WHERE id=?",
                (identity_id,)
            ).fetchone()
            seed_key_bytes = (b"" if not seed_row else bytes.fromhex(
                self._decode_seed_hex(identity_id, seed_row[0], seed_row[1], seed_row[2])))
            backup_key = self._derive_backup_key(seed_key_bytes)
            backup_backend = _FernetBackend(backup_key)
            encrypted_backup = backup_backend.encrypt(old_plaintext)
            conn.execute(
                "INSERT INTO rotated_backups (id, identity_id, original_name, value, "
                "secret_type, security_level, rotated_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (backup_id, identity_id, name, encrypted_backup, stype, level, now, now + 604800),
            )

            # 用新值重新加密（新 row_key）
            new_salt = secrets.token_bytes(16)
            new_row_key = _derive_row_key(master_key, new_salt)
            new_backend = _make_backend(DEFAULT_CIPHER_ALG, new_row_key)
            new_encrypted = new_backend.encrypt(new_value)

            conn.execute(
                "UPDATE secrets SET value=?, secret_type=?, security_level=?, "
                "expires_at=?, last_rotated_at=?, rotate_interval_days=?, metadata=?, "
                "cipher_alg=?, key_salt=?, key_iters=?, key_dklen=? "
                "WHERE identity_id=? AND name=?",
                (new_encrypted, stype, level, expires, now, None,
                 meta_json or '{}', DEFAULT_CIPHER_ALG, new_salt.hex(),
                 DEFAULT_ROW_ITERS, DEFAULT_ROW_DKLEN, identity_id, name),
            )

        self._audit("rotate", identity_id, sess["machine_id"], target=name, success=True, caller=caller)
        return {
            "status": "ok",
            "name": name,
            "action": "rotate",
            "new_value_preview": new_value[:4] + "****" if len(new_value) > 8 else "****",
            "backup_expires_at": now + 604800,
        }

    # ── rollback_secret ──
    def rollback_secret(self, token: str, name: str, backup_id: str = None,
                        caller: str = None) -> dict:
        """回滚凭证到某次轮换前的旧值。

        未过期备份（保留 7 天）可用 seed_key 派生的 backup_key 解密，
        即使 recover 重置过 PIN 也不受影响。
        """
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]

        with self._db() as conn:
            # 查询可用备份（未过期）
            if backup_id:
                rows = conn.execute(
                    "SELECT id, original_name, value, secret_type, security_level, rotated_at "
                    "FROM rotated_backups WHERE identity_id=? AND id=? AND expires_at > ?",
                    (identity_id, backup_id, int(time.time())),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, original_name, value, secret_type, security_level, rotated_at "
                    "FROM rotated_backups WHERE identity_id=? AND original_name=? "
                    "AND expires_at > ? ORDER BY rotated_at DESC LIMIT 1",
                    (identity_id, name, int(time.time())),
                ).fetchall()
            if not rows:
                self._audit("rollback", identity_id, sess["machine_id"], target=name,
                           success=False, reason="no_valid_backup", caller=caller)
                return {"status": "error", "message": "没有可用的未过期备份（保留 7 天）"}

            bid, orig_name, enc_value, stype, level, rotated_at = rows[0]

            # 用 seed_key 派生的 backup_key 解密备份（与 rotate 时一致）
            seed_row = conn.execute(
                "SELECT seed_key, key_protection, key_meta FROM identities WHERE id=?",
                (identity_id,)
            ).fetchone()
            seed_key_bytes = (b"" if not seed_row else bytes.fromhex(
                self._decode_seed_hex(identity_id, seed_row[0], seed_row[1], seed_row[2])))
            backup_key = self._derive_backup_key(seed_key_bytes)
            backup_backend = _FernetBackend(backup_key)

            try:
                old_value = backup_backend.decrypt(enc_value)
            except Exception as e:
                self._audit("rollback", identity_id, sess["machine_id"], target=name,
                           success=False, reason=f"backup_decrypt_error: {e}", caller=caller)
                return {"status": "error", "message": "备份解密失败"}

            # 用当前 master_key 重新加密回滚值（新行级加密）
            now = int(time.time())
            new_salt = secrets.token_bytes(16)
            new_row_key = _derive_row_key(master_key, new_salt)
            new_backend = _make_backend(DEFAULT_CIPHER_ALG, new_row_key)
            new_encrypted = new_backend.encrypt(old_value)

            conn.execute(
                "UPDATE secrets SET value=?, secret_type=?, security_level=?, "
                "expires_at=?, last_rotated_at=?, rotate_interval_days=?, metadata=?, "
                "cipher_alg=?, key_salt=?, key_iters=?, key_dklen=? "
                "WHERE identity_id=? AND name=?",
                (new_encrypted, stype, level, None, now, None, '{}',
                 DEFAULT_CIPHER_ALG, new_salt.hex(),
                 DEFAULT_ROW_ITERS, DEFAULT_ROW_DKLEN, identity_id, orig_name),
            )

            # 删除已使用的备份
            conn.execute(
                "DELETE FROM rotated_backups WHERE id=?", (bid,)
            )

        self._audit("rollback", identity_id, sess["machine_id"], target=orig_name,
                   success=True, caller=caller)
        return {"status": "ok", "name": orig_name, "action": "rollback",
                "backup_id": bid, "rotated_at": rotated_at}

    # ── resolve_vault_refs ──
    def resolve_vault_refs(self, token: str, secrets_config: List[dict],
                           read_only: bool = False) -> dict:
        """解析 vault:// 引用，批量读取凭证并返回 env → value 映射。

        secrets_config 格式（与动作 cfg 中 secrets 声明兼容）：
            [
                {"env": "YANZI_API_KEY", "key": "vault://yanzi_api_key"},
                {"env": "YANZI_API_URL", "key": "vault://yanzi_api_url"},
                {"env": "FALLBACK_KEY", "key": "vault://missing", "default": "fallback_val"}
            ]

        返回:
            {"status": "ok", "resolved": {"YANZI_API_KEY": "sk-xxx", ...}, "missing": ["vault://missing"]}
        """
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        resolved = {}
        missing = []
        for item in secrets_config:
            env_name = item.get("env")
            key_ref = item.get("key", "")
            default = item.get("default")

            if not key_ref.startswith("vault://"):
                # 非 vault 引用，透传默认值（向后兼容传统 env 声明）
                if env_name and default is not None:
                    resolved[env_name] = default
                continue

            secret_name = key_ref[len("vault://"):]
            result = self.get_secret(token, secret_name, caller="vault.resolve",
                                     read_only=read_only)
            if result["status"] == "ok":
                resolved[env_name] = result["value"]
            elif default is not None:
                resolved[env_name] = default
            else:
                missing.append(key_ref)

        return {"status": "ok", "resolved": resolved, "missing": missing}

    # ── anomaly_check ──
    def anomaly_check(self, token: str, window_seconds: int = 3600) -> dict:
        """审计异常检测。扫描指定时间窗口内的审计日志，返回告警列表。"""
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        now = int(time.time())
        cutoff = now - window_seconds
        alerts = []

        # 收集窗口内审计记录
        records = []
        if os.path.isfile(self.audit_path):
            with open(self.audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("identity_id") == identity_id and rec.get("ts", 0) >= cutoff:
                        records.append(rec)

        # 规则 1：短时间内大量失败 auth（≥5 次失败）
        failed_auths = [r for r in records if r["action"] == "auth" and not r["success"]]
        if len(failed_auths) >= 5:
            alerts.append({
                "severity": "high",
                "rule": "brute_force_attempt",
                "message": f"窗口内检测到 {len(failed_auths)} 次失败认证尝试",
                "count": len(failed_auths),
                "latest_ts": max(r["ts"] for r in failed_auths),
            })

        # 规则 2：机器指纹不匹配（可能换机器或伪造）
        fingerprint_mismatches = [r for r in records
                                   if r["action"] == "auth"
                                   and r.get("reason") == "fingerprint_mismatch"]
        if fingerprint_mismatches:
            alerts.append({
                "severity": "medium",
                "rule": "fingerprint_mismatch",
                "message": f"检测到 {len(fingerprint_mismatches)} 次机器指纹不匹配",
                "count": len(fingerprint_mismatches),
            })

        # 规则 3：恢复密钥使用（敏感操作）
        recover_events = [r for r in records if r["action"] == "recover"]
        if recover_events:
            alerts.append({
                "severity": "medium",
                "rule": "recovery_key_used",
                "message": f"检测到 {len(recover_events)} 次恢复密钥使用",
                "count": len(recover_events),
            })

        # 规则 4：异常时间访问（凌晨 2-5 点）
        odd_hour_gets = [r for r in records
                         if r["action"] == "get"
                         and r["success"]
                          and 2 <= (time.localtime(r["ts"]).tm_hour) <= 5]
        if len(odd_hour_gets) >= 3:
            alerts.append({
                "severity": "low",
                "rule": "odd_hour_access",
                "message": f"检测到 {len(odd_hour_gets)} 次凌晨时段凭证读取",
                "count": len(odd_hour_gets),
            })

        return {"status": "ok", "alerts": alerts, "window_seconds": window_seconds,
                "record_count": len(records)}

    # ── list_machines ──
    def list_machines(self, token: str) -> dict:
        """列出当前身份绑定的所有机器。"""
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        with self._db() as conn:
            rows = conn.execute(
                "SELECT id, name, fingerprint, registered_at, last_seen_at "
                "FROM machines WHERE identity_id=?",
                (identity_id,),
            ).fetchall()

        machines = []
        current_fp = self._machine_fingerprint()
        for mid, name, fp, reg, seen in rows:
            machines.append({
                "machine_id": mid,
                "name": name,
                "fingerprint": fp,
                "registered_at": reg,
                "last_seen_at": seen,
                "is_current": fp == current_fp,
            })
        return {"status": "ok", "count": len(machines), "machines": machines}

    # ── cleanup_rotated_backups ──
    def cleanup_rotated_backups(self) -> dict:
        """清理过期的轮换备份（保留 7 天）。可外部定时任务调用。"""
        now = int(time.time())
        with self._db() as conn:
            conn.execute("DELETE FROM rotated_backups WHERE expires_at <= ?", (now,))
            deleted = conn.total_changes
        return {"status": "ok", "deleted": deleted}

    # ── audit_log ──
    def audit_log(self, token: str, limit: int = 100) -> dict:
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期"}

        identity_id = sess["identity_id"]
        records = []
        if os.path.isfile(self.audit_path):
            with open(self.audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("identity_id") == identity_id:
                        records.append(rec)
        records = records[-limit:]
        return {"status": "ok", "count": len(records), "logs": records}

    # ── status ──
    def status(self, token: str = None) -> dict:
        """密钥库状态。

        审计修复（P3 元数据泄露 + ③ L1 加固提示）：
          * 改前**无需任何认证**就返回 identities/secrets/legacy_secrets/
            active_sessions —— 本机任意进程都能枚举"有没有密钥库、存了几条、
            几个会话"。现在无 token 只返回 `initialized`/`vault_dir`/迁移状态；
            计数必须带有效 session token。
          * token 有效时额外返回 L1 身份告警（③）：L1 没有动态码第二因子，
            拿到 db 文件即可解出全部 secrets（审计实测），建议升级 L2/L3。

        `key_protection`（keyring / passphrase / file-key / legacy-plaintext /
        unavailable）无需认证即可看 —— 它是"这库现在靠什么保护"的诊断信息，
        不含密钥本身；`key_protection_warning` 说明该方式的边界。
        """
        # 三种状态必须能区分（lead 第 17 轮硬要求）：
        #   missing —— 库文件不存在（= 没有密钥；**本方法绝不建库**）
        #   corrupt —— 文件在但打不开/表缺失（不能当成"空库"糊过去）
        #   empty   —— 库在且可读，但零身份（已初始化、还没注册）
        #   ok      —— 库在、可读、有身份
        exists = os.path.isfile(self.db_path)
        if exists:
            try:
                self._ensure_ready()      # 幂等：只为解析 key_protection（不新建库）
            except Exception:             # noqa: BLE001 —— 损坏库交给下面的 corrupt 分支
                pass
        state = "missing"
        state_detail = ""
        if exists:
            try:
                with self._db() as conn:
                    row = conn.execute("SELECT COUNT(*) FROM identities").fetchone()
                state = "ok" if (row and row[0]) else "empty"
            except Exception as exc:                       # noqa: BLE001
                state = "corrupt"
                state_detail = "%s: %s" % (type(exc).__name__, exc)
        base = {
            "status": "ok",
            "initialized": exists,
            "exists": exists,
            "state": state,
            "vault_dir": self.vault_dir,
            "key_protection": self.key_protection,
        }
        if state_detail:
            base["state_detail"] = state_detail
        # ── KEK 轮换诊断（第 0 步，**纯读**）──
        # kek_gen：该库所有身份的代数**最小值**（有任何一个身份还停在旧代就报旧代，
        #   便于"还没轮换完"的诊断）；空库/missing 时为 0。
        # kek_retired_count：`kek_retired` 里 cleaned=0 的行数（未清理的旧代数量，应为 0）。
        # kek_rotation_supported：当前保护模式能否轮换 KEK（keyring / passphrase /
        #   file-key 都支持；unavailable / legacy-plaintext 不支持）。
        base["kek_gen"] = 0
        base["kek_gen_max"] = 0
        base["kek_retired_count"] = 0
        base["kek_rotation_supported"] = self.key_protection in (
            PROTECTION_KEYRING, PROTECTION_PASSPHRASE, PROTECTION_FILE)
        if exists and state != "corrupt":
            try:
                with self._db() as conn:
                    metas = [r[0] for r in conn.execute(
                        "SELECT key_meta FROM identities").fetchall()]
                    try:
                        pending = conn.execute(
                            "SELECT COUNT(*) FROM kek_retired WHERE cleaned=0").fetchone()[0]
                    except sqlite3.Error:
                        # 极旧的库还没跑到 _init_schema 的建表分支（理论不可达：
                        # _ensure_ready 已先建）—— 不把只读诊断变成错误
                        pending = 0
                gens = [kek_gen_of_meta(m) for m in metas] or [KEK_GEN_DEFAULT]
                base["kek_gen"] = min(gens)
                base["kek_gen_max"] = max(gens)
                base["kek_retired_count"] = int(pending or 0)
            except sqlite3.Error as exc:                   # noqa: BLE001
                base["kek_diag_error"] = "%s: %s" % (type(exc).__name__, exc)
        if self.key_protection_warning:
            base["key_protection_warning"] = self.key_protection_warning
        if self.migrated_key_protection:
            base["migrated_key_protection"] = self.migrated_key_protection
        if self.migrated_from:
            base["migrated_from"] = self.migrated_from
        if self.migration_conflict:
            base["migration_conflict"] = self.migration_conflict
        if not token:
            # 未认证：只给"初始化没初始化"，不泄露计数
            return base

        ok, _sess = self._verify_token(token)
        if not ok:
            base.update({"status": "error", "message": "会话无效或已过期"})
            return base

        identity_count = secret_count = legacy_count = l1_count = 0
        if exists:
            with self._db() as conn:
                identity_count = conn.execute("SELECT COUNT(*) FROM identities").fetchone()[0]
                secret_count = conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0]
                legacy_count = conn.execute(
                    "SELECT COUNT(*) FROM secrets WHERE key_salt IS NULL"
                ).fetchone()[0]
                l1_count = conn.execute(
                    "SELECT COUNT(*) FROM identities WHERE security_level='L1'"
                ).fetchone()[0]
        base.update({
            "identities": identity_count,
            "secrets": secret_count,
            "legacy_secrets": legacy_count,
            "active_sessions": len(self._sessions),
            "l1_identities": l1_count,
        })
        warnings = []
        if l1_count:
            warnings.append(
                "L1 身份无第二因子：拿到 vault2.db 文件即可解出全部 secrets"
                "（seed_key 与库同文件），建议升级到 L2/L3 或改用外部密钥保护")
        if legacy_count:
            warnings.append("存在 %d 条旧格式（无行级密钥）secret，建议运行迁移"
                            % legacy_count)
        if warnings:
            base["warnings"] = warnings
        return base

    # ── 懒迁移：公共方法（供外部触发批量迁移） ──
    def migrate_legacy_secrets(self, token: str) -> dict:
        """批量将所有旧格式 secret 升级为行级加密格式。"""
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]
        migrated = 0
        failed_names: List[str] = []

        with self._db() as conn:
            rows = conn.execute(
                "SELECT name, value, secret_type, security_level, expires_at, metadata "
                "FROM secrets WHERE identity_id=? AND key_salt IS NULL",
                (identity_id,),
            ).fetchall()

            for name, value_enc, stype, level, expires, meta_json in rows:
                try:
                    # 旧格式一律用 fernet + master_key 直接解密
                    backend = _make_backend("fernet", master_key)
                    plaintext = backend.decrypt(value_enc)

                    # 用新格式重新加密
                    row_salt = secrets.token_bytes(16)
                    row_key = _derive_row_key(master_key, row_salt)
                    new_backend = _make_backend(DEFAULT_CIPHER_ALG, row_key)
                    new_encrypted = new_backend.encrypt(plaintext)

                    conn.execute(
                        "UPDATE secrets SET value=?, cipher_alg=?, key_salt=?, "
                        "key_iters=?, key_dklen=?, last_rotated_at=? "
                        "WHERE identity_id=? AND name=?",
                        (new_encrypted, DEFAULT_CIPHER_ALG, row_salt.hex(),
                         DEFAULT_ROW_ITERS, DEFAULT_ROW_DKLEN, int(time.time()),
                         identity_id, name),
                    )
                    migrated += 1
                except Exception:
                    failed_names.append(name)

        failed = len(failed_names)
        self._audit("migrate_legacy", identity_id, sess["machine_id"],
                    success=(failed == 0),
                    reason="migrated=%d, failed=%d" % (migrated, failed))
        result = {"migrated": migrated, "failed": failed,
                  "failed_names": failed_names}
        if failed:
            # 审计修复（④ 假成功）：改前 failed>0 仍返回 status=ok
            # （实测 {"status":"ok","migrated":0,"failed":1}），调用方会误判
            # "旧格式已全部升级"。现在有失败即 error，并点名失败条目。
            result.update({
                "status": "error",
                "message": "有 %d 条旧格式 secret 迁移失败（密文损坏或密钥不匹配），"
                           "未迁移的条目仍保持旧格式" % failed,
            })
        else:
            result["status"] = "ok"
        return result


# ── 模块级便捷函数（单例） ──
_vault2_singleton: Optional[Vault2] = None


def _get_vault2(create: bool = False) -> Vault2:
    """进程内单例。**构造本身零文件系统操作**（懒创建，见 `Vault2.__init__`），
    所以这里返回实例**不会**凭空建库 —— 建库只发生在写路径（`register()` 或
    首次 `_ensure_ready()`）。

    `create=True` 仅表达"这个调用方是注册流程"，保留给显式语义；实际建库仍由
    `register()` 内部的 `_ensure_ready()` 完成（单一入口，避免两套建库逻辑）。
    """
    global _vault2_singleton
    if _vault2_singleton is None:
        _vault2_singleton = Vault2()
    if create:
        _vault2_singleton._ensure_ready()
    return _vault2_singleton


def register(identity_name: str, pin: str, machine_name: str = None,
             security_level: str = "L2") -> dict:
    return _get_vault2().register(identity_name, pin, machine_name, security_level)


def auth(identity_id: str, machine_id: str, pin: str, hardware_token: str = None) -> dict:
    return _get_vault2().auth(identity_id, machine_id, pin, hardware_token)


def get_secret(token: str, name: str, caller: str = None,
               read_only: bool = False) -> dict:
    return _get_vault2().get_secret(token, name, caller, read_only=read_only)


def set_secret(token: str, name: str, value: str, secret_type: str = "api_key",
               security_level: str = None, expires_at: int = None,
               rotate_interval_days: int = None, metadata: dict = None,
               caller: str = None, cipher_alg: str = None) -> dict:
    return _get_vault2().set_secret(token, name, value, secret_type, security_level,
                                    expires_at, rotate_interval_days, metadata, caller, cipher_alg)


def list_secrets(token: str) -> dict:
    return _get_vault2().list_secrets(token)


def audit_log(token: str, limit: int = 100) -> dict:
    return _get_vault2().audit_log(token, limit)


def status(token: str = None) -> dict:
    """密钥库状态：无 token 只返回 initialized/vault_dir；计数需 token。"""
    return _get_vault2().status(token)


def migrate_legacy_secrets(token: str) -> dict:
    return _get_vault2().migrate_legacy_secrets(token)


def recover(identity_id: str, recovery_key: str, new_pin: str) -> dict:
    return _get_vault2().recover(identity_id, recovery_key, new_pin)


def delete_secret(token: str, name: str, caller: str = None) -> dict:
    return _get_vault2().delete_secret(token, name, caller)


def rotate_seed_key(token: str, caller: str = None) -> dict:
    return _get_vault2().rotate_seed_key(token, caller)


def rotate_secret(token: str, name: str, new_value: str = None, caller: str = None) -> dict:
    return _get_vault2().rotate_secret(token, name, new_value, caller)


def rollback_secret(token: str, name: str, backup_id: str = None, caller: str = None) -> dict:
    return _get_vault2().rollback_secret(token, name, backup_id, caller)


def cleanup_rotated_backups() -> dict:
    return _get_vault2().cleanup_rotated_backups()


def resolve_vault_refs(token: str, secrets_config: List[dict],
                       read_only: bool = False) -> dict:
    return _get_vault2().resolve_vault_refs(token, secrets_config,
                                            read_only=read_only)


def migrate_legacy_rows(token: str) -> dict:
    """**显式**迁移 legacy 行（key_salt 为空）→ 行级加密。

    第 14 轮：读路径（get_secret(read_only=True)）不再顺手迁移；需要迁移时
    由调用方/运维显式触发本函数（或走会把 read_only=False 的写入口）。
    """
    return _get_vault2().migrate_legacy_rows(token)


def anomaly_check(token: str, window_seconds: int = 3600) -> dict:
    return _get_vault2().anomaly_check(token, window_seconds)


def list_machines(token: str) -> dict:
    return _get_vault2().list_machines(token)


