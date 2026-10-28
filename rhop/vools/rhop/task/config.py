"""vools.rhop.task.config - 任务队列配置（方向驱动 + 数据库抽象 + 明文/密文）

配置形态（JSON/dict，只有「方向 + 相关配置」，**没有 P0..P3**）::

    {
      "name": "rhop-link",
      "role": "A",                         // A=提交方 | B=执行方 | C=中转
      "key":  {"plain": "", "cipher": "RHOP-ENC:...", "path": "", "env": "RHOP_KEY"},
      "shared": {"write": "E:\\\\share\\\\rhop", "read": "\\\\\\\\nas\\\\share\\\\rhop"},
      "online": [{"kind": "sftp", "host": "...", "user": "...", "password_cipher": "..."}],
      "relay":  {"host": "127.0.0.1", "port": 0, "token_cipher": ""},
      "queue": {
        "store": {"kind": "sqlite-shared"},        // sqlite-shared(默认) | sqlite-local
        "heartbeat": {"file": "rhop-link.heartbeat", "interval_sec": 5, "stale_after_sec": 15},
        "poll_interval_sec": 2,
        "max_retries": 3, "retry_delay_min": 5, "timeout_min": 60,
        "encrypt_result": true, "result_max_bytes": 65536
      },
      "exec": {"allow": ["action:*"], "allow_any": false, "timeout_sec": 3600}
    }

本模块职责：
1. 方向归一（A/B/C ↔ SEND/RECV/RELAY，兼容 requester/executor 写法）；
2. 敏感信息解析（明文优先 + 告警，密文自动解密，见 ``secrets.py``）；
3. 组装共享介质 / 存储后端 / 心跳 / 执行策略所需的构件与上下文。

不直接实例化存储与心跳（那是 ``build_store`` / ``build_heartbeat`` 的事，
保持"读配置"与"开资源"分离，方便 ``config --print`` 无副作用）。
"""

from __future__ import absolute_import

import json
import os
from typing import Any, Dict, List, Optional

from ..config import RhopConfig, _key_from_cfg
from ..crypto import ENV_RHOP_KEY, RhopCrypto, load_key
from ..session import Role
from .errors import SecretError
from .secrets import (
    DEFAULT_SKIP_PATHS,
    SecretResolver,
    mask_value,
    resolve_config_secrets,
)

#: 方向别名 → 长角色（与 session.Role 对齐）
ROLE_ALIASES = {
    "A": Role.SEND, "SEND": Role.SEND, "REQUESTER": Role.SEND, "SUBMIT": Role.SEND,
    "B": Role.RECV, "RECV": Role.RECV, "RECEIVE": Role.RECV, "EXECUTOR": Role.RECV,
    "SERVER": Role.RECV, "WORKER": Role.RECV,
    "C": Role.RELAY, "RELAY": Role.RELAY, "RELAY_SERVER": Role.RELAY,
}

#: 长角色 → 短方向（显示/日志用）
SHORT_ROLES = {Role.SEND: "A", Role.RECV: "B", Role.RELAY: "C"}

#: queue 段默认值
DEFAULT_QUEUE = {
    "store": {"kind": "sqlite-shared"},
    "heartbeat": {"file": "", "interval_sec": 5, "stale_after_sec": 15, "closed_token": "closed"},
    "poll_interval_sec": 2,
    "max_retries": 3,
    "retry_delay_min": 5,
    "timeout_min": 60,
    "encrypt_result": True,
    "result_max_bytes": 65536,
    "lock_ttl_sec": 900,
    # 租约续期（BUG-289 引入，BUG-367 收口为受管键）：默认关闭 ⇒ 零回归。
    # renew_interval_sec=0 表示自动（= lock_ttl_sec/2）；显式值必须 ≤ lock_ttl_sec/2，
    # 否则续期与租约同拍，边际上仍可能被 clean_stale_locks 抢先回收。
    "renew_lock": False,
    "renew_interval_sec": 0,
    # 大载荷文件通道（默认关闭 ⇒ 零回归）：开启后，结果超过 max_bytes 时把完整结果落文件，
    # 信封里只回 file_ref（路径 + sha256 + 字节数），B 端按引用读回。
    # dir 需双方共享（缺省 <base_dir>/rhop-files，且会校验落点必须落在 base_dir/shared 之内）；
    # keep_days 是 cleanup 的保留期；payload_max_bytes 是**载荷侧**落文件阈值（0=关闭）。
    "file_channel": {"enabled": False, "dir": "", "max_bytes": 1048576,
                     "keep_days": 7, "payload_max_bytes": 0},
}

