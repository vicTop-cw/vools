"""vools.rhop.crypto - MVP-1 抽象密钥函数

本地固定密钥（配置侧管理，信封不含密钥）对 JSON 文本加密 / 解密验证的一体抽象。

核心公共 API:
    load_key(source, env_name, path)  密钥加载（显式 source > 配置文件 path > 环境变量）
    RhopCrypto(key)                   密钥加密/解密验证一体对象
        encrypt_json(payload)         对 JSON（dict）加密，输出加密 JSON 文本（str）
        decrypt_verify(token)         用本地固定密钥解密后比对内容，明确区分通过/失败

输出格式（加密 JSON 文本）:
    {"v":1, "alg":"fernet", "ct": "<Fernet token base64>"}
    - v: 信封版本
    - alg: 算法标识（当前 fernet）
    - ct: 加密载荷（Fernet token，urlsafe base64 文本）

失败原因（VerifyResult.reason）明确区分:
    "OK"            解密成功且内容有效（json 可解析）
    "MALFORMED"     信封结构不合法（非 dict / 缺字段 / 类型错）
    "BAD_TOKEN"     Fernet token 无法解密（密钥错误或密文被篡改）
    "NOT_JSON"      解密成功但内容不是合法 JSON
"""

import base64
import hashlib
import json
import os
from typing import Any, Dict, NamedTuple, Optional, Tuple, Union

from cryptography.fernet import Fernet, InvalidToken

# 信封常量
_ENV_VERSION = 1
_ENV_ALG = "fernet"
_ENV_KEY_FIELD = "ct"

# 默认环境变量名
ENV_RHOP_KEY = "RHOP_KEY"

# 密钥派生参数（固定本地密钥 → Fernet key）
_DERIVE_ALG = "sha256"
_DERIVE_INFO = b"vools.rhop.mvp.crypto.v1"


class VerifyResult(NamedTuple):
    """解密验证结果。

    ok:     是否通过
    payload: 通过时为解密后的 dict；失败为 None
    reason:  明确区分结果原因（见模块 docstring）
    """

    ok: bool
    payload: Optional[Dict[str, Any]]
    reason: str


def _derive_fernet_key(key_material: Union[str, bytes]) -> bytes:
    """把任意长度的本地固定密钥派生为 Fernet 所需的 32 字节 urlsafe key。"""
    if isinstance(key_material, str):
        key_material = key_material.encode("utf-8")
    digest = hashlib.pbkdf2_hmac(
        _DERIVE_ALG,
        key_material,
        _DERIVE_INFO,
        100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(digest)


def load_key(
    source: Optional[Union[str, bytes]] = None,
    path: Optional[str] = None,
    env_name: str = ENV_RHOP_KEY,
) -> str:
    """加载本地固定密钥。

    加载优先级:
        1. source（调用方显式传入的密钥文本）
        2. path（配置文件路径，读其内容）
        3. env_name（环境变量）

    返回值: 密钥文本（str）。密钥以派生形式使用，本函数不做派生。
    """
    if source is not None:
        return source if isinstance(source, str) else source.decode("utf-8")
    if path is not None:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    env = os.environ.get(env_name, "")
    if env:
        return env
    raise ValueError(
        "rhop: 未找到本地固定密钥。请通过 source / path / 环境变量 {0} 提供。".format(env_name)
    )


class RhopCrypto(object):
    """本地固定密钥 + 加密/解密验证一体抽象。"""

    def __init__(self, key: Union[str, bytes]):
        self._key_material = key
        self._fernet = Fernet(_derive_fernet_key(key))

    # ------------------------------------------------------------------
    # 密钥加载辅助（类方法）
    # ------------------------------------------------------------------

    @classmethod
    def from_key(cls, key: Union[str, bytes]) -> "RhopCrypto":
        return cls(key)

    @classmethod
    def from_path(cls, path: str) -> "RhopCrypto":
        return cls(load_key(path=path))

    @classmethod
    def from_env(cls, env_name: str = ENV_RHOP_KEY) -> "RhopCrypto":
        return cls(load_key(env_name=env_name))

    # ------------------------------------------------------------------
    # 加密 / 解密验证
    # ------------------------------------------------------------------

    def encrypt_json(self, payload: Union[Dict[str, Any], str]) -> str:
        """对 JSON 文本（dict 或 str）加密，输出加密 JSON 文本。

        返回: str，形如 {"v":1,"alg":"fernet","ct":"<token>"}
        """
        if isinstance(payload, str):
            # 字符串按 JSON 文本处理：若已是合法 JSON 原样保留，否则当作普通字符串载荷
            try:
                json.loads(payload)
                body = payload
            except (ValueError, TypeError):
                body = json.dumps({"__text__": payload}, ensure_ascii=False)
        else:
            body = json.dumps(payload, ensure_ascii=False)
        token = self._fernet.encrypt(body.encode("utf-8")).decode("ascii")
        envelope = {
            "v": _ENV_VERSION,
            "alg": _ENV_ALG,
            _ENV_KEY_FIELD: token,
        }
        return json.dumps(envelope, ensure_ascii=False)

    def decrypt_verify(self, token_text: str) -> VerifyResult:
        """用本地固定密钥解密后比对内容，判断验证是否通过。

        返回 VerifyResult：
            ok=True,  payload=解密后的 dict,   reason="OK"
            ok=False, payload=None,            reason 区分失败原因
        """
        try:
            envelope = json.loads(token_text)
        except (ValueError, TypeError):
            return VerifyResult(False, None, "MALFORMED")

        if not isinstance(envelope, dict):
            return VerifyResult(False, None, "MALFORMED")
        if envelope.get("v") != _ENV_VERSION:
            return VerifyResult(False, None, "MALFORMED")
        if envelope.get("alg") != _ENV_ALG:
            return VerifyResult(False, None, "MALFORMED")
        ct = envelope.get(_ENV_KEY_FIELD)
        if not isinstance(ct, str) or not ct:
            return VerifyResult(False, None, "MALFORMED")

        try:
            plain = self._fernet.decrypt(ct.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return VerifyResult(False, None, "BAD_TOKEN")
        except Exception:
            return VerifyResult(False, None, "BAD_TOKEN")

        try:
            payload = json.loads(plain)
        except (ValueError, TypeError):
            return VerifyResult(False, None, "NOT_JSON")

        return VerifyResult(True, payload, "OK")
