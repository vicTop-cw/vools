"""vault.py —— 密钥保险库（docs/10 §D）。

为动作提供加密的密钥/密码/API token 存储。
存储位置：_meta/vault/keys.json（加密后）+ _meta/vault/meta.json（明文元数据）

加密策略：
- 首选 Fernet（cryptography 库）
- 回退 XOR + HMAC-SHA256（无外部依赖）
- 主密钥从环境变量 ACTUS_VAULT_KEY 获取；没有时生成一把**临时密钥**，
  它只在本进程内有效。密文要长期存，临时密钥存不了 —— 所以落盘入口
  （CLI `vault set` / MCP actus_vault_set）在 Vault.ephemeral_key 为真时一律拒绝写入，
  而不是回一个「ok」再把永远解不开的密文留在磁盘上（BUG-0009）。

API：
- set(key, value, scope='global') → 加密存储
- get(key, scope='global') → 解密返回
- inspect(key, scope='global') → 'ok' | 'absent' | 'undecryptable'（钥匙错不得谎报成不存在）
- delete(key, scope='global') → 删除
- list(scope=None) → 列出密钥元数据
- resolve_secrets(action) → 解析动作的 secrets 字段并注入实际值
"""

__all__ = ['Vault', 'default_meta_dir', 'set_key', 'get_key', 'delete_key',
           'list_keys', 'resolve_secrets',
           # 统一 secret resolver（第 12 轮：v2 优先 / v1 兼容读）
           'resolve_secret', 'write_secret', 'resolve_vault_refs',
           'resolver_status',
           # 合并清单 / 删除（第 12 轮收尾：CLI/MCP 不再依赖私有 _v2_session）
           'list_secret_names', 'delete_secret']

import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import struct
import tempfile
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 加密后端 ──

class _FernetBackend:
    """基于 Fernet 的加密后端（推荐）。"""

    def __init__(self, master_key: str):
        from cryptography.fernet import Fernet
        # 从主密钥派生 Fernet key（32 url-safe base64-encoded bytes）
        key_bytes = hashlib.sha256(master_key.encode('utf-8')).digest()
        import base64
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')


class _XorHmacBackend:
    """回退加密：XOR + HMAC-SHA256（无外部依赖，安全性较低）。"""

    def __init__(self, master_key: str):
        self._key = hashlib.sha256(master_key.encode('utf-8')).digest()

    def encrypt(self, plaintext: str) -> str:
        data = plaintext.encode('utf-8')
        # 生成随机 nonce
        nonce = secrets.token_bytes(16)
        # XOR 加密
        key_stream = self._generate_key_stream(nonce, len(data))
        encrypted = bytes(a ^ b for a, b in zip(data, key_stream))
        # HMAC
        mac = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        # 打包：nonce(16) + mac(32) + encrypted
        packed = nonce + mac + encrypted
        import base64
        return 'xor:' + base64.b64encode(packed).decode('utf-8')

    def decrypt(self, ciphertext: str) -> str:
        if ciphertext.startswith('xor:'):
            ciphertext = ciphertext[4:]
        import base64
        packed = base64.b64decode(ciphertext)
        nonce, mac, encrypted = packed[:16], packed[16:48], packed[48:]
        # 验证 HMAC
        expected_mac = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError('Vault 解密失败：HMAC 不匹配（密钥错误或数据损坏）')
        # XOR 解密
        key_stream = self._generate_key_stream(nonce, len(encrypted))
        decrypted = bytes(a ^ b for a, b in zip(encrypted, key_stream))
        return decrypted.decode('utf-8')

    def _generate_key_stream(self, nonce: bytes, length: int) -> bytes:
        """基于 nonce 生成密钥流（SHA256 链）。"""
        stream = b''
        counter = 0
        while len(stream) < length:
            block = hashlib.sha256(self._key + nonce + struct.pack('>I', counter)).digest()
            stream += block
            counter += 1
        return stream[:length]


def _make_backend(master_key: str):
    """自动选择加密后端。"""
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        return _FernetBackend(master_key)
    except ImportError:
        return _XorHmacBackend(master_key)


# ── 保险库 ──

_EPHEMERAL_MASTER_KEYS = set()   # 本进程自造过的临时主密钥（一次性，落盘即作废）


