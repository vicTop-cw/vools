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
           'list_keys', 'resolve_secrets']

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

    def get(self, key: str, scope: str = 'global') -> Optional[str]:
        """解密获取密钥。

        返回:
            密钥值，或 None（不存在）。
        """
        encrypted = self._keys_data.get(scope, {}).get(key)
        if encrypted is None:
            return None
        try:
            return self._backend.decrypt(encrypted)
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


def reset_vault_singleton():
    """测试用：重置单例。"""
    global _vault_singleton
    _vault_singleton = None
