"""vools.rhop.session - A/B/C 三角拓扑会话模型（配置驱动地基 Step 3）

拓扑约束（analysis/rhop-PLAN.md 附录 C）：不存在多跳链；任何交互都可演化为
A[发送端]、B[接收端]、C[中转] 三角。A/B 反向传递只需调换角色复用同一套机制。

角色模型：
    Role.SEND  - 发送端 A：把加密动作包投递到介质/中转
    Role.RECV  - 接收端 B：从介质/中转取包、解密验证
    Role.RELAY - 中转 C：临时自建 HTTP 中转（RelayServer），A/B 不可直连时暂存/转交

会话（Session）持有角色 + 介质（在线通道列表 + shared path 视图）+ 对端/中转地址 + 密钥。
同一方可多角色：双向交互时 A 同时是 SEND+RECV（reverse() 互换角色复用同一份介质）。

通道选择链（C.3 升级后）：
    1. A -> C -> B 中转（C 在线、地址可达）-> 优先
    2. Git / SFTP（paramiko 优先）-> 次选
    3. shared path（多端视图）-> 最终回退
"""

import json
import time
from typing import Dict, List, Optional, Union

from .crypto import RhopCrypto
from .transport import (
    LocalSharedPath,
    RelayChannel,
    SharedPath,
    select_transport,
)


class Role(object):
    """会话角色常量（字符串，兼容 Py3.6）。"""

    SEND = "SEND"
    RECV = "RECV"
    RELAY = "RELAY"
    ALL = (SEND, RECV, RELAY)


class Session(object):
    """一次配置驱动会话：角色 + 介质 + 对端/中转 + 密钥。"""

    def __init__(
        self,
        role: str = Role.SEND,
        shared: Optional[SharedPath] = None,
        online: Optional[List] = None,
        relay: Optional[RelayChannel] = None,
        relay_server: Optional[object] = None,
        crypto: Optional[RhopCrypto] = None,
        name: Optional[str] = None,
    ):
        if role not in Role.ALL:
            raise ValueError("未知角色: %s（可用 %s）" % (role, Role.ALL))
        self.role = role
        self.shared = shared
        self.online = list(online) if online else []
        self.relay = relay          # 本端作为投递方视角的中转通道（RelayChannel）
        self.relay_server = relay_server  # 本端作为中转方自建的中转（RelayServer）
        self.crypto = crypto
        self.name = name or "session:{0}".format(role.lower())

    # ---- 介质可用性 ----

    def available(self) -> bool:
        """介质链是否至少有一条可用（中转 > 在线 > shared path）。"""
        if self.relay is not None and self.relay.available():
            return True
        for ch in self.online:
            if ch.available():
                return True
        return self.shared is not None and self.shared.available()

    def _pick_transport(self):
        """按通道选择链挑选传输对象，返回 (transport, label)。

        优先级: 中转 RelayChannel -> select_transport 在线通道 -> shared path 回退。
        """
        if self.relay is not None:
            try:
                if self.relay.available():
                    return self.relay, "relay"
            except Exception:
                pass
        if self.online:
            sel = select_transport(self.online, self.shared)
            if sel.is_online and sel.transport is not None:
                return sel.transport, "online"
        if self.shared is not None:
            return self.shared, "shared"
        raise IOError("rhop session: 无可用的传输介质（relay/online/shared 全不可达）")

    # ---- 发送 / 接收 ----

    def send_package(self, filename: str, payload: Union[Dict, str]) -> dict:
        """发送端：加密 JSON 载荷并投递到选定介质。

        返回: {"status": "ok", "transport": <label>, "filename": ...}
        """
        if self.role == Role.RELAY:
            raise ValueError("RELAY 角色不发送载荷，仅提供中转")
        if self.crypto is None:
            raise ValueError("会话未配置密钥（RhopCrypto）")
        token_text = self.crypto.encrypt_json(payload)
        transport, label = self._pick_transport()
        if label == "relay":
            transport.send(filename, token_text)
        elif label == "online":
            transport.send(filename, token_text)
        else:
            transport.write_text(filename, token_text)
        return {"status": "ok", "transport": label, "filename": filename,
                "role": self.role}

    def recv_package(self, filename: str) -> dict:
        """接收端：从介质取包并解密验证。

        返回: {"status": "ok", "transport": <label>, "payload": <解密后的 dict>}
        解密失败 -> {"status": "error", "reason": ...}
        """
        if self.role == Role.RELAY:
            raise ValueError("RELAY 角色不消费载荷，仅提供中转")
        if self.crypto is None:
            raise ValueError("会话未配置密钥（RhopCrypto）")
        transport, label = self._pick_transport()
        if label == "relay":
            token_text = transport.receive(filename)
        elif label == "online":
            token_text = transport.receive(filename)
        else:
            token_text = transport.read_text(filename)
        result = self.crypto.decrypt_verify(token_text)
        if not result.ok:
            return {"status": "error", "transport": label, "filename": filename,
                    "reason": result.reason}
        return {"status": "ok", "transport": label, "filename": filename,
                "payload": result.payload}

    # ---- 角色互换（反向传递复用同一套介质） ----

    def reverse(self) -> "Session":
        """互换角色：SEND <-> RECV；RELAY 保持 RELAY（中转无方向）。

        介质、密钥、中转地址原样复用，仅角色标签对调。
        """
        new_role = Role.RELAY if self.role == Role.RELAY else (
            Role.RECV if self.role == Role.SEND else Role.SEND
        )
        return Session(
            role=new_role,
            shared=self.shared,
            online=self.online,
            relay=self.relay,
            relay_server=self.relay_server,
            crypto=self.crypto,
            name=self.name,
        )

    def describe(self) -> dict:
        """会话描述（配置登记/调试用）。"""
        return {
            "name": self.name,
            "role": self.role,
            "online": [getattr(ch, "name", repr(ch)) for ch in self.online],
            "shared": getattr(self.shared, "name", None),
            "relay": getattr(self.relay, "base", None),
            "has_crypto": self.crypto is not None,
        }