class Vault:
    """密钥保险库。

    存储结构：
    - _meta/vault/keys.json: {scope: {key: encrypted_value}}
    - _meta/vault/meta.json: {scope: {key: {created_at, updated_at, description}}}
    """

    def __init__(self, meta_dir: str, master_key: Optional[str] = None,
                 migrate_legacy: Optional[bool] = None):
        """
        参数:
            meta_dir: 仓库 _meta 目录路径。
            master_key: 加密主密钥（缺省从 ACTUS_VAULT_KEY 环境变量获取）。
            migrate_legacy: 是否把旧位置的保险库迁到 `meta_dir/vault`。
                None（默认）= 自动：不在测试环境下才迁移（测试绝不搬真实用户数据），
                True/False 可强制。迁移结果记在 `migrated_from` / `migration_conflict`。
        """
        self._vault_dir = os.path.join(meta_dir, 'vault')
        os.makedirs(self._vault_dir, exist_ok=True)
        # 旧位置探测/迁移必须在**读取数据之前**做，否则读到的是空库。
        self.migrated_from: Optional[str] = None
        self.migration_conflict: Optional[str] = None
        self.last_refusal: Optional[dict] = None
        self._maybe_migrate_legacy(migrate_legacy)

        if master_key is None:
            master_key = os.environ.get('ACTUS_VAULT_KEY')
        # 「本进程用没用过自造钥匙」必须跨实例认得出来：临时钥匙会写回
        # os.environ，同进程下一次 Vault() 从环境里读到它，看着像用户配的钥匙 ——
        # 于是长驻 MCP server 里的第二次 set 又会把永远解不开的密文落盘。
        self.ephemeral_key = master_key in _EPHEMERAL_MASTER_KEYS
        if not master_key:
            # 生成临时密钥（仅当前会话有效）
            master_key = secrets.token_hex(32)
            _EPHEMERAL_MASTER_KEYS.add(master_key)
            self.ephemeral_key = True
            os.environ['ACTUS_VAULT_KEY'] = master_key

        self._backend = _make_backend(master_key)
        self._keys_path = os.path.join(self._vault_dir, 'keys.json')
        self._meta_path = os.path.join(self._vault_dir, 'meta.json')
        self._keys_data: Dict[str, Dict[str, str]] = self._load(self._keys_path)
        self._meta_data: Dict[str, Dict[str, dict]] = self._load(self._meta_path)
        #: 最近一次 get() 的取值来源（'v1' / 'v2' / None）—— 供上层诊断"这份密钥
        #: 到底来自哪个库"（第 12 轮统一 resolver 的兼容读会填 'v2'）。
        self.last_read_source: Optional[str] = None
        #: 最近一次写操作被拒的原因（临时密钥守卫等）；None = 未被拒。
        self.last_refusal: Optional[dict] = None

    @staticmethod
    def _load(path: str) -> dict:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    # ── 旧位置探测 / 迁移（audit 第 25 轮：路径来源统一到 paths.meta_dir 之后）──

    @staticmethod
    def _legacy_vault_candidates() -> List[str]:
        """历史 v1 保险库可能出现过的旧位置（真实路径去重，按可能性排序）。

        1. `<repo_root>/_meta/vault` —— 未设 ACTUS_META_DIR 时的常规位置；
        2. `<cwd>/_meta/vault`     —— 旧版 `join(_, '_meta')` 跟 shell 走的时代；
        3. `<cwd>/vault`           —— BUG-0010：`join('', 'vault')` 的相对产物。
        """
        from .paths import repo_root as _paths_repo_root
        raw = [
            os.path.join(_paths_repo_root(), '_meta', 'vault'),
            os.path.join(os.getcwd(), '_meta', 'vault'),
            os.path.join(os.getcwd(), 'vault'),
        ]
        seen, out = set(), []
        for cand in raw:
            real = os.path.realpath(cand)
            if real not in seen:
                seen.add(real)
                out.append(cand)
        return out

    def _maybe_migrate_legacy(self, migrate_legacy: Optional[bool]) -> None:
        """新位置为空、旧位置有数据时把旧库**移动**过来（不复制、不合并）。

        与 `vault2._maybe_migrate_legacy()` 同款规则：
          * 新位置本身就是常规位置（未设 ACTUS_META_DIR）→ 什么都不做；
          * 旧有/新空 → 迁移（`shutil.move`），记 `migrated_from`；
          * 两边都有 → 不合并，记 `migration_conflict`（ambiguous），交人处理；
          * 只在**非测试环境**自动迁移（测试绝不允许搬动真实用户的保险库 —— 这与会
            把我们自己的数据搬走的其它事故同族），也可用 `ACTUS_VAULT_MIGRATE=1`
            或显式参数强制。
        """
        target = os.path.realpath(self._vault_dir)
        candidates = self._legacy_vault_candidates()
        if any(os.path.realpath(c) == target for c in candidates):
            return                       # 新位置就是常规位置：零影响，无需迁移

        legacy = None
        for cand in candidates:
            if os.path.isdir(cand) and os.listdir(cand):
                legacy = cand
                break
        if legacy is None:
            return

        if os.path.isdir(self._vault_dir) and os.listdir(self._vault_dir):
            self.migration_conflict = (
                'ambiguous: 新旧保险库同时存在，未自动合并（旧=%s，新=%s）'
                '—— 请人工确认保留哪一份' % (legacy, self._vault_dir))
            return

        if migrate_legacy is None:
            in_test = bool(os.environ.get('PYTEST_CURRENT_TEST')
                           or os.environ.get('ACTUS_TEST_MODE'))
            migrate_legacy = (os.environ.get('ACTUS_VAULT_MIGRATE') == '1') or not in_test
        if not migrate_legacy:
            self.migration_conflict = (
                'pending: 检测到旧位置保险库 %s（新位置为空），自动迁移已跳过'
                '（测试环境）；可设 ACTUS_VAULT_MIGRATE=1 或人工搬迁' % legacy)
            return

        try:
            os.rmdir(self._vault_dir)     # 空目录：让 move 直接落位
            os.makedirs(os.path.dirname(self._vault_dir), exist_ok=True)
            shutil.move(legacy, self._vault_dir)
            self.migrated_from = legacy
        except OSError as exc:
            self.migration_conflict = 'migrate_failed: %s（旧=%s，新=%s）' % (
                exc, legacy, self._vault_dir)

    def status(self) -> dict:
        """保险库状态（迁移/密钥可用性），供校验与排障。"""
        return {
            'vault_dir': self._vault_dir.replace(os.sep, '/'),
            'ephemeral_key': bool(self.ephemeral_key),
            'writable': not self.ephemeral_key,
            'keys_count': sum(len(v) for v in self._keys_data.values()),
            'migrated_from': self.migrated_from,
            'migration_conflict': self.migration_conflict,
        }

    def _refuse_if_ephemeral(self) -> Optional[dict]:
        """临时主密钥下拒绝写盘（audit 第 25 轮：兑现 docstring 承诺）。

        改前 `ephemeral_key` **只被赋值、零读取** —— 未配置 ACTUS_VAULT_KEY 时
        `set()` 照样返回 `{'status':'ok'}` 并把密文落盘，而主密钥是进程级临时值，
        下次启动就解不开了（实测：进程 A set→ok，进程 B get→None、inspect→
        undecryptable）。密文永久不可解，属**不可逆数据损失**，必须拒绝。
        """
        if not getattr(self, 'ephemeral_key', False):
            return None
        return {
            'status': 'refused',
            'code': 'vault_ephemeral_key',
            'message': ('未配置 ACTUS_VAULT_KEY，拒绝写入：当前用的是本进程临时密钥，'
                        '写进去的密文重启后永远解不开（请先设置 ACTUS_VAULT_KEY）'),
        }

    @staticmethod
    def _atomic_write(path: str, data) -> None:
        """原子写：同目录临时文件 + `os.replace`（Windows 亦原子）。

        改前直接 `open(path, 'w') + json.dump`：崩在中间会留下截断的半份 JSON，
        下次 `_load` 抛 JSONDecodeError 或读到残缺映射 —— 密钥文件损坏是灾难级。
        """
        directory = os.path.dirname(path) or '.'
        fd, tmp_path = tempfile.mkstemp(prefix='.vault-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _save(self):
        """原子写盘。

        **两份文件的顺序（判断）**：先 `keys.json`（密文真相），后 `meta.json`（描述）。
        崩在两次 replace 之间时最坏结果是「密钥可用但描述/时间戳是旧的」；
        反过来先写 meta 则会出现「列表里看得见、get 却拿不到」的幽灵条目，
        那是更坏的假象（看起来存在、实际不存在）。所以 keys 先落。
        """
        self._atomic_write(self._keys_path, self._keys_data)
        self._atomic_write(self._meta_path, self._meta_data)

    def set(self, key: str, value: str, scope: str = 'global',
            description: str = '') -> dict:
        """加密存储密钥。

        返回:
            {'status': 'ok', 'key': ..., 'scope': ...}；未配置主密钥时
            {'status': 'refused', 'code': 'vault_ephemeral_key', ...}（不写盘）。
        """
        refused = self._refuse_if_ephemeral()
        if refused is not None:
            return refused

        # 快照（写盘失败时回滚内存，避免"内存已改、磁盘没改"，下次别的操作把半截写进去）
        prev_value = self._keys_data.get(scope, {}).get(key)
        prev_meta = self._meta_data.get(scope, {}).get(key)

        if scope not in self._keys_data:
            self._keys_data[scope] = {}
        if scope not in self._meta_data:
            self._meta_data[scope] = {}

        encrypted = self._backend.encrypt(value)
        self._keys_data[scope][key] = encrypted

        now = time.time()
        meta = {
            'created_at': now,
            'updated_at': now,
            'description': description,
        }
        if key in self._meta_data[scope]:
            meta['created_at'] = self._meta_data[scope][key].get('created_at', now)
        self._meta_data[scope][key] = meta

        try:
            self._save()
        except Exception as exc:              # noqa: BLE001 —— 落盘失败必须停止并回滚
            if prev_value is None:
                self._keys_data.get(scope, {}).pop(key, None)
            else:
                self._keys_data.setdefault(scope, {})[key] = prev_value
            if prev_meta is None:
                self._meta_data.get(scope, {}).pop(key, None)
            else:
                self._meta_data.setdefault(scope, {})[key] = prev_meta
            return {'status': 'failed', 'code': 'vault_write_failed',
                    'message': f'保险库写入失败（已回滚内存，磁盘未改动）: {exc}'}
        return {'status': 'ok', 'key': key, 'scope': scope}

    def get(self, key: str, scope: str = 'global',
            _allow_v2_fallback: bool = True) -> Optional[str]:
        """解密获取密钥；v1 里没有时**兼容回退读 v2**（统一 resolver 的读侧）。

        返回:
            密钥值，或 None（两个库都没有）。

        第 12 轮统一 resolver 的兼容读：CLI `vault get` 走的仍是本方法，若只认 v1，
        "resolver 写进 v2 的新密钥"在 CLI 里就永远读不到（这边写、那边读不到）。
        因此 v1 缺失时按需尝试 v2（需要 `VAULT_IDENTITY_ID/MACHINE_ID/PIN` 且 v2
        可用；否则静默跳过，不报错）。`last_read_source` 记录来源。

        注意：**只回退读、不回退写** —— v1 的写入口保持原样（临时密钥守卫不变）。
        """
        encrypted = self._keys_data.get(scope, {}).get(key)
        if encrypted is None:
            if _allow_v2_fallback and _resolver_enabled():
                state, value, _reason = _v2_read_secret(key)
                if state == 'found':
                    self.last_read_source = 'v2'
                    return value
            self.last_read_source = None
            return None
        try:
            value = self._backend.decrypt(encrypted)
            self.last_read_source = 'v1'
            return value
        except Exception:
            return None

    def inspect(self, key: str, scope: str = 'global') -> str:
        """密钥的可读性状态：'ok' | 'absent' | 'undecryptable'。

        get() 把「没写过」和「写了但当前主密钥解不开」都返回 None，入口只能回一句
        not_found；而这两件事用户该做的动作完全相反（重新 set vs 去找对的主密钥）。
        """
        encrypted = self._keys_data.get(scope, {}).get(key)
        if encrypted is None:
            return 'absent'
        try:
            self._backend.decrypt(encrypted)
        except Exception:
            return 'undecryptable'
        return 'ok'

    def delete(self, key: str, scope: str = 'global') -> bool:
        """删除密钥。

        返回:
            是否成功删除。

        说明（temp 主密钥）：`delete` 同样是**写操作**，临时密钥下拒绝执行
        （否则会在"读不出内容"的状态下按名字删掉真实密钥 —— 破坏性且不可逆）。
        拒绝时返回 False 并把原因记进 `self.last_refusal`（供上层展示；
        返回 False 与"密钥不存在"的区分由 `last_refusal` 承担）。
        """
        refused = self._refuse_if_ephemeral()
        if refused is not None:
            self.last_refusal = refused
            logger.warning('vault delete 被拒绝: %s', refused['message'])
            return False
        self.last_refusal = None

        existed = False
        if scope in self._keys_data and key in self._keys_data[scope]:
            del self._keys_data[scope][key]
            existed = True
        if scope in self._meta_data and key in self._meta_data[scope]:
            del self._meta_data[scope][key]
        self._save()
        return existed

    def list(self, scope: Optional[str] = None) -> List[dict]:
        """列出密钥元数据（不含值）。

        返回:
            [{'key': ..., 'scope': ..., 'description': ..., 'created_at': ..., 'updated_at': ...}]
        """
        results = []
        scopes = [scope] if scope else list(self._meta_data.keys())
        for s in scopes:
            for key, meta in self._meta_data.get(s, {}).items():
                results.append({
                    'key': key,
                    'scope': s,
                    'description': meta.get('description', ''),
                    'created_at': meta.get('created_at'),
                    'updated_at': meta.get('updated_at'),
                })
        return results

    def resolve_secrets(self, secrets_config: List[dict]) -> Dict[str, str]:
        """解析动作的 secrets 字段（schema 格式：provider + env）。

        支持两种格式：
        - schema 标准格式: [{'provider': 'openai', 'env': 'OPENAI_API_KEY', 'scopes': [...]}]
        - 兼容格式: [{'key': 'MY_API_KEY', 'scope': 'global', 'default': '...'}]

        返回:
            {env_var_name: resolved_value} —— 可直接注入 os.environ
        """
        resolved = {}
        for entry in secrets_config:
            # schema 标准格式
            if 'provider' in entry and 'env' in entry:
                provider = entry['provider']
                env_name = entry['env']
                scopes = entry.get('scopes') or []
                val = self.get(provider)
                if val is None and scopes:
                    # 尝试各 scope 查找
                    for sc in scopes:
                        val = self.get(provider, scope=sc)
                        if val is not None:
                            break
                resolved[env_name] = val if val is not None else ''
            # 兼容格式
            else:
                key = entry.get('key', '')
                scope = entry.get('scope', 'global')
                default = entry.get('default', '')
                val = self.get(key, scope)
                resolved[key] = val if val is not None else default
        return resolved


# ── 便捷函数（模块级单例） ──

_vault_singleton: Optional[Vault] = None


def default_meta_dir() -> str:
    """便捷函数缺省 meta_dir 时的落点：**运行时数据目录真源** `paths.meta_dir()`。

    调用方（executor 注入 secrets 时传的是 `meta_dir or ''`）给空串是常态。

    历史沿革（两次修）：
      1. 旧写法 `os.path.join('', 'vault')` 得到相对路径 'vault'，于是在**当时的
         cwd** 长出空保险库、密钥静默解析成 ''（BUG-0010）；
      2. 之后改成 `ACTUS_REPO_ROOT > _repo_root() > cwd` 再拼 `_meta` —— 修好了 cwd
         问题，但仍**无视 ACTUS_META_DIR**（测试/嵌入式隔离对它无效，会把 vault 写进
         真实仓库的 `_meta/`）。
    现在直接委托 `paths.meta_dir()`（`ACTUS_META_DIR` > `repo_root()/_meta`），
    与全仓其它运行时数据目录同一真源。旧位置的库由 `Vault._maybe_migrate_legacy()`
    探测/迁移，不会因为换路径而"看不见"。
    """
    from .paths import meta_dir as _paths_meta_dir
    return _paths_meta_dir()


def _get_vault(meta_dir: str) -> Vault:
    global _vault_singleton
    if _vault_singleton is None:
        # 便捷函数是"常规运行时路径"，允许探测并迁移旧位置的保险库
        _vault_singleton = Vault(meta_dir or default_meta_dir())
    return _vault_singleton


def set_key(key: str, value: str, scope: str = 'global',
            description: str = '', meta_dir: str = '') -> dict:
    """便捷函数：存储密钥。"""
    vault = _get_vault(meta_dir)
    return vault.set(key, value, scope, description)


def get_key(key: str, scope: str = 'global', meta_dir: str = '') -> Optional[str]:
    """便捷函数：获取密钥。"""
    vault = _get_vault(meta_dir)
    return vault.get(key, scope)


def delete_key(key: str, scope: str = 'global', meta_dir: str = '') -> bool:
    """便捷函数：删除密钥。"""
    vault = _get_vault(meta_dir)
    return vault.delete(key, scope)


def list_keys(scope: Optional[str] = None, meta_dir: str = '') -> List[dict]:
    """便捷函数：列出密钥。"""
    vault = _get_vault(meta_dir)
    return vault.list(scope)


def resolve_secrets(secrets_config: List[dict], meta_dir: str = '') -> Dict[str, str]:
    """便捷函数：解析密钥引用。"""
    vault = _get_vault(meta_dir)
    return vault.resolve_secrets(secrets_config)


# ── 统一 secret resolver（第 12 轮：v2 优先 / v1 兼容读）────────────────
#
# 设计（docs/vault-v1-v2-merge.md §3）：
#   * **读**：先 v2（keyring/passphrase 保护、有审计/轮换），v2 不可用或没有该
#     密钥时回退 v1（老数据兼容）；两边都有但值不同 → **报 conflict，不自动选**。
#   * **写**：默认写 v2；v2 不可用时**拒绝**（除非显式 allow_v1_write=True），
#     绝不静默写进一个将来 resolver 读不到的地方。
#   * **懒迁移**：默认关闭（opt-in `ACTUS_VAULT_LAZY_MIGRATE=1`）。原因见 §3 报告：
#     本轮 CLI 仍直连 v1 写入，若读时自动把 v1 复制到 v2，CLI 之后再改 v1 的值就会
#     与 v2 的旧副本"不同" → 每次读都变冲突；等 CLI 也切到 resolver 后再打开默认迁移。
#   * v2 凭据口径与 executor 既有一致：VAULT_IDENTITY_ID / VAULT_MACHINE_ID / VAULT_PIN。

V2_IDENTITY_ENV = 'VAULT_IDENTITY_ID'
V2_MACHINE_ENV = 'VAULT_MACHINE_ID'
V2_PIN_ENV = 'VAULT_PIN'
RESOLVER_ENV = 'ACTUS_VAULT_RESOLVER'
LAZY_MIGRATE_ENV = 'ACTUS_VAULT_LAZY_MIGRATE'

_V2_SESSION_CACHE: Dict[str, Any] = {}        # auth 会话（写路径用）
_V2_ERROR_CACHE: Dict[str, Any] = {}          # auth 失败原因缓存
_V2_READONLY_CACHE: Dict[str, Any] = {}       # 只读会话（读路径用；不含登录副作用）
_V2_SESSION_TTL = 300.0
_V2_ERROR_TTL = 30.0


def _resolver_enabled() -> bool:
    """统一 resolver 总开关（默认开；`ACTUS_VAULT_RESOLVER=0` 可关闭回退读）。"""
    return (os.environ.get(RESOLVER_ENV) or '1').strip().lower() not in ('0', 'false', 'no', 'off')


def _lazy_migrate_enabled() -> bool:
    return (os.environ.get(LAZY_MIGRATE_ENV) or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _v2_credentials():
    return (os.environ.get(V2_IDENTITY_ENV), os.environ.get(V2_MACHINE_ENV),
            os.environ.get(V2_PIN_ENV))


def _v2_session(force: bool = False):
    """尝试建立 v2 会话。返回 (module, token, reason)；失败不抛。

    v2 不可用（未配置凭据 / 没有 keyring 或 passphrase / auth 失败）→
    (None, None, 可读原因)。调用方据此决定"回退 v1 读"或"拒绝写"。
    """
    creds = _v2_credentials()
    if not all(creds):
        return None, None, ('未配置 v2 凭据（%s / %s / %s），v2 读不可用'
                            % (V2_IDENTITY_ENV, V2_MACHINE_ENV, V2_PIN_ENV))
    now = time.time()
    cache = _V2_SESSION_CACHE
    if (not force and cache.get('creds') == creds and cache.get('token')
            and now - cache.get('ts', 0.0) < _V2_SESSION_TTL):
        return cache.get('module'), cache.get('token'), None
    err = _V2_ERROR_CACHE
    if (not force and err.get('creds') == creds and err.get('reason')
            and now - err.get('ts', 0.0) < _V2_ERROR_TTL):
        return None, None, err.get('reason')
    try:
        from . import vault2 as v2
        vault = v2._get_vault2()
        result = vault.auth(creds[0], creds[1], creds[2])
    except Exception as exc:  # noqa: BLE001 —— v2 不可用必须降级为可读原因
        reason = 'v2 不可用（%s: %s）' % (type(exc).__name__, exc)
        _V2_ERROR_CACHE.update({'creds': creds, 'ts': now, 'reason': reason})
        return None, None, reason
    if result.get('status') != 'ok':
        reason = 'v2 auth 失败：%s' % result.get('message')
        _V2_ERROR_CACHE.update({'creds': creds, 'ts': now, 'reason': reason})
        return None, None, reason
    token = result.get('session_token')
    cache.update({'creds': creds, 'token': token, 'module': v2, 'ts': now})
    _V2_ERROR_CACHE.update({'creds': None, 'ts': 0.0, 'reason': None})
    return v2, token, None


def _v2_read_secret(name: str):
    """读 v2 单个密钥。返回 (state, value, reason)。

    state ∈ {'found','absent','unavailable','error'}：
      * unavailable → 允许回退 v1 读（不是数据问题）；
      * error       → **不回退**（例如 v2 有该密钥但解密失败，隐藏它比报错更危险）。

    ⚠️ 第 12 轮残留修复：本函数是 `resolve_secret()`（CLI `vault get`、`vault list`
    逐 key 解析、executor `vault://` 批量解析）的**最热读路径**，之前用 `_v2_session()`
    （`vault2.auth()` 会 UPDATE `last_auth_at`/`failed_attempts`/`used_codes`），
    等于每次读密钥都在偷写 db。现在改走 `_v2_readonly_session()`：读不是登录，
    不做登录副作用（`used_codes` 防重放/失败计数），但 PIN/锁定/机器指纹检查照做
    —— 因此读到的值、source、warnings 与改前一致（见验收脚本对比）。
    """
    v2, token, reason = _v2_readonly_session()
    if reason:
        return 'unavailable', None, reason
    try:
        result = v2.get_secret(token, name, caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') == 'ok':
        return 'found', result.get('value'), None
    message = str(result.get('message') or '')
    if '凭证不存在' in message:
        return 'absent', None, None
    if '会话无效' in message:
        _V2_READONLY_CACHE.clear()          # 只清只读缓存，重建一次
        v2, token, reason = _v2_readonly_session()
        if reason:
            return 'unavailable', None, reason
        try:
            result = v2.get_secret(token, name, caller='vault.resolver')
        except Exception as exc:  # noqa: BLE001
            return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)
        if result.get('status') == 'ok':
            return 'found', result.get('value'), None
        message = str(result.get('message') or '')
        if '凭证不存在' in message:
            return 'absent', None, None
    return 'error', None, 'v2 读取失败：%s' % message


def _v1_read_secret(name: str, scope: str, meta_dir: Optional[str]):
    """读 v1 单个密钥。返回 (state, value, reason)；区分 absent / undecryptable。"""
    try:
        vault = Vault(meta_dir or default_meta_dir())
    except Exception as exc:  # noqa: BLE001
        return 'error', None, 'v1 打开失败（%s: %s）' % (type(exc).__name__, exc)
    status = vault.inspect(name, scope)
    if status == 'absent':
        return 'absent', None, None
    if status == 'undecryptable':
        return 'error', None, ('v1 中存在 %r 但当前 ACTUS_VAULT_KEY 解不开'
                               '（请配置正确主密钥，而不是把它当"不存在"）' % name)
    value = vault.get(name, scope, _allow_v2_fallback=False)
    if value is None:
        return 'absent', None, None
    return 'found', value, None


def _secret_fingerprint(value: str) -> str:
    """值的短指纹（冲突报错用；不打印明文，避免日志泄露密钥）。"""
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:12]


def resolve_secret(name: str, scope: str = 'global',
                   meta_dir: Optional[str] = None,
                   lazy_migrate: Optional[bool] = None) -> dict:
    """**统一 secret resolver**：读一个密钥（v2 优先，v1 兼容回退）。

    返回:
        {'status': 'ok'|'not_found'|'conflict'|'error',
         'name': ..., 'value': ..., 'source': 'v2'|'v1'|'v2+v1',
         'warnings': [...], 'migrated': bool, ...}

    规则（lead 裁决）：
      * v2 有 → 用它；v1 也有且相同 → source='v2+v1'；**不同 → conflict（不自动选）**；
      * v2 不可用/没有 → 回退 v1 读（数据在，读不能丢），并给 warning 说明；
      * 都没有 → not_found（附 v2 不可用原因，便于排查）；
      * v2 读出错（如密钥存在但解不开）→ error，**不回退**（避免把"坏了"伪装成"没有"）；
      * 懒迁移 opt-in：`lazy_migrate=True` 或 `ACTUS_VAULT_LAZY_MIGRATE=1` 时，
        读到 v1 的密钥会复制到 v2（失败只 warning，不影响本次读取）。
    """
    raw = '' if name is None else str(name).strip()
    if raw.startswith('vault://'):
        raw = raw[len('vault://'):]
    if not raw:
        return {'status': 'error', 'code': 'param_invalid',
                'message': '密钥名不能为空', 'name': raw}

    v2_state, v2_value, v2_reason = _v2_read_secret(raw)
    v1_state, v1_value, v1_reason = _v1_read_secret(raw, scope, meta_dir)
    warnings: list = []

    if v2_state == 'error':
        return {'status': 'error', 'code': 'v2_read_failed', 'name': raw,
                'source': 'v2', 'message': v2_reason}
    if v1_state == 'error':
        return {'status': 'error', 'code': 'v1_read_failed', 'name': raw,
                'source': 'v1', 'message': v1_reason}

    if v2_state == 'found' and v1_state == 'found':
        if str(v2_value) == str(v1_value):
            return {'status': 'ok', 'name': raw, 'value': v2_value,
                    'source': 'v2+v1', 'warnings': ['两个库值一致（以 v2 为准）'],
                    'migrated': False}
        return {
            'status': 'conflict', 'code': 'vault_secret_conflict', 'name': raw,
            'source': 'v1+v2',
            'message': ('v1 与 v2 都存在密钥 %r 但**值不同**（v1 指纹 %s…，v2 指纹 %s…）；'
                        'resolver 不自动选择，请人工确认保留哪个（删除其中一个或人工改齐）'
                        % (raw, _secret_fingerprint(v1_value), _secret_fingerprint(v2_value))),
            'conflicts': [{'name': raw, 'v1_fingerprint': _secret_fingerprint(v1_value),
                           'v2_fingerprint': _secret_fingerprint(v2_value)}],
        }

    if v2_state == 'found':
        return {'status': 'ok', 'name': raw, 'value': v2_value, 'source': 'v2',
                'warnings': warnings, 'migrated': False}

    if v1_state == 'found':
        if v2_state == 'unavailable':
            warnings.append('v2 不可用，本次回退读取旧库 v1：%s' % v2_reason)
        else:
            warnings.append('该密钥只在旧库 v1 中（v2 没有），已兼容读取；'
                            '建议迁移（见 docs/vault-v1-v2-merge.md）')
        migrated = False
        do_migrate = _lazy_migrate_enabled() if lazy_migrate is None else bool(lazy_migrate)
        if do_migrate and v2_state != 'unavailable':
            migrated, migrate_reason = _migrate_to_v2(raw, v1_value)
            if migrated:
                warnings.append('已懒迁移到 v2（%r）' % raw)
            elif migrate_reason:
                warnings.append('懒迁移失败（本次仍返回 v1 值）：%s' % migrate_reason)
        return {'status': 'ok', 'name': raw, 'value': v1_value, 'source': 'v1',
                'warnings': warnings, 'migrated': migrated}

    message = '密钥不存在: %r（v1 与 v2 都没有）' % raw
    if v2_state == 'unavailable':
        message += '；v2 不可用：%s' % v2_reason
    return {'status': 'not_found', 'code': 'secret_not_found', 'name': raw,
            'message': message, 'warnings': warnings}


def _migrate_to_v2(name: str, value: str):
    """把 v1 里的密钥复制到 v2（懒迁移）。返回 (ok, reason)。"""
    v2, token, reason = _v2_session()
    if reason:
        return False, reason
    try:
        result = v2.set_secret(token, name, str(value), caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return False, 'v2 写入异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') != 'ok':
        return False, 'v2 写入失败：%s' % result.get('message')
    return True, None


def write_secret(name: str, value: str, scope: str = 'global',
                 meta_dir: Optional[str] = None,
                 allow_v1_write: bool = False) -> dict:
    """**统一 secret resolver**：写一个密钥（默认写 v2）。

    失败模式（lead 硬要求：写不能落到将来读不到的地方）：
      * v2 可用 → 写 v2；若 v1 已有同名且**值不同** → 返回 conflict（避免制造分歧），
        若相同 → 覆盖 v2 并提示；
      * v2 **不可用** → 默认**拒绝**（code='vault2_unavailable'）。只有调用方显式
        `allow_v1_write=True` 时才写 v1（并在返回值里 warning 说明"眼下只能写 v1"）。
    """
    raw = '' if name is None else str(name).strip()
    if raw.startswith('vault://'):
        raw = raw[len('vault://'):]
    if not raw:
        return {'status': 'error', 'code': 'param_invalid', 'message': '密钥名不能为空'}
    if value is None:
        return {'status': 'error', 'code': 'param_invalid', 'message': '密钥值不能为空'}

    v1_state, v1_value, _v1_reason = _v1_read_secret(raw, scope, meta_dir)
    v2_state, _v2_value, v2_reason = _v2_read_secret(raw)

    if v2_state == 'error':
        return {'status': 'error', 'code': 'v2_read_failed', 'message': _v2_value or '',
                'source': 'v2'}

    if v2_state == 'found':
        if v1_state == 'found' and str(v1_value) != str(value):
            return {'status': 'conflict', 'code': 'vault_secret_conflict', 'name': raw,
                    'message': ('v1 中已有 %r 且与本次要写的值不同（v1 指纹 %s…）；'
                                '直接写 v2 会制造双库分歧，请先人工确认'
                                % (raw, _secret_fingerprint(v1_value)))}
        v2, token, reason = _v2_session()
        if reason:
            return {'status': 'refused', 'code': 'vault2_unavailable', 'name': raw,
                    'message': 'v2 不可用，拒绝写入：%s' % reason}
        try:
            result = v2.set_secret(token, raw, str(value), caller='vault.resolver')
        except Exception as exc:  # noqa: BLE001
            return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                    'message': 'v2 写入异常（%s: %s）' % (type(exc).__name__, exc)}
        if result.get('status') != 'ok':
            return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                    'message': 'v2 写入失败：%s' % result.get('message')}
        warnings = []
        if v1_state == 'found':
            warnings.append('v1 中已有同名密钥且值相同；已更新 v2（v1 未改动）')
        return {'status': 'ok', 'name': raw, 'source': 'v2', 'warnings': warnings}

    # v2 不可用或没有该密钥：v2 不可用时默认拒绝
    if v2_state == 'unavailable':
        if not allow_v1_write:
            return {'status': 'refused', 'code': 'vault2_unavailable', 'name': raw,
                    'message': ('v2 不可用（%s），拒绝写入 —— 避免写进一个 resolver '
                                '将来读不到的地方；如确需只写 v1，请显式 allow_v1_write=True'
                                % v2_reason)}
        vault = Vault(meta_dir or default_meta_dir())
        result = vault.set(raw, str(value), scope)
        if result.get('status') != 'ok':
            result.setdefault('warnings', []).append('v2 不可用，本次写入的是 v1')
            return result
        return {'status': 'ok', 'name': raw, 'source': 'v1',
                'warnings': ['v2 不可用（%s）：本次按显式 allow_v1_write 写入了 v1'
                             % v2_reason]}

    # v2 可用但当前没有该密钥：写 v2
    v2, token, reason = _v2_session()
    if reason:
        return {'status': 'refused', 'code': 'vault2_unavailable', 'name': raw,
                'message': 'v2 不可用，拒绝写入：%s' % reason}
    try:
        result = v2.set_secret(token, raw, str(value), caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                'message': 'v2 写入异常（%s: %s）' % (type(exc).__name__, exc)}
    if result.get('status') != 'ok':
        return {'status': 'error', 'code': 'v2_write_failed', 'name': raw,
                'message': 'v2 写入失败：%s' % result.get('message')}
    return {'status': 'ok', 'name': raw, 'source': 'v2', 'warnings': []}


