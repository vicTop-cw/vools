"""vault.py —— 密钥保险库（docs/10 §D）。

为动作提供加密的密钥/密码/API token 存储。
存储位置：_meta/vault/keys.json（加密后）+ _meta/vault/meta.json（明文元数据）

加密策略：
- 首选 Fernet（cryptography 库）
- 回退 XOR + HMAC-SHA256（无外部依赖）
- 主密钥从环境变量 ACTUS_VAULT_KEY 获取，缺省为随机生成（仅当前会话有效）

API：
- set(key, value, scope='global') → 加密存储
- get(key, scope='global') → 解密返回
- delete(key, scope='global') → 删除
- list(scope=None) → 列出密钥元数据
- resolve_secrets(action) → 解析动作的 secrets 字段并注入实际值
"""

__all__ = ['Vault', 'set_key', 'get_key', 'delete_key', 'list_keys', 'resolve_secrets']

import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from typing import Any, Dict, List, Optional


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

class Vault:
    """密钥保险库。

    存储结构：
    - _meta/vault/keys.json: {scope: {key: encrypted_value}}
    - _meta/vault/meta.json: {scope: {key: {created_at, updated_at, description}}}
    """

    def __init__(self, meta_dir: str, master_key: Optional[str] = None):
        """
        参数:
            meta_dir: 仓库 _meta 目录路径。
            master_key: 加密主密钥（缺省从 ACTUS_VAULT_KEY 环境变量获取）。
        """
        self._vault_dir = os.path.join(meta_dir, 'vault')
        os.makedirs(self._vault_dir, exist_ok=True)

        if master_key is None:
            master_key = os.environ.get('ACTUS_VAULT_KEY')
        if not master_key:
            # 生成临时密钥（仅当前会话有效）
            master_key = secrets.token_hex(32)
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

    def _save(self):
        with open(self._keys_path, 'w', encoding='utf-8') as f:
            json.dump(self._keys_data, f, ensure_ascii=False, indent=2)
        with open(self._meta_path, 'w', encoding='utf-8') as f:
            json.dump(self._meta_data, f, ensure_ascii=False, indent=2)

    def set(self, key: str, value: str, scope: str = 'global',
            description: str = '') -> dict:
        """加密存储密钥。

        返回:
            {'status': 'ok', 'key': ..., 'scope': ...}
        """
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

        self._save()
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

    def delete(self, key: str, scope: str = 'global') -> bool:
        """删除密钥。

        返回:
            是否成功删除。
        """
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


def _get_vault(meta_dir: str) -> Vault:
    global _vault_singleton
    if _vault_singleton is None:
        _vault_singleton = Vault(meta_dir)
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
