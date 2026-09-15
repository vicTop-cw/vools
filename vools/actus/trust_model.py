"""trust_model.py —— 信任模型（docs/20 §M3）。

签名生成/验证、Scope 权限检查、三级信任审批流程。
"""

import hashlib
import json
import os
import time
import base64
from typing import Dict, List, Optional, Tuple

from .constants import SCOPE_LEVELS, SCOPE_PERMISSIONS, PERMISSIONS


class KeyManager:
    """签名密钥管理。

    生成、加载、保存 Ed25519 签名密钥对。
    """

    def __init__(self, keys_dir: str = None):
        """
        参数:
            keys_dir: 密钥存储目录（默认 ~/.actus/keys）。
        """
        if keys_dir is None:
            keys_dir = os.path.join(os.path.expanduser("~"), ".actus", "keys")
        self._keys_dir = keys_dir
        os.makedirs(keys_dir, exist_ok=True)

    @property
    def keys_dir(self) -> str:
        return self._keys_dir

    def generate_keypair(self, name: str = "default") -> Tuple[str, str]:
        """生成 Ed25519 密钥对。

        参数:
            name: 密钥名称。

        返回:
            (私钥路径, 公钥路径)
        """
        priv_path = os.path.join(self._keys_dir, f"{name}.key")
        pub_path = os.path.join(self._keys_dir, f"{name}.pub")

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey
            )
            from cryptography.hazmat.primitives import serialization

            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key()

            # 保存私钥
            priv_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            with open(priv_path, "wb") as f:
                f.write(priv_pem)
            os.chmod(priv_path, 0o600)

            # 保存公钥
            pub_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            with open(pub_path, "wb") as f:
                f.write(pub_pem)

        except ImportError:
            # 退化方案：使用简单随机字节
            priv_bytes = os.urandom(32)
            pub_bytes = os.urandom(32)

            with open(priv_path, "wb") as f:
                f.write(base64.b64encode(priv_bytes))
            os.chmod(priv_path, 0o600)

            with open(pub_path, "wb") as f:
                f.write(base64.b64encode(pub_bytes))

        return priv_path, pub_path

    def load_private_key(self, name: str = "default"):
        """加载私钥。"""
        priv_path = os.path.join(self._keys_dir, f"{name}.key")
        if not os.path.isfile(priv_path):
            return None

        with open(priv_path, "rb") as f:
            data = f.read()

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey
            )
            from cryptography.hazmat.primitives import serialization

            # 尝试 PEM 格式
            try:
                return serialization.load_pem_private_key(data, password=None)
            except Exception:
                pass

            # 尝试裸 32 字节
            decoded = base64.b64decode(data)
            if len(decoded) == 32:
                # 退化：返回裸字节
                return decoded

        except ImportError:
            return base64.b64decode(data)

        return None

    def load_public_key(self, name: str = "default") -> Optional[bytes]:
        """加载公钥。"""
        pub_path = os.path.join(self._keys_dir, f"{name}.pub")
        if not os.path.isfile(pub_path):
            return None

        with open(pub_path, "rb") as f:
            data = f.read()

        # 检查是否是 PEM 格式
        if data.startswith(b"-----BEGIN"):
            return data

        # 裸格式
        try:
            return base64.b64decode(data)
        except Exception:
            return data

    def list_keys(self) -> List[str]:
        """列出所有密钥名称。"""
        keys = []
        for fname in os.listdir(self._keys_dir):
            if fname.endswith(".key"):
                keys.append(fname[:-4])
        return keys


