"""
vools.rhop.crypto - rhop 加密抽象

复用 vools.data.vtext.VText 的 Fernet 加密/解密，保留 rhop 专属接口：

    RhopCrypto(key)               — 密钥加密/解密验证一体对象
        encrypt_json(payload)      — 对 JSON（dict）加密，输出加密 JSON 文本（str）
        decrypt_verify(token_text) — 用本地固定密钥解密后比对内容，明确区分通过/失败
        encrypt_secret(plaintext)  — 把配置敏感信息加密为 RHOP-ENC 密文
        decrypt_secret(cipher)     — 解密 RHOP-ENC 密文
    is_secret(value)              — 判断字符串是否是 RHOP-ENC 密文

底层加密委托给 VText.encrypt(way="fernet") / VText.decrypt()，
密钥派生参数（PBKDF2 salt/iterations）由 VText 统一管理。
"""

from __future__ import absolute_import

import base64
import hashlib
import json
import os
from typing import Any, Dict, NamedTuple, Optional, Union

from vools.data.vtext import VText

# 信封常量
_ENV_VERSION = 1
_ENV_ALG = "fernet"
_ENV_KEY_FIELD = "ct"

# 默认环境变量名
ENV_RHOP_KEY = "RHOP_KEY"

# 配置密文前缀（明文 ↔ 密文 双支持用；见 RhopCrypto.encrypt_secret / decrypt_secret）
SECRET_PREFIX = "RHOP-ENC:"


class VerifyResult(NamedTuple):
    """解密验证结果。

    ok:     是否通过
    payload: 通过时为解密后的 dict；失败为 None
    reason:  明确区分结果原因（见模块 docstring）
    """

    ok: bool
    payload: Optional[Dict[str, Any]]
    reason: str


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

    返回值: 密钥文本（str）。
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


def is_secret(value: Any) -> bool:
    """判断字符串是否是 rhop 密文（``RHOP-ENC:`` 前缀）。"""
    return isinstance(value, str) and value.startswith(SECRET_PREFIX)


class RhopCrypto(object):
    """本地固定密钥 + 加密/解密验证一体抽象。

    底层加密委托给 vools.data.vtext.VText，保留 rhop 专属接口与前缀格式。
    """

    def __init__(self, key: Union[str, bytes]):
        self._key_material = key
        self._key_str = key if isinstance(key, str) else key.decode("utf-8")

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

    def _vtext(self, text: str = "") -> VText:
        """构造一个 VText 用于加密/解密（key 传给 encrypt/decrypt 方法）。"""
        return VText(text)

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
        # 委托 VText Fernet 加密，取 "F:" 前缀后的 token
        enc = self._vtext(body).encrypt(way="fernet", key=self._key_material)
        token_text = str(enc)
        if token_text.startswith("F:"):
            token = token_text[2:]
        else:
            token = token_text
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

        # 委托 VText Fernet 解密
        try:
            token_text_full = "F:" + ct
            plain_vtext = self._vtext(token_text_full).decrypt(way="fernet", key=self._key_material)
            plain = str(plain_vtext)
        except Exception:
            return VerifyResult(False, None, "BAD_TOKEN")

        # VText.decrypt 失败时可能返回原文（非 JSON），区分 BAD_TOKEN vs NOT_JSON
        if not plain or plain == token_text_full or plain.startswith("F:") or plain.startswith("E:"):
            return VerifyResult(False, None, "BAD_TOKEN")

        try:
            payload = json.loads(plain)
        except (ValueError, TypeError):
            return VerifyResult(False, None, "NOT_JSON")

        return VerifyResult(True, payload, "OK")

    # ------------------------------------------------------------------
    # 配置密文（明文 / 密文 双支持：敏感字段用 RHOP-ENC: 前缀承载）
    # ------------------------------------------------------------------

    def encrypt_secret(self, plaintext: Union[str, bytes, None]) -> str:
        """把一段明文（密码 / token / 密钥）加密成 ``RHOP-ENC:<token>`` 密文。

        与 ``encrypt_json`` 共用同一把 Fernet 密钥，底层委托 VText。
        """
        if plaintext is None or plaintext == "":
            return ""
        if isinstance(plaintext, bytes):
            plaintext = plaintext.decode("utf-8")
        enc = self._vtext(str(plaintext)).encrypt(way="fernet", key=self._key_material)
        token_text = str(enc)
        if token_text.startswith("F:"):
            token = token_text[2:]
        else:
            token = token_text
        return SECRET_PREFIX + token

    def decrypt_secret(self, value: Union[str, None]) -> str:
        """解密 ``RHOP-ENC:`` 密文，返回明文。

        Raises:
            ValueError: 前缀不符（不是 rhop 密文）或解密失败（密钥不符/密文被篡改），
                        错误文本明确区分两种原因，便于配置诊断。
        """
        if value is None or value == "":
            return ""
        text = str(value).strip()
        if not text.startswith(SECRET_PREFIX):
            raise ValueError(
                "不是 rhop 密文（应以 %r 开头）；明文请直接填明文区，"
                "密文请用 python -m vools.rhop.secret enc \"<明文>\" 生成" % SECRET_PREFIX
            )
        token = text[len(SECRET_PREFIX):].strip()
        if not token:
            return ""
        try:
            token_text_full = "F:" + token
            plain_vtext = self._vtext(token_text_full).decrypt(way="fernet", key=self._key_material)
            plain = str(plain_vtext)
        except Exception as exc:
            raise ValueError("密文解密失败：密钥不符或密文被篡改"
                             "（请确认 RHOP_KEY / 密钥文件与生成密文时一致）: %s" % exc)
        # VText.decrypt 失败时静默回退原文（设计如此），这里显式检测恢复「错误密钥必须报错」语义
        if not plain or plain.startswith(("F:", "E:", "A:")) or plain == token_text_full:
            raise ValueError("密文解密失败：密钥不符或密文被篡改"
                             "（请确认 RHOP_KEY / 密钥文件与生成密文时一致）")
        return plain