def resolve_vault_refs(secrets_config: List[dict], meta_dir: str = '') -> dict:
    """批量解析动作的 `vault://` 引用（executor 注入 secrets 用）。

    Returns:
        {'status': 'ok'|'conflict'|'error', 'resolved': {env: value},
         'missing': [...], 'conflicts': [...], 'warnings': [...]}

    冲突/错误**不吞**：status 由调用方决定怎么处理（executor 会显式拒绝执行），
    绝不静默挑一个值。
    """
    resolved: Dict[str, str] = {}
    missing: List[str] = []
    conflicts: List[dict] = []
    errors: List[dict] = []
    warnings: List[str] = []
    for item in secrets_config or []:
        if not isinstance(item, dict):
            continue
        env_name = item.get('env')
        key_ref = str(item.get('key') or '')
        default = item.get('default')
        if not key_ref.startswith('vault://'):
            if env_name and default is not None:
                resolved[env_name] = default
            continue
        result = resolve_secret(key_ref, meta_dir=meta_dir or None)
        state = result.get('status')
        if state == 'ok':
            if env_name and result.get('value'):
                resolved[env_name] = result.get('value')
            warnings.extend(result.get('warnings') or [])
        elif state == 'conflict':
            conflicts.append(result)
        elif state == 'error':
            errors.append(result)
        elif default is not None:
            if env_name:
                resolved[env_name] = default
        else:
            missing.append(key_ref)
    if conflicts:
        return {'status': 'conflict', 'code': 'vault_secret_conflict',
                'resolved': resolved, 'missing': missing,
                'conflicts': conflicts, 'warnings': warnings,
                'message': '有 %d 个密钥在 v1/v2 中值不同，拒绝自动选择' % len(conflicts)}
    if errors:
        return {'status': 'error', 'code': 'vault_read_failed',
                'resolved': resolved, 'missing': missing, 'errors': errors,
                'warnings': warnings,
                'message': '有 %d 个密钥读取失败' % len(errors)}
    return {'status': 'ok', 'resolved': resolved, 'missing': missing,
            'warnings': warnings}