#: exec 段默认值（默认白名单：只放行代码内注册的 rhop 动作与处理器，
#: 任意命令行 cli:* 需显式列出，或 allow_any 整体放开）
DEFAULT_EXEC = {
    "allow": ["action:*", "handler:*"],
    "allow_any": False,
    "workdir": "",
    "env": {},
    "timeout_sec": 3600,
    "shell": False,
}


def normalize_role(value: Any) -> str:
    """把任意方向写法归一为长角色（SEND/RECV/RELAY）。"""
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if not text:
        raise SecretError("配置缺少 role/direction（A=提交方 / B=执行方 / C=中转）")
    mapped = ROLE_ALIASES.get(text)
    if mapped is None:
        raise SecretError(
            "未知方向 role=%r（可用 A / B / C，也接受 SEND / RECV / RELAY）" % value)
    return mapped


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """dict 深合并（override 优先；list/标量直接覆盖）。"""
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _as_dict(value: Any, key_name: str) -> Dict[str, Any]:
    """把「字符串简写」或 dict 统一成 dict。"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        return {key_name: value}
    raise SecretError("配置 %s 必须是 dict 或字符串简写，收到 %s" % (key_name, type(value).__name__))


def _filesystem_root(view: Any) -> Optional[str]:
    """从端视图取「可承载数据库」的文件系统路径；URL 形态一律返回 None。

    只有本地目录 / UNC / 盘符 / file:// 解析出的路径能放 SQLite。
    http(s):// 或其它形态必须返回 None —— 否则会把 URL 当成相对路径 abspath 成一个
    奇怪的本地目录，静默在错误位置建库（这一点有真实踩坑记录，故显式挡住）。
    """
    if view is None:
        return None
    if getattr(view, "kind", "") not in ("local", "file-url"):
        return None
    path = getattr(view, "path", None)
    if not path or "://" in str(path):
        return None
    return str(path)


def _validate_shared_root(root: str, base_dir: str, label: str) -> str:
    """校验共享介质落点在 base_dir 的父目录之内（BUG-302 收口）。

    shared.write/shared.read 的路径只经过 _filesystem_root 的「视图解析」，
    没有像 file_channel.dir 那样的落点校验——写成 ``..`` 上跳会让共享库
    真实写到 base_dir 之外（BUG-295 只覆盖了文件通道，没覆盖共享介质）。

    校验规则：解析后的绝对路径必须在 base_dir 的父目录（或其更深层）之内。
    这允许 shared 指向 base_dir 的同级目录（如 ``<parent>/share`` 与
    ``<parent>/a`` 并存），同时拒绝逃逸到父目录之上的 ``../..`` 路径。

    Args:
        root: 共享介质路径（相对或绝对）
        base_dir: 基准目录
        label: 配置键名（用于错误提示）

    Returns:
        校验通过的绝对路径

    Raises:
        SecretError: 路径逃逸时
    """
    from .errors import SecretError
    abs_root = os.path.realpath(os.path.abspath(os.path.join(base_dir, root)))
    real_base = os.path.realpath(os.path.abspath(base_dir))
    # 允许的边界：base_dir 的父目录（含自身）
    allowed_root = os.path.dirname(real_base)
    if not (abs_root == allowed_root or abs_root.startswith(allowed_root + os.sep)):
        raise SecretError(
            "shared.%s=%r 解析为 %s，不在允许的共享根（%s）之内。"
            "为防止共享库写到约定范围之外，请把 shared.%s 设成 base_dir "
            "的父目录或其子目录下的路径。" % (label, root, abs_root, allowed_root, label))
    return abs_root


class TaskConfig(object):
    """任务队列配置对象（读配置 + 构件工厂）。"""

    def __init__(self, rhop: RhopConfig, raw: dict, resolved: dict,
                 findings: List[Dict[str, str]], base_dir: str, role: str):
        self.rhop = rhop
        self.raw = raw                      # 原始配置（含明文，勿落日志）
        self.resolved = resolved            # 敏感信息已解析（明文已告警 / 密文已解密）
        self.findings = findings            # [{path, action, message}]
        self.base_dir = base_dir
        self.role = role                    # SEND / RECV / RELAY
        self.name = str(resolved.get("name") or rhop.name or "rhop")

        queue_raw = resolved.get("queue") or {}
        if not isinstance(queue_raw, dict):
            raise SecretError("配置 queue 段必须是 dict")
        store_spec = _as_dict(queue_raw.get("store") or queue_raw.get("store_kind"), "kind")
        heartbeat_raw = queue_raw.get("heartbeat")
        if isinstance(heartbeat_raw, str):
            heartbeat_raw = {"file": heartbeat_raw}
        elif heartbeat_raw is None:
            heartbeat_raw = {}
        elif not isinstance(heartbeat_raw, dict):
            raise SecretError("配置 queue.heartbeat 必须是 dict 或文件名字符串")
        self.queue = _deep_merge(DEFAULT_QUEUE, queue_raw)
        self.queue["store"] = _deep_merge(DEFAULT_QUEUE["store"], store_spec)
        self.queue["heartbeat"] = _deep_merge(DEFAULT_QUEUE["heartbeat"], heartbeat_raw)
        if not self.queue["heartbeat"].get("file"):
            self.queue["heartbeat"]["file"] = "%s.heartbeat" % self.name
        # 判死阈值校验（BUG-282 收口）：心跳时间戳是微秒级，但读数的 age 仍依赖阈值合理性。
        # 阈值必须 ≥ 写间隔 + 1s，否则「刚写完就被判死」的窗口成立；同时阈值过小还会把 B 的
        # 一次写间隔抖动误判成挂了。
        heartbeat = self.queue["heartbeat"]
        interval = float(heartbeat.get("interval_sec") or 5.0)
        stale = float(heartbeat.get("stale_after_sec") or 15.0)
        if stale < interval + 1.0:
            raise SecretError(
                "心跳判死阈值过小：stale_after_sec=%s 必须 ≥ interval_sec=%s + 1s。"
                "心跳读数的 age 含最多约 1s 的截断误差（历史缺陷 BUG-282：秒精度时该误差会顶到 0.999s，"
                "阈值小于 1s 会把刚写完心跳的 B 判成 stale）。请把阈值调到 interval_sec + 1s 以上。"
                % (stale, interval))

        # 续期间隔校验（BUG-367 收口）：renew_interval_sec 曾是「不在 DEFAULT_QUEUE、不校验、
        # 实现层静默 min(interval, ttl)」的野键——请求 100000 会被悄悄压成 ttl，与判死阈值同拍，
        # 边际上仍可能被 clean_stale_locks 抢先回收。现在显式受管并拒绝越界值。
        lock_ttl = float(self.queue.get("lock_ttl_sec") or 900.0)
        renew_interval = float(self.queue.get("renew_interval_sec") or 0.0)
        if lock_ttl <= 0:
            raise SecretError("lock_ttl_sec 必须为正数，收到 %s" % lock_ttl)
        if renew_interval < 0:
            raise SecretError("renew_interval_sec 不能为负，收到 %s" % renew_interval)
        if self.queue.get("renew_lock") and renew_interval > lock_ttl / 2.0:
            raise SecretError(
                "续期间隔过大：renew_interval_sec=%s 必须 ≤ lock_ttl_sec/2=%s"
                "（缺陷 BUG-367：续期与租约同拍时，续期线程还没刷到，clean_stale_locks 就可能"
                "把仍活着执行的任务判死回收，导致重复执行）。0 表示自动取 lock_ttl_sec/2。"
                % (renew_interval, lock_ttl / 2.0))

        exec_raw = resolved.get("exec") or {}
        if not isinstance(exec_raw, dict):
            raise SecretError("配置 exec 段必须是 dict")
        self.exec = _deep_merge(DEFAULT_EXEC, exec_raw)

    # ------------------------------------------------------------------
    # 构造入口
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict, base_dir: Optional[str] = None,
                  strict_secrets: bool = False,
                  warner: Any = None, warn_plaintext: bool = True) -> "TaskConfig":
        """从 dict 构造（先解析敏感信息，再组装 RhopConfig）。"""
        if not isinstance(data, dict):
            raise SecretError("配置必须是 dict/JSON 对象")
        raw = json.loads(json.dumps(data, ensure_ascii=False))  # 深拷贝，避免改调用方对象
        base_dir = os.path.abspath(base_dir or raw.get("base_dir") or os.getcwd())

        role_value = raw.get("role", raw.get("direction", raw.get("rhop_role")))
        role = normalize_role(role_value)

        # 1) 先取主密钥（它是解其它密文的那把钥匙，必须最先确定）
        master_resolver = SecretResolver(strict=strict_secrets, warner=warner,
                                        warn_plaintext=warn_plaintext,
                                        skip_paths=DEFAULT_SKIP_PATHS)
        key_text = cls._resolve_master_key(raw.get("key"), master_resolver)
        crypto = RhopCrypto(key_text) if key_text else None

        # 2) 再解析整棵配置（用主密钥解各密文；key 本身跳过自动解密）
        resolved, findings = resolve_config_secrets(
            raw, crypto=crypto, strict=strict_secrets, warner=warner,
            warn_plaintext=warn_plaintext, skip_paths=DEFAULT_SKIP_PATHS)
        resolved["role"] = role
        # 主密钥：没有就置空串（是否必需由使用点判定——加密/解密/同步时才强制），
        # 使"只跑本地命令、不带任何密文"的配置也能加载。
        resolved["key"] = key_text or ""

        rhop = RhopConfig.from_dict(resolved)
        findings = list(master_resolver.findings) + list(findings)
        return cls(rhop, raw, resolved, findings, base_dir, role)

    @classmethod
    def from_file(cls, path: str, strict_secrets: bool = False,
                  warner: Any = None, warn_plaintext: bool = True) -> "TaskConfig":
        """从 JSON 文件构造（base_dir 缺省取配置文件所在目录）。"""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_dict(data, base_dir=os.path.dirname(os.path.abspath(path)),
                             strict_secrets=strict_secrets, warner=warner,
                             warn_plaintext=warn_plaintext)

    @staticmethod
    def _resolve_master_key(key_cfg: Any, resolver: SecretResolver) -> str:
        """解析主密钥（明文 / 密文 / path / env 四种来源，明文告警）。"""
        if key_cfg is None or key_cfg == "":
            env_key = os.environ.get(ENV_RHOP_KEY, "")
            if env_key:
                return env_key
            return ""
        if isinstance(key_cfg, dict):
            plain = key_cfg.get("plain")
            cipher = key_cfg.get("cipher")
            path = key_cfg.get("path")
            env_name = key_cfg.get("env") or ENV_RHOP_KEY
            if plain not in (None, ""):
                resolver.flag_plaintext("key.plain", (
                    "⚠ 配置字段 'key.plain' 使用了明文主密钥。\n"
                    "      生成密文：python -m vools.rhop.secret enc \"<你的密钥>\"\n"
                    "      然后把输出填到 'key.cipher'，并把 'key.plain' 置空"
                    "（解开它需要 'key.env' 或 'key.path' 提供外层密钥）。"
                ))
                return str(plain)
            if cipher not in (None, ""):
                try:
                    unlock = load_key(source=None, path=path, env_name=env_name)
                except ValueError as exc:
                    raise SecretError(
                        "配置 key.cipher 是密文，但缺少解开它的外层密钥："
                        "请设置 %s 环境变量或 key.path（%s）" % (env_name, exc))
                try:
                    return RhopCrypto(unlock).decrypt_secret(str(cipher))
                except ValueError as exc:
                    raise SecretError("配置 key.cipher 解密失败：%s" % exc)
            return _key_from_cfg(key_cfg)
        # 字符串写法：明文主密钥
        resolver.flag_plaintext("key", (
            "⚠ 配置字段 'key' 使用了明文主密钥。\n"
            "      生成密文：python -m vools.rhop.secret enc \"<你的密钥>\"\n"
            "      然后改写成 {\"cipher\": \"RHOP-ENC:...\", \"env\": \"RHOP_KEY\"}"
            "（env/path 提供解开它的外层密钥），并清空明文。"
        ))
        return str(key_cfg)

    # ------------------------------------------------------------------
    # 构件工厂
    # ------------------------------------------------------------------

    def build_crypto(self) -> Optional[RhopCrypto]:
        """构造加解密对象（主密钥为空时返回 None）。"""
        return self.rhop.build_crypto() if self.rhop.key else None

    def build_shared(self):
        """构造共享介质（write/read 多端视图）；未配置返回 None。"""
        return self.rhop.build_shared()

    def shared_read_root(self) -> Optional[str]:
        """共享介质读端视图的文件系统路径（http-url 形态返回 None）。"""
        shared = self.build_shared()
        if shared is None:
            return None
        root = _filesystem_root(getattr(shared, "read_view", None))
        if root is None:
            return None
        # BUG-302: 落点校验——必须落在 base_dir 内
        return _validate_shared_root(root, self.base_dir, 'read')

    def shared_write_root(self) -> Optional[str]:
        """共享介质写端视图的文件系统路径。"""
        shared = self.build_shared()
        if shared is None:
            return None
        root = _filesystem_root(getattr(shared, "write_view", None))
        if root is None:
            return None
        # BUG-302: 落点校验——必须落在 base_dir 内
        return _validate_shared_root(root, self.base_dir, 'write')

    def store_ctx(self) -> dict:
        """存储后端的解析上下文。"""
        return {
            "name": self.name,
            "role": SHORT_ROLES.get(self.role, "?"),
            "base_dir": self.base_dir,
            "shared_root": self.shared_read_root(),
            "shared": self.build_shared(),
            "config_dir": self.base_dir,
        }

    def build_store(self):
        """按 ``queue.store.kind`` 构造存储后端（打开数据库文件）。"""
        from .store import create_store
        return create_store(self.queue.get("store") or {}, self.store_ctx())

    def build_session(self, role: Optional[str] = None):
        """构造 rhop 会话（传输链：relay > online > shared）。"""
        return self.rhop.build_session(role=role)

    def build_heartbeat(self, worker_id: Optional[str] = None):
        """构造心跳对象（写端 B 用；A 侧也可构造来只读）。"""
        from .heartbeat import Heartbeat
        spec = dict(self.queue.get("heartbeat") or {})
        return Heartbeat(
            shared=self.build_shared(),
            filename=str(spec.get("file") or "%s.heartbeat" % self.name),
            interval_sec=float(spec.get("interval_sec") or 5),
            stale_after_sec=float(spec.get("stale_after_sec") or 15),
            closed_token=str(spec.get("closed_token") or "closed"),
            worker_id=worker_id or self.worker_id(),
        )

    def worker_id(self) -> str:
        """worker 标识（配置优先，缺省 <name>-<方向>）。"""
        explicit = str(self.queue.get("worker_id") or "").strip()
        if explicit:
            return explicit
        return "%s-%s" % (self.name, SHORT_ROLES.get(self.role, "?").lower())

    def poll_interval(self) -> float:
        """轮询间隔（秒）。"""
        return float(self.queue.get("poll_interval_sec") or 2)

    def exec_timeout(self) -> float:
        """单任务执行超时（秒）。"""
        return float(self.exec.get("timeout_sec") or 3600)

    # ---- 展示 ----

    def role_short(self) -> str:
        """短方向（A/B/C）。"""
        return SHORT_ROLES.get(self.role, "?")

    def plaintext_findings(self) -> List[Dict[str, str]]:
        """只挑出「用了明文」的发现（CLI 汇总/CI 卡口用）。"""
        return [f for f in self.findings if f.get("action") == "plaintext"]

    def to_dict(self, mask: bool = True) -> Dict[str, Any]:
        """导出配置（mask=True 时敏感值打码，绝不回显明文）。"""
        out = dict(self.resolved)
        out["role"] = self.role
        out["name"] = self.name
        out["base_dir"] = self.base_dir
        if mask:
            out["key"] = "***" if self.rhop.key else ""
            for section in ("sftp", "relay"):
                node = out.get(section)
                if isinstance(node, dict):
                    out[section] = {
                        k: (mask_value(v) if k in ("password", "token", "key_path") else v)
                        for k, v in node.items()}
            online = out.get("online")
            if isinstance(online, list):
                out["online"] = [
                    ({k: (mask_value(v) if k in ("password", "token") else v)
                      for k, v in item.items()} if isinstance(item, dict) else item)
                    for item in online]
            hb = (out.get("queue") or {}).get("heartbeat") if isinstance(out.get("queue"), dict) else None
            if isinstance(hb, dict) and hb.get("token"):
                hb["token"] = mask_value(hb["token"])
        return out

    def describe(self) -> Dict[str, Any]:
        """自描述（CLI config --print 的结构化输出）。"""
        return {
            "name": self.name,
            "role": self.role_short(),
            "role_long": self.role,
            "base_dir": self.base_dir,
            "has_key": bool(self.rhop.key),
            "shared": {
                "write": self.shared_write_root(),
                "read": self.shared_read_root(),
            },
            "store": dict(self.queue.get("store") or {}),
            "heartbeat": dict(self.queue.get("heartbeat") or {}),
            "worker_id": self.worker_id(),
            "poll_interval_sec": self.poll_interval(),
            "exec": {
                "allow": list(self.exec.get("allow") or []),
                "allow_any": bool(self.exec.get("allow_any")),
                "timeout_sec": self.exec_timeout(),
            },
            "plaintext_fields": [f.get("path") for f in self.plaintext_findings()],
        }


def load_task_config(path_or_dict, strict_secrets: bool = False,
                     warner: Any = None, warn_plaintext: bool = True) -> TaskConfig:
    """便捷入口：JSON 文件路径或 dict → TaskConfig。"""
    if isinstance(path_or_dict, dict):
        return TaskConfig.from_dict(path_or_dict, strict_secrets=strict_secrets,
                                    warner=warner, warn_plaintext=warn_plaintext)
    return TaskConfig.from_file(path_or_dict, strict_secrets=strict_secrets,
                                warner=warner, warn_plaintext=warn_plaintext)


__all__ = [
    "TaskConfig",
    "load_task_config",
    "normalize_role",
    "ROLE_ALIASES",
    "SHORT_ROLES",
    "DEFAULT_QUEUE",
    "DEFAULT_EXEC",
]