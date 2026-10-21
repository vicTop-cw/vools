"""vools.rhop.task.secrets - 配置敏感信息：明文 / 密文双支持 + 明文告警

配置里的敏感字段（密码 / token / 密钥）允许两种写法，**优先级统一**：

A) 兄弟键（推荐，最通用）::

       "sftp_password_plain":  "my-password",        # 明文区（一旦非空即被采用）
       "sftp_password_cipher": "RHOP-ENC:...",       # 密文区（明文为空时才用）

   → 解析出 ``sftp_password``

B) 秘密节点（既有 key 写法延伸）::

       "key": {"plain": "", "cipher": "RHOP-ENC:...", "path": "C:/secrets/rhop.key", "env": "RHOP_KEY"}

   → 解析出该节点的标量值

取值优先级：**非空明文 > 密文（解密） > path（读文件） > env（读环境变量） > 空串**。

只要用了明文就告警，并把「生成密文的确切命令」和「回填密文 / 清空明文」的操作写清楚::

    [rhop] ⚠ 配置字段 'sftp.password' 使用了明文。
          生成密文：python -m vools.rhop.secret enc "<你的明文>"
          然后把输出填到该字段的密文区（*_cipher / cipher），并清空明文区（*_plain / plain）。

``strict=True``（CLI ``--strict-secrets``）时明文直接报错，便于 CI / 生产卡口。
"""

from __future__ import absolute_import

import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..crypto import RhopCrypto, is_secret
from .errors import PlaintextSecretError, SecretError

#: 兄弟键后缀
PLAIN_SUFFIX = "_plain"
CIPHER_SUFFIX = "_cipher"

#: 秘密节点里承载明/密文的键名
SECRET_NODE_KEYS = ("plain", "cipher")

#: 敏感叶名（大小写不敏感，匹配「以这些词结尾」的叶键）
SENSITIVE_LEAF_RE = re.compile(
    r"(^|_)(password|passwd|pwd|token|secret|apikey|accesskey|privatekey|key)$",
    re.IGNORECASE,
)

#: 生成密文的命令（告警文案里引用同一处，改一处即全局生效）
SECRET_ENC_COMMAND = 'python -m vools.rhop.secret enc "<你的明文>"'

#: 根密钥字段默认不参与"自动解密"（它是解其他密文的那把钥匙）
DEFAULT_SKIP_PATHS = ("key",)


def mask_value(value: Any, keep: int = 2) -> str:
    """把敏感值打码（保留首尾少量字符），用于日志 / --print / HTML 回显。"""
    if value is None or value == "":
        return ""
    text = str(value)
    if is_secret(text):
        return "***CIPHER***" if len(text) <= keep * 2 else (
            text[: keep + len("RHOP-ENC:")] + "***" + text[-keep:])
    if len(text) <= keep * 2:
        return "***"
    return text[:keep] + "***" + text[-keep:]


def is_sensitive_leaf(key: str) -> bool:
    """叶键名是否属于敏感字段（password / token / key ... 结尾）。"""
    return bool(SENSITIVE_LEAF_RE.search(str(key or "")))


def command_hint(path: str, plain_key: Optional[str] = None,
                 cipher_key: Optional[str] = None) -> str:
    """拼出「生成密文 + 回填」的操作指引（告警与文档共用）。"""
    if plain_key or cipher_key:
        target = cipher_key or (str(plain_key)[: -len(PLAIN_SUFFIX)] + CIPHER_SUFFIX
                                if str(plain_key).endswith(PLAIN_SUFFIX) else "cipher")
        clear = plain_key or "plain"
    else:
        target = path + CIPHER_SUFFIX
        clear = path + PLAIN_SUFFIX
    return (
        "生成密文：%s\n"
        "      然后把输出填到 '%s'（密文区），并清空 '%s'（明文区）。" % (
            SECRET_ENC_COMMAND, target, clear)
    )


def _default_warner(message: str) -> None:
    """默认告警通道：stderr（CLI 可见）+ logging（可被捕获/过滤）。"""
    sys.stderr.write("[rhop] %s\n" % message)
    sys.stderr.flush()