def resolver_status() -> dict:
    """resolver 自检：v2 是否可用、v1 路径、懒迁移开关（诊断用）。

    第 12 轮残留修复：诊断不该有写副作用 —— 切到 `_v2_readonly_session()`
    （此前走 `_v2_session()` 的 `vault2.auth()`，每次诊断都 UPDATE db）。
    """
    v2, token, reason = _v2_readonly_session()
    return {
        'enabled': _resolver_enabled(),
        'v2_available': v2 is not None,
        'v2_reason': reason,
        'v1_path': os.path.join(default_meta_dir(), 'vault'),
        'lazy_migrate': _lazy_migrate_enabled(),
    }


# ── 合并清单 / 删除（公开 API；CLI/MCP 不再借私有 `_v2_session`）──────────
#
# 背景（第 12 轮收尾）：CLI/MCP 为了"v1+v2 合并清单"直接 import 了 resolver 的
# 私有 `_v2_session` 并调 v2 私有实例方法 —— 一旦 resolver 内部重构就断。这里
# 把两件事提升为公开 API，行为与调用方现有实现逐字段对齐（见验收脚本对比）。
#
# 只读保证：`list_secret_names` 走**只读 v2 会话**（不调用 v2.auth：auth 会写
# last_auth_at / used_codes / 审计；这里只 SELECT，PIN/锁定/机器指纹检查全部在
# 内存里做）——因此 keys.json 与 vault2.db 逐字节不变（审计日志仍会追加"读了什么"，
# 那是审计语义，不是数据变更；要在 vault2 里加真正的 read-only session API 属后续项）。

