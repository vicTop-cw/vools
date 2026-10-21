"""vools.rhop.config - 一份配置描述密钥/角色/介质/动作集（配置驱动地基 Step 4）

RhopConfig 把 JSON/dict 配置归一为会话构件（密钥 + 在线通道 + shared path + 中转），
供 interact() 一键交互与动作执行使用。vq/sparksql-exe 只需提供配置 + 指定动作。

配置形态（JSON/dict）：
    {
      "name": "dev-A",                     # 可选：会话名
      "key": "plain-secret",               # 密钥：明文 / {"path": "...", "env": "RHOP_KEY"}
      "role": "SEND",                      # SEND | RECV | RELAY
      "sftp": {"host": "...", "user": "...", "password": "...", "dir": "/srv", "key_path": "..."},
                                           # 可选：jump 动作的目标跳板机（FTP_connect 形态）
      "online": [
          {"kind": "sftp", "host": "...", "user": "...", "dir": "/srv", "port": 22, "password": "..."},
          {"kind": "git", "remote_url": "...", "branch": "main"}
      ],                                   # 可选：在线通道列表（按优先级）
      "shared": {"write": "D:/share", "read": "D:/share"},
                                           # 可选：shared path（写/读视图，缺省读=写）
      "relay": {"host": "127.0.0.1", "port": 0, "token": "..."}
                                           # 可选：A->C->B 中转地址（本端投递视角）
    }
"""

import json
import os
from typing import Any, Dict, List, Optional, Union

from .crypto import RhopCrypto, load_key
from .session import Role, Session
from .transport import (
    GitChannel,
    LocalSharedPath,
    RelayChannel,
    SftpChannel,
    make_shared_path,
)


def _key_from_cfg(key_cfg):
    """从配置的 key 字段解析密钥文本（明文 / 密文 / path / env）。

    兼容写法：
    - 字符串：直接作为密钥文本（明文，调用方负责告警）；
    - 字典 ``{"path": ...}`` / ``{"env": ...}``：从文件或环境变量取密钥；
    - 字典 ``{"plain": "..."}``：明文字段（task 层会打明文告警）；
    - 字典 ``{"cipher": "RHOP-ENC:...", "env"|"path": ...}``：加密的主密钥，
      用 env/path 提供的外层密钥解开（避免"自己解自己"的循环）。
    """
    if key_cfg is None:
        raise ValueError("配置缺少 key（明文、key.cipher、key.path 或 key.env 三者其一）")
    if isinstance(key_cfg, dict):
        plain = key_cfg.get("plain")
        if plain not in (None, ""):
            return str(plain)
        cipher = key_cfg.get("cipher")
        if cipher not in (None, ""):
            from .crypto import RhopCrypto
            unlock = load_key(source=key_cfg.get("source"),
                              path=key_cfg.get("path"),
                              env_name=key_cfg.get("env") or "RHOP_KEY")
            return RhopCrypto(unlock).decrypt_secret(str(cipher))
        path = key_cfg.get("path")
        env = key_cfg.get("env")
        source = key_cfg.get("source")
        return load_key(source=source, path=path, env_name=env or "RHOP_KEY")
    return str(key_cfg)


def _channel_from_dict(spec: dict):
    """按 spec 构造在线通道（kind: sftp / git / relay）。"""
    kind = (spec.get("kind") or "sftp").lower()
    if kind == "sftp":
        return SftpChannel(
            spec.get("host") or "",
            spec.get("dir") or spec.get("remote_dir") or "",
            username=spec.get("user") or spec.get("username") or "",
            port=int(spec.get("port", 22) or 22),
            password=spec.get("password"),
            key_path=spec.get("key_path"),
            probe_mode=spec.get("probe_mode", "tcp"),
        )
    if kind == "git":
        return GitChannel(
            spec.get("remote_url") or "",
            local_workdir=spec.get("workdir"),
            branch=spec.get("branch", "main"),
        )
    if kind == "relay":
        return RelayChannel(
            spec.get("host") or "127.0.0.1",
            int(spec.get("port", 0) or 0),
            token=spec.get("token"),
            timeout=float(spec.get("timeout", 3.0) or 3.0),
        )
    raise ValueError("不支持的在线通道 kind: %s（可用 sftp/git/relay）" % kind)