class SignatureVerifier:
    """签名生成与验证。"""

    def __init__(self, key_manager: KeyManager = None):
        self._key_manager = key_manager or KeyManager()

    def sign_file(self, fpath: str, key_name: str = "default",
                  output: str = None) -> dict:
        """对文件进行签名。

        参数:
            fpath: 要签名的文件路径。
            key_name: 使用的密钥名称。
            output: 签名输出路径（默认 .sig 后缀）。

        返回:
            签名数据字典。
        """
        if not os.path.isfile(fpath):
            return {"status": "error", "message": f"File not found: {fpath}"}

        # 计算文件哈希
        file_hash = self._compute_hash(fpath)
        message = f"actus-sig:{file_hash}:{time.time()}".encode("utf-8")

        # 加载私钥
        private_key = self._key_manager.load_private_key(key_name)
        if private_key is None:
            return {"status": "error", "message": f"Private key not found: {key_name}"}

        # 生成签名
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey
            )

            if isinstance(private_key, Ed25519PrivateKey):
                sig_bytes = private_key.sign(message)
            else:
                # 退化：HMAC-SHA256
                import hmac
                sig_bytes = hmac.new(private_key, message, hashlib.sha256).digest()

        except ImportError:
            import hmac
            if isinstance(private_key, bytes):
                sig_bytes = hmac.new(private_key, message, hashlib.sha256).digest()
            else:
                sig_bytes = hashlib.sha256(message + private_key).digest()

        sig_data = {
            "version": "1.0",
            "algorithm": "ed25519",
            "message": message.decode("utf-8"),
            "signature": base64.b64encode(sig_bytes).decode("utf-8"),
            "file": os.path.basename(fpath),
            "timestamp": time.time(),
            "signer": key_name
        }

        # 保存签名
        if output is None:
            output = fpath + ".sig"
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            json.dump(sig_data, f, indent=2)

        return {"status": "ok", "output": output, "signature": sig_data["signature"][:16] + "..."}

    def verify_file(self, fpath: str, sig_path: str = None,
                    public_key: bytes = None, key_name: str = "default") -> dict:
        """验证文件签名。

        参数:
            fpath: 原始文件路径。
            sig_path: 签名文件路径。
            public_key: 公钥内容（优先使用）。
            key_name: 公钥名称（从 KeyManager 加载）。

        返回:
            验证结果。
        """
        if not os.path.isfile(fpath):
            return {"status": "error", "message": "File not found"}

        if sig_path is None:
            sig_path = fpath + ".sig"

        if not os.path.isfile(sig_path):
            return {"status": "error", "message": "Signature file not found"}

        # 加载签名数据
        with open(sig_path, "r", encoding="utf-8") as f:
            sig_data = json.load(f)

        # 检查文件是否匹配
        if sig_data.get("file") and sig_data["file"] != os.path.basename(fpath):
            return {"status": "error", "message": "Signature file mismatch"}

        # 重新计算哈希验证内容完整性
        file_hash = self._compute_hash(fpath)
        message = sig_data.get("message", "").encode("utf-8")

        # 快速检查：消息中的哈希是否匹配
        if file_hash.encode() not in message:
            return {"status": "error", "message": "File content mismatch (tampered)"}

        # 加载公钥
        if public_key is None:
            public_key = self._key_manager.load_public_key(key_name)

        if public_key is None:
            return {"status": "error", "message": "Public key not found"}

        # 验证签名
        sig_bytes = base64.b64decode(sig_data["signature"])

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey
            )
            from cryptography.hazmat.primitives import serialization

            # 加载公钥
            if isinstance(public_key, bytes):
                if public_key.startswith(b"-----BEGIN"):
                    pub = serialization.load_pem_public_key(public_key)
                elif len(public_key) == 32:
                    pub = Ed25519PublicKey.from_public_bytes(public_key)
                else:
                    return {"status": "error", "message": "Invalid public key format"}
            else:
                pub = public_key

            # 验证
            try:
                pub.verify(sig_bytes, message)
                return {"status": "ok", "signer": sig_data.get("signer"), "algorithm": "ed25519"}
            except Exception:
                return {"status": "error", "message": "Signature verification failed"}

        except ImportError:
            # 退化：HMAC 验证（需要公钥 = 私钥）
            import hmac
            if isinstance(public_key, bytes):
                expected = hmac.new(public_key, message, hashlib.sha256).digest()
                if hmac.compare_digest(sig_bytes, expected):
                    return {"status": "ok", "signer": sig_data.get("signer"), "algorithm": "hmac-sha256"}
            return {"status": "error", "message": "Signature verification failed (fallback)"}

    @staticmethod
    def _compute_hash(fpath: str) -> str:
        """计算文件 SHA256 哈希。"""
        h = hashlib.sha256()
        with open(fpath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


class ScopeEnforcer:
    """Scope 权限执行。

    根据安装的 scope 配置，限制动作的权限。
    """

    def __init__(self, scope: str = "community"):
        """
        参数:
            scope: 权限范围（trusted/community/unverified/sandbox）。
        """
        self._scope = scope if scope in SCOPE_LEVELS else "community"
        self._allowed = set(SCOPE_PERMISSIONS.get(self._scope, []))

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def allowed_permissions(self) -> List[str]:
        return list(self._allowed)

    def check_permission(self, permission: str) -> bool:
        """检查是否拥有指定权限。"""
        return permission in self._allowed

    def check_permissions(self, permissions: List[str]) -> Tuple[bool, List[str]]:
        """检查权限列表。

        返回:
            (是否全部通过, 缺失的权限列表)
        """
        missing = [p for p in permissions if p not in self._allowed]
        return len(missing) == 0, missing

    def enforce(self, permissions: List[str]) -> Optional[str]:
        """执行权限检查，返回错误信息（如果有）。"""
        ok, missing = self.check_permissions(permissions)
        if ok:
            return None
        return f"Scope '{self._scope}' lacks permissions: {', '.join(missing)}"

    def is_readonly(self) -> bool:
        """是否为只读 scope。"""
        return self._scope in ("unverified", "sandbox")

    def requires_confirmation(self) -> bool:
        """是否需要执行前确认。"""
        return self._scope in ("unverified", "sandbox", "community")


class ApprovalManager:
    """审批流程管理。

    管理社区级别动作的审批记录，支持私有动作自动审批和团队动作审批。
    """

    def __init__(self, approvals_dir: str = None):
        if approvals_dir is None:
            approvals_dir = os.path.join(os.path.expanduser("~"), ".actus", "approvals")
        self._approvals_dir = approvals_dir
        os.makedirs(approvals_dir, exist_ok=True)

    def request_approval(self, action_id: str, source_url: str,
                         permissions: List[str], checksum: str,
                         visibility: str = "public",
                         author: str = "",
                         team: str = "") -> dict:
        """请求审批。

        参数:
            action_id: 动作 id。
            source_url: 来源 URL。
            permissions: 请求的权限列表。
            checksum: 动作文件校验和。
            visibility: 可见性级别 (public/unlisted/private/team)。
            author: 动作作者（私有动作需要）。
            team: 团队名称（团队动作需要）。

        返回:
            审批记录。
        """
        record = {
            "action_id": action_id,
            "source_url": source_url,
            "permissions": permissions,
            "checksum": checksum,
            "visibility": visibility,
            "author": author,
            "team": team,
            "requested_at": time.time(),
            "status": "pending"
        }

        # 私有动作：作者自动获得批准
        if visibility == "private" and author:
            record["status"] = "auto_approved"
            record["auto_approved_at"] = time.time()
            record["auto_approve_reason"] = "private_action_author"

        self._save(record)
        return record

    def approve(self, action_id: str) -> Optional[dict]:
        """批准动作。"""
        record = self._load(action_id)
        if record:
            record["status"] = "approved"
            record["approved_at"] = time.time()
            self._save(record)
        return record

    def reject(self, action_id: str, reason: str = "") -> Optional[dict]:
        """拒绝动作。"""
        record = self._load(action_id)
        if record:
            record["status"] = "rejected"
            record["rejected_at"] = time.time()
            record["reason"] = reason
            self._save(record)
        return record

    def is_approved(self, action_id: str) -> bool:
        """检查动作是否已批准。"""
        record = self._load(action_id)
        return record is not None and record.get("status") == "approved"

    def is_rejected(self, action_id: str) -> bool:
        """检查动作是否已拒绝。"""
        record = self._load(action_id)
        return record is not None and record.get("status") == "rejected"

    def list_pending(self) -> List[dict]:
        """列出待审批的动作。"""
        records = []
        for fname in os.listdir(self._approvals_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self._approvals_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                record = json.load(f)
            if record.get("status") == "pending":
                records.append(record)
        return records

    def _save(self, record: dict):
        """保存审批记录。"""
        action_id = record["action_id"]
        fpath = os.path.join(self._approvals_dir, f"{action_id}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)

    def _load(self, action_id: str) -> Optional[dict]:
        """加载审批记录。"""
        fpath = os.path.join(self._approvals_dir, f"{action_id}.json")
        if not os.path.isfile(fpath):
            return None
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)


class TrustEvaluator:
    """信任评估器。

    综合评估动作的信任级别，决定执行策略。
    """

    def __init__(self, install_dir: str = None):
        from .installer import ActionInstaller
        self._installer = ActionInstaller(install_dir=install_dir)
        self._approval = ApprovalManager()

    def evaluate(self, action_id: str, action_permissions: List[str] = None) -> dict:
        """评估动作的执行策略。

        返回:
            {
                "trust_level": "trusted|community|unverified|sandbox",
                "can_execute": bool,
                "requires_confirmation": bool,
                "scope_permissions": [...],
                "error": "..."
            }
        """
        result = {
            "trust_level": "unverified",
            "can_execute": False,
            "requires_confirmation": True,
            "scope_permissions": [],
            "error": None
        }

        # 查找安装来源
        manifest = self._find_manifest(action_id)
        if not manifest:
            result["error"] = f"Action not installed: {action_id}"
            return result

        # 获取 scope
        local_path = manifest.get("local_path", "")
        scope = self._get_scope(local_path)

        # 检查审批状态
        if self._approval.is_rejected(action_id):
            result["error"] = "Action has been rejected by user"
            return result

        requires_approval = scope in ("community", "unverified")
        if requires_approval and not self._approval.is_approved(action_id):
            # 需要但未批准
            result["trust_level"] = scope
            result["can_execute"] = False
            result["requires_confirmation"] = True
            result["error"] = f"Action requires approval (scope: {scope}). Run: actus approve {action_id}"
            return result

        # 检查权限
        enforcer = ScopeEnforcer(scope)
        if action_permissions:
            error = enforcer.enforce(action_permissions)
            if error:
                result["error"] = error
                return result

        result["trust_level"] = scope
        result["can_execute"] = True
        result["requires_confirmation"] = enforcer.requires_confirmation()
        result["scope_permissions"] = enforcer.allowed_permissions
        return result

    def _find_manifest(self, action_id: str) -> Optional[dict]:
        """查找动作的安装清单。"""
        manifests = self._installer.list_installed()
        for m in manifests:
            for a in m.get("actions", []):
                if a.get("id") == action_id:
                    return m
        return None

    def _get_scope(self, local_path: str) -> str:
        """获取安装路径的 scope 配置。"""
        scope_path = os.path.join(local_path, ".actus.scope")
        if os.path.isfile(scope_path):
            with open(scope_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "community"  # 默认


# ── 便捷函数 ──

def generate_keys(name: str = "default", keys_dir: str = None) -> Tuple[str, str]:
    """便捷函数：生成密钥对。"""
    km = KeyManager(keys_dir=keys_dir)
    return km.generate_keypair(name)


def sign_action(fpath: str, key_name: str = "default") -> dict:
    """便捷函数：签名动作文件。"""
    verifier = SignatureVerifier()
    return verifier.sign_file(fpath, key_name=key_name)


def verify_action(fpath: str, key_name: str = "default") -> dict:
    """便捷函数：验证动作文件签名。"""
    verifier = SignatureVerifier()
    return verifier.verify_file(fpath, key_name=key_name)


def check_scope_permission(scope: str, permission: str) -> bool:
    """便捷函数：检查 scope 是否拥有权限。"""
    enforcer = ScopeEnforcer(scope)
    return enforcer.check_permission(permission)


def evaluate_trust(action_id: str, permissions: List[str] = None) -> dict:
    """便捷函数：评估动作信任级别。"""
    evaluator = TrustEvaluator()
    return evaluate(action_id, action_permissions=permissions)


__all__ = [
    'ApprovalManager',
    'KeyManager',
    'ScopeEnforcer',
    'SignatureVerifier',
    'TrustEvaluator',
    'check_scope_permission',
    'evaluate_trust',
    'generate_keys',
    'sign_action',
    'verify_action'
]