def _v2_readonly_session():
    """建立**只读** v2 会话（不写 DB）。返回 (vault, token, reason)。

    与 `vault2.auth()` 的检查项对齐（存在性 / 锁定 / PIN / 机器指纹 / seed 解码 /
    master_key 派生），但：
      * 不执行 `failed_attempts/locked_until/last_auth_at` 的 UPDATE（只读）；
      * 不写 used_codes（动态码防重放是"登录"语义，只读会话不做）；
      * 失败原因以可读字符串返回，由 `list_secret_names` 填进 `v2_reason`。

    会话按 (identity, machine, pin, ACTUS_VAULT2_DIR) 缓存：`resolve_secret` 是
    最热读路径（每个 `vault://` 引用都会调），每次重建要跑 100k 次 pbkdf2；
    缓存后 TTL 内复用同一只读 token（token 仍受 vault2 的 SESSION_TTL 约束）。
    """
    identity_id = os.environ.get(V2_IDENTITY_ENV)
    machine_id = os.environ.get(V2_MACHINE_ENV)
    pin = os.environ.get(V2_PIN_ENV)
    if not (identity_id and machine_id and pin):
        return None, None, ('未配置 v2 凭据（%s / %s / %s），v2 读不可用'
                            % (V2_IDENTITY_ENV, V2_MACHINE_ENV, V2_PIN_ENV))
    cache_key = (identity_id, machine_id, pin,
                 (os.environ.get('ACTUS_VAULT2_DIR') or '').strip())
    cached = _V2_READONLY_CACHE
    if cached.get('key') == cache_key:
        token_cached = cached.get('token')
        session_cached = (getattr(cached.get('vault'), '_sessions', None) or {}).get(
            token_cached) if token_cached else None
        if session_cached and session_cached.get('expires_at', 0) > int(time.time()):
            return cached.get('vault'), token_cached, None
    try:
        from . import vault2 as v2
        vault = v2._get_vault2()
    except Exception as exc:  # noqa: BLE001
        return None, None, 'v2 不可用（%s: %s）' % (type(exc).__name__, exc)
    try:
        with vault._db() as conn:
            row = conn.execute(
                "SELECT pin_hash, salt, seed_key, security_level, failed_attempts, "
                "locked_until, key_salt, key_protection, key_meta "
                "FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            if not row:
                return None, None, 'v2 身份不存在: %s' % identity_id
            (pin_hash_hex, salt_hex, seed_key_stored, level, _failed, locked,
             key_salt_hex, seed_protection, seed_meta) = row
            if locked and int(time.time()) < locked:
                return None, None, ('v2 账户已锁定，请 %d 秒后重试'
                                    % (locked - int(time.time())))
            expected_hash = hashlib.pbkdf2_hmac(
                'sha256', pin.encode('utf-8'), bytes.fromhex(salt_hex), 100000)
            if not hmac.compare_digest(expected_hash.hex(), pin_hash_hex):
                return None, None, 'PIN 错误'
            machine = conn.execute(
                "SELECT fingerprint FROM machines WHERE id=? AND identity_id=?",
                (machine_id, identity_id)).fetchone()
            if not machine:
                return None, None, 'v2 机器未注册: %s' % machine_id
            if machine[0] != vault._machine_fingerprint():
                return None, None, 'v2 机器指纹不匹配'
        seed_key_hex = vault._decode_seed_hex(
            identity_id, seed_key_stored, seed_protection, seed_meta)
        dynamic_code = ''
        if level != 'L1':
            dynamic_code = v2.generate_dynamic_code(
                bytes.fromhex(seed_key_hex), v2.DEFAULT_TIME_STEP)
        if key_salt_hex:
            master_key = v2.derive_master_key(seed_key_hex, dynamic_code,
                                              bytes.fromhex(key_salt_hex))
        else:                                  # 旧身份（无 key_salt）：与 auth 同口径
            master_key = v2.derive_master_key(pin, dynamic_code,
                                              bytes.fromhex(salt_hex))
    except Exception as exc:  # noqa: BLE001
        return None, None, 'v2 只读会话建立失败（%s: %s）' % (type(exc).__name__, exc)
    token = 'readonly-' + secrets.token_hex(8)
    ttl = v2.SESSION_TTL.get(level, 600)
    vault._sessions[token] = {
        'identity_id': identity_id,
        'machine_id': machine_id,
        'security_level': level,
        'expires_at': int(time.time()) + ttl,
        'master_key': master_key,
    }
    old = _V2_READONLY_CACHE.get('token')
    if old and old != token:
        # 换新 token 时清掉旧的只读会话，避免 vault._sessions 里累积已过期的只读 token
        (getattr(vault, '_sessions', None) or {}).pop(old, None)
    _V2_READONLY_CACHE.update({'key': cache_key, 'vault': vault,
                               'token': token, 'ts': time.time()})
    return vault, token, None


def _v2_readonly_names():
    """只读列出 v2 密钥名。返回 (names, available, reason)。"""
    vault, token, reason = _v2_readonly_session()
    if reason:
        return [], False, reason
    try:
        result = vault.list_secrets(token)
    except Exception as exc:  # noqa: BLE001
        return [], False, 'v2 列举异常（%s: %s）' % (type(exc).__name__, exc)
    if result.get('status') != 'ok':
        return [], False, str(result.get('message') or 'v2 列举失败')
    return [item.get('name') for item in (result.get('secrets') or [])], True, None


def _v2_readonly_value(name: str):
    """只读取 v2 密钥值；失败返回 (state, value, reason)。

    与 `_v2_read_secret` 是同一实现（避免两份逻辑漂移：本轮把 `_v2_read_secret`
    也切到只读会话后，二者语义完全一致）。
    """
    return _v2_read_secret(name)


def list_secret_names(scope: str = 'global', meta_dir: Optional[str] = None) -> dict:
    """**合并清单（v1 + v2）**，只读、不写任何数据文件。

    每条：
        {'key', 'scope', 'source': 'v1'|'v2'|'v2+v1'|'v1+v2',
         'conflict': bool, 'in_v1': bool, 'in_v2': bool}

    顶层诊断：`v2_available` / `v2_reason` / `v1_error`（与 CLI 现有
    `_list_secrets_merged` 的返回体逐字段一致，便于无行为差异切换）。

    `source` 口径与 `resolve_secret` 一致：两边都有且值相同 → `v2+v1`；
    值不同 → `v1+v2` + `conflict=True`（**不静默挑一个**）。
    值比对用明文（只是不落盘）；v2 不可用不抛错，返回 v1 部分 + `v2_available=False`。
    """
    scope = scope or 'global'
    v1_names: list = []
    v1_error = None
    v1_vault = None
    try:
        v1_vault = Vault(meta_dir or default_meta_dir())
        v1_names = [row.get('key') for row in v1_vault.list(scope)]
    except Exception as exc:  # noqa: BLE001
        v1_error = 'v1 列举异常（%s: %s）' % (type(exc).__name__, exc)
    v2_names, v2_available, v2_reason = _v2_readonly_names()
    names = sorted(set(n for n in v1_names if n) | set(n for n in v2_names if n))
    rows = []
    for name in names:
        in_v1 = name in v1_names
        in_v2 = name in v2_names
        conflict = False
        if in_v1 and in_v2:
            v1_value = v1_vault.get(name, scope, _allow_v2_fallback=False) if v1_vault else None
            state, v2_value, _reason = _v2_readonly_value(name)
            if state == 'found' and v1_value is not None:
                conflict = str(v1_value) != str(v2_value)
        if in_v1 and in_v2:
            source = 'v1+v2' if conflict else 'v2+v1'
        else:
            source = 'v1' if in_v1 else 'v2'
        rows.append({'key': name, 'scope': scope, 'source': source,
                     'conflict': conflict, 'in_v1': in_v1, 'in_v2': in_v2})
    return {'status': 'ok', 'keys': rows, 'count': len(rows),
            'v2_available': v2_available, 'v2_reason': v2_reason,
            'v1_error': v1_error}


def delete_secret(name: str, scope: str = 'global', meta_dir: Optional[str] = None,
                  include_v1: bool = False, caller: str = None) -> dict:
    """**删除密钥**：默认只删 v2（resolver 的权威写入口与优先读源）。

    - `include_v1=True` 才会删旧库 v1 副本（**破坏性，必须显式**）；
    - v2 不可用 → `status='failed'` + `errors=[原因]` + `hint`（**不是静默 not_found**）；
    - 返回体同时给出 `deleted_v2` / `deleted_v1` / `not_found`（"删了几个/原本在不在"）。

    行为与 CLI 现有 `_delete_secret_merged` 对齐（字段为超集：多 `deleted_v2` /
    `not_found`；`hint` 用中性文案，调用方可按自己的 CLI 旗标覆写）。
    """
    raw = '' if name is None else str(name).strip()
    if raw.startswith('vault://'):
        raw = raw[len('vault://'):]
    scope = scope or 'global'
    removed: list = []
    errors: list = []
    v2, token, reason = _v2_session()
    if reason:
        errors.append('v2 不可用：%s' % reason)
    else:
        try:
            result = v2.delete_secret(token, raw, caller=caller or 'vault.resolver')
            if result.get('status') == 'ok':
                removed.append('v2')
            elif '凭证不存在' in str(result.get('message') or ''):
                pass                       # v2 里没有，不算错
            else:
                errors.append('v2 删除失败：%s' % result.get('message'))
        except Exception as exc:  # noqa: BLE001
            errors.append('v2 删除异常（%s: %s）' % (type(exc).__name__, exc))
    if include_v1:
        try:
            v1_vault = Vault(meta_dir or default_meta_dir())
            if v1_vault.delete(raw, scope):
                removed.append('v1')
            elif getattr(v1_vault, 'last_refusal', None):
                # v1 的写保护（临时主密钥等）必须显式上报，不能静默当"没这个密钥"
                refusal = v1_vault.last_refusal
                errors.append('v1 删除被拒绝：%s'
                              % (refusal.get('message') or refusal.get('code')))
        except Exception as exc:  # noqa: BLE001
            errors.append('v1 删除异常（%s: %s）' % (type(exc).__name__, exc))
    status = 'ok' if removed else ('failed' if errors else 'not_found')
    payload = {'status': status, 'key': raw, 'scope': scope,
               'deleted': removed,
               'deleted_v2': 'v2' in removed,
               'deleted_v1': 'v1' in removed,
               'not_found': status == 'not_found',
               'errors': errors}
    if not include_v1:
        payload['hint'] = ('默认只删 v2（权威来源）；旧库 v1 若也有副本，'
                           '请显式 include_v1=True（破坏性）')
    return payload