class RhopConfig(object):
    """配置驱动会话的静态描述 + 构件工厂。"""

    def __init__(
        self,
        key: str,
        role: str = Role.SEND,
        sftp: Optional[dict] = None,
        online: Optional[List[dict]] = None,
        shared: Optional[dict] = None,
        relay: Optional[dict] = None,
        name: Optional[str] = None,
    ):
        self.key = key
        self.role = role
        self.sftp = sftp or {}
        self.online = online or []
        self.shared = shared
        self.relay = relay
        self.name = name or "rhop-config"

    # ---- 工厂 ----

    @classmethod
    def from_dict(cls, data: dict) -> "RhopConfig":
        """从 dict 构造并校验（缺关键字段抛 ValueError）。"""
        if not isinstance(data, dict):
            raise ValueError("配置必须是 dict/JSON 对象")
        key = _key_from_cfg(data.get("key"))
        role = str(data.get("role") or Role.SEND).upper()
        if role not in Role.ALL:
            raise ValueError("未知 role: %s（可用 %s）" % (role, Role.ALL))
        return cls(
            key=key,
            role=role,
            sftp=data.get("sftp"),
            online=data.get("online"),
            shared=data.get("shared"),
            relay=data.get("relay"),
            name=data.get("name"),
        )

    @classmethod
    def from_file(cls, path: str) -> "RhopConfig":
        """从 JSON 文件构造。"""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        """导出配置 dict（密钥不落盘，仅回填存在性标记）。"""
        out = {
            "name": self.name,
            "role": self.role,
            "has_key": bool(self.key),
            "sftp": {k: ("***" if k in ("password", "key_path") else v)
                     for k, v in self.sftp.items()},
            "online": self.online,
            "shared": self.shared,
            "relay": self.relay,
        }
        return out

    # ---- 构件工厂 ----

    def build_crypto(self) -> RhopCrypto:
        return RhopCrypto.from_key(self.key)

    def build_online(self) -> List:
        channels = []
        for spec in self.online:
            channels.append(_channel_from_dict(spec))
        return channels

    def build_shared(self):
        if not self.shared:
            return None
        write_spec = self.shared.get("write") or self.shared.get("spec")
        read_spec = self.shared.get("read")
        if not write_spec:
            raise ValueError("shared 配置缺少 write/spec 字段")
        # 统一走 make_shared_path：单 spec 时读端=写端，语义与旧 LocalSharedPath 一致；
        # 关键是把 http(s):// 形态正确解析为 HttpEndpoint，而不是误当本地目录
        # （旧实现只在 read_spec 存在时才走解析，http:// 写端会被 abspath 成本地路径）。
        return make_shared_path(write_spec, read_spec)

    def build_relay(self):
        if not self.relay:
            return None
        return RelayChannel(
            self.relay.get("host") or "127.0.0.1",
            int(self.relay.get("port", 0) or 0),
            token=self.relay.get("token"),
            timeout=float(self.relay.get("timeout", 3.0) or 3.0),
        )

    def build_session(self, role: Optional[str] = None) -> Session:
        """按配置构造会话（可覆盖角色）。"""
        return Session(
            role=role or self.role,
            shared=self.build_shared(),
            online=self.build_online(),
            relay=self.build_relay(),
            crypto=self.build_crypto(),
            name=self.name,
        )

    def action_cfg(self) -> dict:
        """给动作执行用的 cfg：sftp 配置（FTP_connect 形态）+ 密钥存在性。"""
        return {"sftp": self.sftp, "has_key": bool(self.key), "config_name": self.name}


def load_config(path_or_dict: Union[str, dict]) -> RhopConfig:
    """便捷入口：dict 或 JSON 文件路径 -> RhopConfig。"""
    if isinstance(path_or_dict, dict):
        return RhopConfig.from_dict(path_or_dict)
    return RhopConfig.from_file(path_or_dict)
