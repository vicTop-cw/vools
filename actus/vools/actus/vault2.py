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

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import struct
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
DEFAULT_VAULT_DIR = os.path.join(os.getcwd(), "_meta", "vault")
DEFAULT_TIME_STEP = 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 900
SESSION_TTL = {"L1": 900, "L2": 600, "L3": 300}

# 行级密钥派生默认参数（master_key 已是高熵，无需 10 万轮）
DEFAULT_ROW_ITERS = 1000
DEFAULT_ROW_DKLEN = 32
DEFAULT_CIPHER_ALG = "fernet"
CIPHER_ALG_WHITELIST = {"fernet", "xor-hmac"}  # aes-gcm 后续加入


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


# ── Vault2 ──
class Vault2:
    def __init__(self, vault_dir: str = None):
        self.vault_dir = vault_dir or DEFAULT_VAULT_DIR
        os.makedirs(self.vault_dir, exist_ok=True)
        self.db_path = os.path.join(self.vault_dir, "vault2.db")
        self.audit_path = os.path.join(self.vault_dir, "audit.log")
        self._init_schema()
        self._sessions: Dict[str, dict] = {}

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
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
                """
            )

    def _audit(self, action: str, identity_id: str = None, machine_id: str = None,
               target: str = None, success: bool = True, reason: str = None, caller: str = None):
        record = {"ts": int(time.time()), "action": action, "identity_id": identity_id,
                  "machine_id": machine_id, "target": target, "success": success,
                  "reason": reason, "caller": caller}
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

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

        identity_id = str(uuid.uuid4())
        machine_id = str(uuid.uuid4())
        salt = secrets.token_bytes(16)
        pin_hash = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100000)
        seed_key = generate_seed_key(32)
        key_salt = secrets.token_bytes(16)  # 主密钥派生盐，recover 不变
        fingerprint = self._machine_fingerprint()
        recovery_key = self._generate_recovery_key()
        recovery_key_hash = self._hash_recovery_key(recovery_key, seed_key.hex())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO identities (id, name, pin_hash, salt, seed_key, security_level, "
                "recovery_key_hash, key_salt, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identity_id, identity_name, pin_hash.hex(), salt.hex(), seed_key.hex(),
                 security_level, recovery_key_hash, key_salt.hex(), int(time.time())),
            )
            conn.execute(
                "INSERT INTO machines (id, identity_id, fingerprint, name, registered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (machine_id, identity_id, fingerprint, machine_name or "default", int(time.time())),
            )
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
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT pin_hash, salt, seed_key, security_level, failed_attempts, locked_until, key_salt "
                "FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            if not row:
                self._audit("auth", identity_id, machine_id, success=False, reason="identity_not_found")
                return {"status": "error", "message": "身份不存在"}

            pin_hash_hex, salt_hex, seed_key_hex, level, failed, locked, key_salt_hex = row
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

            effective_dynamic = "" if level == "L1" else dynamic_code
            if key_salt_hex:
                # 主密钥由 seed_key + dynamic_code + key_salt 派生。
                # seed_key / key_salt 注册时生成、recover 不改变，
                # 因此 recover 重置 PIN 后历史 secrets 仍可解密。
                master_key = derive_master_key(
                    seed_key_hex, effective_dynamic, bytes.fromhex(key_salt_hex)
                )
            else:
                # 旧身份（无 key_salt）：回退为 pin 派生（向后兼容）
                master_key = derive_master_key(pin, effective_dynamic, bytes.fromhex(salt_hex))

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
            return {"status": "ok", "dynamic_code": dynamic_code if level != "L1" else "",
                    "expires_in": DEFAULT_TIME_STEP, "session_token": token,
                    "security_level": level}

    # ── recover（恢复密钥重置 PIN） ──
    def recover(self, identity_id: str, recovery_key: str, new_pin: str) -> dict:
        if not (new_pin and new_pin.isdigit() and len(new_pin) == 6):
            return {"status": "error", "message": "新 PIN 必须是 6 位数字"}

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT salt, seed_key, recovery_key_hash, security_level "
                "FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            if not row:
                self._audit("recover", identity_id, success=False, reason="identity_not_found")
                return {"status": "error", "message": "身份不存在"}

            salt_hex, seed_key_hex, rk_hash, level = row
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
    def get_secret(self, token: str, name: str, caller: str = None) -> dict:
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value, secret_type, security_level, expires_at, metadata, "
                "cipher_alg, key_salt, key_iters, key_dklen "
                "FROM secrets WHERE identity_id=? AND name=?",
                (identity_id, name),
            ).fetchone()
            if not row:
                self._audit("get", identity_id, sess["machine_id"], target=name,
                           success=False, reason="not_found", caller=caller)
                return {"status": "error", "message": "凭证不存在"}

            (value_enc, stype, level, expires, meta_json,
             cipher_alg, key_salt_hex, key_iters, key_dklen) = row

            if expires and int(time.time()) > expires:
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
                self._audit("get", identity_id, sess["machine_id"], target=name,
                           success=False, reason=f"decrypt_error: {e}", caller=caller)
                return {"status": "error", "message": "凭证解密失败（密钥错误？）"}

            # 懒迁移：旧格式读取成功后自动升级为行级加密
            if is_legacy:
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
            self._audit("get", identity_id, sess["machine_id"], target=name,
                       success=True, caller=caller)
            return {"status": "ok", "name": name, "value": value,
                    "type": stype, "security_level": level,
                    "expires_at": expires, "metadata": metadata}

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

        with sqlite3.connect(self.db_path) as conn:
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
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期"}

        identity_id = sess["identity_id"]
        with sqlite3.connect(self.db_path) as conn:
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
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        with sqlite3.connect(self.db_path) as conn:
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
    def rotate_secret(self, token: str, name: str, new_value: str = None,
                      caller: str = None) -> dict:
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]

        with sqlite3.connect(self.db_path) as conn:
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
                "SELECT seed_key FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            seed_key_bytes = bytes.fromhex(seed_row[0]) if seed_row else b""
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

        with sqlite3.connect(self.db_path) as conn:
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
                "SELECT seed_key FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            seed_key_bytes = bytes.fromhex(seed_row[0]) if seed_row else b""
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
    def resolve_vault_refs(self, token: str, secrets_config: List[dict]) -> dict:
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
            result = self.get_secret(token, secret_name, caller="vault.resolve")
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
        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
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
    def status(self) -> dict:
        exists = os.path.isfile(self.db_path)
        identity_count = 0
        secret_count = 0
        legacy_count = 0
        if exists:
            with sqlite3.connect(self.db_path) as conn:
                identity_count = conn.execute("SELECT COUNT(*) FROM identities").fetchone()[0]
                secret_count = conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0]
                legacy_count = conn.execute(
                    "SELECT COUNT(*) FROM secrets WHERE key_salt IS NULL"
                ).fetchone()[0]
        return {
            "status": "ok",
            "initialized": exists,
            "identities": identity_count,
            "secrets": secret_count,
            "legacy_secrets": legacy_count,
            "active_sessions": len(self._sessions),
        }

    # ── 懒迁移：公共方法（供外部触发批量迁移） ──
    def migrate_legacy_secrets(self, token: str) -> dict:
        """批量将所有旧格式 secret 升级为行级加密格式。"""
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期"}

        identity_id = sess["identity_id"]
        master_key = sess["master_key"]
        migrated = 0
        failed = 0

        with sqlite3.connect(self.db_path) as conn:
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
                    failed += 1

        self._audit("migrate_legacy", identity_id, sess["machine_id"],
                   success=(failed == 0), reason=f"migrated={migrated}, failed={failed}")
        return {"status": "ok", "migrated": migrated, "failed": failed}


# ── 模块级便捷函数（单例） ──
_vault2_singleton: Optional[Vault2] = None


def _get_vault2() -> Vault2:
    global _vault2_singleton
    if _vault2_singleton is None:
        _vault2_singleton = Vault2()
    return _vault2_singleton


def register(identity_name: str, pin: str, machine_name: str = None,
             security_level: str = "L2") -> dict:
    return _get_vault2().register(identity_name, pin, machine_name, security_level)


def auth(identity_id: str, machine_id: str, pin: str, hardware_token: str = None) -> dict:
    return _get_vault2().auth(identity_id, machine_id, pin, hardware_token)


def get_secret(token: str, name: str, caller: str = None) -> dict:
    return _get_vault2().get_secret(token, name, caller)


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


def status() -> dict:
    return _get_vault2().status()


def migrate_legacy_secrets(token: str) -> dict:
    return _get_vault2().migrate_legacy_secrets(token)


def recover(identity_id: str, recovery_key: str, new_pin: str) -> dict:
    return _get_vault2().recover(identity_id, recovery_key, new_pin)


def delete_secret(token: str, name: str, caller: str = None) -> dict:
    return _get_vault2().delete_secret(token, name, caller)


def rotate_secret(token: str, name: str, new_value: str = None, caller: str = None) -> dict:
    return _get_vault2().rotate_secret(token, name, new_value, caller)


def rollback_secret(token: str, name: str, backup_id: str = None, caller: str = None) -> dict:
    return _get_vault2().rollback_secret(token, name, backup_id, caller)


def cleanup_rotated_backups() -> dict:
    return _get_vault2().cleanup_rotated_backups()


def resolve_vault_refs(token: str, secrets_config: List[dict]) -> dict:
    return _get_vault2().resolve_vault_refs(token, secrets_config)


def anomaly_check(token: str, window_seconds: int = 3600) -> dict:
    return _get_vault2().anomaly_check(token, window_seconds)


def list_machines(token: str) -> dict:
    return _get_vault2().list_machines(token)


def reset_singleton():
    global _vault2_singleton
    _vault2_singleton = None