def _plaintext_message(path: str, plain_key: Optional[str],
                       cipher_key: Optional[str]) -> str:
    """明文告警文案。"""
    return (
        "⚠ 配置字段 '%s' 使用了明文。\n"
        "      %s" % (path, command_hint(path, plain_key, cipher_key))
    )


class SecretResolver(object):
    """配置敏感信息解析器（明文优先 + 告警 + 密文解密）。"""

    def __init__(self, crypto: Optional[RhopCrypto] = None, strict: bool = False,
                 warner: Optional[Callable[[str], None]] = None,
                 warn_plaintext: bool = True,
                 skip_paths: Tuple[str, ...] = DEFAULT_SKIP_PATHS):
        self.crypto = crypto
        self.strict = strict
        self.warner = warner or _default_warner
        self.warn_plaintext = warn_plaintext
        self.skip_paths = tuple(skip_paths or ())
        #: 解析发现 [{path, action, message}]
        self.findings = []  # type: List[Dict[str, str]]

    # ---- 对外 ----

    def resolve(self, cfg: dict) -> dict:
        """解析整棵配置树，返回新 dict（不改原对象）。"""
        if not isinstance(cfg, dict):
            raise SecretError("配置必须是 dict/JSON 对象")
        return self._walk(cfg, "")

    # ---- 内部 ----

    def _record(self, path: str, action: str, message: str) -> None:
        self.findings.append({"path": path, "action": action, "message": message})

    def flag_plaintext(self, path: str, message: str) -> None:
        """登记「用了明文」：记录 finding → 告警 → 严格模式直接抛错。"""
        self._record(path, "plaintext", message)
        if self.warn_plaintext:
            self.warner(message)
        if self.strict:
            raise PlaintextSecretError(message)

    def _decrypt(self, cipher: Any, path: str) -> str:
        if self.crypto is None:
            raise SecretError(
                "配置字段 '%s' 是密文，但当前没有解密密钥："
                "请设置环境变量 RHOP_KEY，或配置 key.path / --key-file。" % path)
        try:
            return self.crypto.decrypt_secret(str(cipher))
        except ValueError as exc:
            raise SecretError("配置字段 '%s' 解密失败：%s" % (path, exc))

    def _read_file(self, file_path: str, path: str) -> str:
        try:
            with open(os.path.expanduser(str(file_path)), "r", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError as exc:
            raise SecretError("配置字段 '%s' 读取密钥文件失败: %s" % (path, exc))

    def _resolve_layers(self, plain: Any, cipher: Any, file_path: Any, env_name: Any,
                        path: str, plain_key: Optional[str] = None,
                        cipher_key: Optional[str] = None) -> str:
        """按 明文 > 密文 > path > env 取值。"""
        if plain is not None and str(plain) != "":
            self.flag_plaintext(path, _plaintext_message(path, plain_key, cipher_key))
            return str(plain)
        if cipher is not None and str(cipher) != "":
            value = self._decrypt(cipher, path)
            self._record(path, "cipher", "")
            return value
        if file_path is not None and str(file_path) != "":
            value = self._read_file(str(file_path), path)
            self._record(path, "path", "")
            return value
        if env_name is not None and str(env_name) != "":
            value = os.environ.get(str(env_name), "")
            if value == "":
                raise SecretError(
                    "配置字段 '%s' 指定了环境变量 %s，但该变量为空/未设置。" % (path, env_name))
            self._record(path, "env", "")
            return value
        return ""

    def _is_secret_node(self, node: dict) -> bool:
        """是否是一个"秘密节点"。

        判定规则（刻意收紧，避免误伤普通配置节点）：节点里必须显式出现
        ``plain`` 或 ``cipher`` 键（值可以为空串）。这样：
        - ``{"plain": "", "cipher": "RHOP-ENC:..", "env": "RHOP_KEY"}`` → 秘密节点；
        - ``{"env": {...}}``（如 exec.env 这种真·配置）→ 普通节点，不会被当成秘密；
        - ``{"env": "RHOP_KEY"}`` 单靠 env 的写法由 ``_key_from_cfg`` /
          ``TaskConfig._resolve_master_key`` 负责，不走通用解析器。
        """
        return any(k in node for k in SECRET_NODE_KEYS)

    def _is_skipped(self, rel_path: str) -> bool:
        """该相对路径是否属于「不参与自动解密/自动告警」的路径（如根密钥 key）。

        ``key`` 是解其它密文的那把钥匙：它由 ``_key_from_cfg`` /
        ``TaskConfig._resolve_master_key`` 专门处理（含自己的明文告警），
        这里必须整棵跳过，否则会出现重复告警与"自己解自己"的循环。
        """
        rel = str(rel_path or "").lstrip(".")
        for pattern in self.skip_paths:
            if rel == pattern or rel.startswith(pattern + "."):
                return True
        return False

    def _walk(self, node: Any, path: str) -> Any:
        if isinstance(node, list):
            return [self._walk(item, "%s[%d]" % (path, i)) for i, item in enumerate(node)]
        if not isinstance(node, dict):
            return node

        rel = path.lstrip(".")
        if self._is_skipped(rel):
            return node  # 交给上层专门处理（主密钥来源），此处不改写、不告警

        # 秘密节点：{"plain":.., "cipher":.., "path":.., "env":..} → 标量
        if self._is_secret_node(node):
            resolved = self._resolve_layers(
                node.get("plain"), node.get("cipher"), node.get("path"), node.get("env"),
                rel or "(root)", plain_key=None, cipher_key=None)
            rest = {k: v for k, v in node.items()
                    if k not in SECRET_NODE_KEYS and k not in ("path", "env")}
            if rest:
                # 其余键保留（如自定义说明字段），但主值以解析出的标量为准
                for key, value in rest.items():
                    self._record("%s.%s" % (rel, key), "kept", "")
            return resolved

        # 兄弟键 *_plain / *_cipher
        bases = {}  # type: Dict[str, Dict[str, str]]
        for key in node.keys():
            if key.endswith(PLAIN_SUFFIX):
                bases.setdefault(key[: -len(PLAIN_SUFFIX)], {})["plain"] = key
            elif key.endswith(CIPHER_SUFFIX):
                bases.setdefault(key[: -len(CIPHER_SUFFIX)], {})["cipher"] = key

        out = {}
        node_resolved = set()
        for key, value in node.items():
            if key.endswith(PLAIN_SUFFIX) or key.endswith(CIPHER_SUFFIX):
                continue  # 由 bases 统一收敛
            child_path = ("%s.%s" % (path, key)) if path else key
            if isinstance(value, dict) and not self._is_skipped(child_path) \
                    and self._is_secret_node(value):
                # 秘密节点：递归进去把它收敛成标量，并记下来避免下面又被当敏感叶告警一次
                out[key] = self._walk(value, child_path)
                node_resolved.add(key)
                continue
            out[key] = self._walk(value, child_path)

        from_pairs = set()
        for base, pair in bases.items():
            plain_key = pair.get("plain")
            cipher_key = pair.get("cipher")
            plain = node.get(plain_key) if plain_key else None
            cipher = node.get(cipher_key) if cipher_key else None
            # 告警/诊断一律用「基础字段路径」，回填提示用完整 *_plain / *_cipher 路径
            base_path = ("%s.%s" % (path, base)) if path else base
            plain_full = ("%s.%s" % (path, plain_key)) if (path and plain_key) else plain_key
            cipher_full = ("%s.%s" % (path, cipher_key)) if (path and cipher_key) else cipher_key
            out[base] = self._resolve_layers(plain, cipher, None, None, base_path,
                                             plain_key=plain_full, cipher_key=cipher_full)
            from_pairs.add(base)

        # 单值敏感叶：明文告警 / 密文自动解密（pair / 秘密节点已收敛的键、以及 skip 路径跳过）
        for key, value in list(out.items()):
            if key in from_pairs or key in node_resolved \
                    or isinstance(value, (dict, list)) or not is_sensitive_leaf(key):
                continue
            field_path = ("%s.%s" % (path, key)) if path else key
            if self._is_skipped(field_path):
                continue
            if value is None or value == "":
                continue
            if is_secret(value):
                out[key] = self._decrypt(value, field_path)
                self._record(field_path, "cipher", "")
            else:
                self.flag_plaintext(field_path,
                                    _plaintext_message(field_path, None, None))
        return out


def resolve_config_secrets(cfg: dict, crypto: Optional[RhopCrypto] = None,
                           strict: bool = False,
                           warner: Optional[Callable[[str], None]] = None,
                           warn_plaintext: bool = True,
                           skip_paths: Tuple[str, ...] = DEFAULT_SKIP_PATHS
                           ) -> Tuple[dict, List[Dict[str, str]]]:
    """解析配置里的明文/密文，返回 ``(resolved_cfg, findings)``。

    Args:
        cfg:            原始配置 dict（不会被修改）
        crypto:         RhopCrypto（解密密文用）；只含明文时可给 None
        strict:         True 时遇到明文敏感字段直接抛 PlaintextSecretError
        warner:         告警通道（缺省 stderr）；测试可注入列表收集
        warn_plaintext: 是否输出明文告警（RhopConfig 兼容路径可关掉）
        skip_paths:     不参与"自动解密/自动告警"的路径（默认根密钥 key）

    Returns:
        (resolved_cfg, findings)：findings 为 [{path, action, message}]，action ∈
        plaintext / cipher / path / env / kept。
    """
    resolver = SecretResolver(crypto=crypto, strict=strict, warner=warner,
                              warn_plaintext=warn_plaintext, skip_paths=skip_paths)
    resolved = resolver.resolve(cfg)
    return resolved, resolver.findings


def find_secret_fields(cfg: Any, prefix: str = "") -> List[Dict[str, str]]:
    """列出配置里所有敏感字段（供 HTML 生成器 / CLI 提示使用）。

    Returns:
        [{"path": "sftp.password", "kind": "leaf"|"pair"|"node", "plain_key":..., "cipher_key":...}]
    """
    out = []  # type: List[Dict[str, str]]
    if isinstance(cfg, list):
        for idx, item in enumerate(cfg):
            out.extend(find_secret_fields(item, "%s[%d]" % (prefix, idx)))
        return out
    if not isinstance(cfg, dict):
        return out
    bases = {k[: -len(PLAIN_SUFFIX)] for k in cfg if k.endswith(PLAIN_SUFFIX)}
    bases |= {k[: -len(CIPHER_SUFFIX)] for k in cfg if k.endswith(CIPHER_SUFFIX)}
    for key, value in cfg.items():
        path = ("%s.%s" % (prefix, key)) if prefix else key
        if key in bases or key.endswith(PLAIN_SUFFIX) or key.endswith(CIPHER_SUFFIX):
            continue
        if isinstance(value, dict) and any(k in value for k in SECRET_NODE_KEYS):
            out.append({"path": path, "kind": "node", "plain_key": "plain", "cipher_key": "cipher"})
        elif isinstance(value, (dict, list)):
            out.extend(find_secret_fields(value, path))
        elif is_sensitive_leaf(key):
            out.append({"path": path, "kind": "leaf",
                        "plain_key": path + PLAIN_SUFFIX,
                        "cipher_key": path + CIPHER_SUFFIX})
    for base in sorted(bases):
        path = ("%s.%s" % (prefix, base)) if prefix else base
        out.append({"path": path, "kind": "pair",
                    "plain_key": path + PLAIN_SUFFIX, "cipher_key": path + CIPHER_SUFFIX})
    return out


__all__ = [
    "PLAIN_SUFFIX",
    "CIPHER_SUFFIX",
    "SECRET_NODE_KEYS",
    "SECRET_ENC_COMMAND",
    "SENSITIVE_LEAF_RE",
    "DEFAULT_SKIP_PATHS",
    "SecretResolver",
    "resolve_config_secrets",
    "find_secret_fields",
    "is_sensitive_leaf",
    "mask_value",
    "command_hint",
]