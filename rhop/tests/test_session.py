"""Step 3 判据：A/B/C 三角拓扑会话模型。

判据：A->B 直连往返、A->C->B 中转往返、B->A 反向往返三条路径通过；
同一份介质/密钥互换角色复用，不需新增代码。
"""

import threading
import time

import pytest

from vools.rhop.crypto import RhopCrypto
from vools.rhop.session import Role, Session
from vools.rhop.transport import LocalSharedPath, RelayChannel, RelayServer

KEY = "session-topology-key"
TOKEN = "topo-token"


def _shared(tmp_path):
    return LocalSharedPath(str(tmp_path / "share"))


def _sessions(shared, role_a=Role.SEND, role_b=Role.RECV):
    a = Session(role=role_a, shared=shared, crypto=RhopCrypto.from_key(KEY))
    b = Session(role=role_b, shared=shared, crypto=RhopCrypto.from_key(KEY))
    return a, b


class TestRoleModel:
    def test_reverse_swap_send_recv(self):
        a, b = _sessions(_shared)
        assert a.reverse().role == Role.RECV
        assert b.reverse().role == Role.SEND
        assert a.reverse().reverse().role == Role.SEND

    def test_reverse_relay_keeps_relay(self):
        c = Session(role=Role.RELAY, crypto=RhopCrypto.from_key(KEY))
        assert c.reverse().role == Role.RELAY

    def test_invalid_role_rejected(self):
        with pytest.raises(ValueError):
            Session(role="X", crypto=RhopCrypto.from_key(KEY))

    def test_no_crypto_send_rejected(self, tmp_path):
        sess = Session(role=Role.SEND, shared=_shared(tmp_path))
        with pytest.raises(ValueError):
            sess.send_package("x.rhop", {"a": 1})


class TestDirectTopology:
    def test_judge_a_to_b_direct(self, tmp_path):
        """判据 A->B 直连：A 加密投递 shared path，B 取回解密验证 OK。"""
        shared = _shared(tmp_path)
        a, b = _sessions(shared)
        sent = a.send_package("pkg-a.rhop", {"task": "direct", "seq": 1})
        assert sent["status"] == "ok"
        assert sent["transport"] == "shared"

        received = b.recv_package("pkg-a.rhop")
        assert received["status"] == "ok"
        assert received["payload"] == {"task": "direct", "seq": 1}

    def test_judge_b_to_a_reverse(self, tmp_path):
        """判据 B->A 反向：同一份介质互换角色复用，无需新增代码。"""
        shared = _shared(tmp_path)
        a, b = _sessions(shared)
        # B 用 reverse 会话反向发送
        b_rev = b.reverse()
        assert b_rev.role == Role.SEND
        sent = b_rev.send_package("pkg-b.rhop", {"task": "reverse", "seq": 2})
        assert sent["status"] == "ok"

        a_recv = a.reverse()  # A 反转为 RECV
        assert a_recv.role == Role.RECV
        received = a_recv.recv_package("pkg-b.rhop")
        assert received["status"] == "ok"
        assert received["payload"] == {"task": "reverse", "seq": 2}

    def test_bidirectional_same_media(self, tmp_path):
        """双向交互：A 收一条、发一条，介质与密钥完全复用。"""
        shared = _shared(tmp_path)
        a, b = _sessions(shared)
        a.send_package("q1.rhop", {"dir": "a->b"})
        a_rev = a.reverse()
        a_rev.send_package("q2.rhop", {"dir": "b->a"})

        r1 = b.recv_package("q1.rhop")
        r2 = b.reverse().recv_package("q2.rhop")
        assert r1["payload"]["dir"] == "a->b"
        assert r2["payload"]["dir"] == "b->a"

    def test_wrong_key_verify_fails(self, tmp_path):
        """密钥不符：解密验证明确失败（reason=BAD_TOKEN）。"""
        shared = _shared(tmp_path)
        a = Session(role=Role.SEND, shared=shared, crypto=RhopCrypto.from_key(KEY))
        a.send_package("pkg-w.rhop", {"secret": "x"})
        b = Session(role=Role.RECV, shared=shared,
                    crypto=RhopCrypto.from_key("wrong-key"))
        received = b.recv_package("pkg-w.rhop")
        assert received["status"] == "error"
        assert received["reason"] == "BAD_TOKEN"


class TestRelayTopology:
    def test_judge_a_to_c_to_b(self, tmp_path):
        """判据 A->C->B 中转：C 自建中转，A 经中转投递，B 从中转取回。"""
        c = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=60).start()
        try:
            ch = RelayChannel(c.host, c.port, token=TOKEN)
            a = Session(role=Role.SEND, relay=ch, crypto=RhopCrypto.from_key(KEY))
            b = Session(role=Role.RECV, relay=ch, crypto=RhopCrypto.from_key(KEY))

            sent = a.send_package("pkg-c.rhop", {"task": "via-relay", "seq": 3})
            assert sent["status"] == "ok"
            assert sent["transport"] == "relay"

            received = b.recv_package("pkg-c.rhop")
            assert received["status"] == "ok"
            assert received["transport"] == "relay"
            assert received["payload"] == {"task": "via-relay", "seq": 3}
        finally:
            c.stop()

    def test_relay_preferred_over_shared(self, tmp_path):
        """通道选择链：中转可达时优先于 shared path。"""
        c = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=30).start()
        try:
            shared = _shared(tmp_path)
            ch = RelayChannel(c.host, c.port, token=TOKEN)
            a = Session(role=Role.SEND, relay=ch, shared=shared,
                        crypto=RhopCrypto.from_key(KEY))
            sent = a.send_package("pkg-p.rhop", {"prefer": "relay"})
            assert sent["transport"] == "relay"
        finally:
            c.stop()

    def test_relay_down_falls_back_shared(self, tmp_path):
        """中转不可达 -> 自动回退 shared path，链路不中断。"""
        shared = _shared(tmp_path)
        dead = RelayChannel("127.0.0.1", 1, token=TOKEN, timeout=0.3)
        a = Session(role=Role.SEND, relay=dead, shared=shared,
                    crypto=RhopCrypto.from_key(KEY))
        sent = a.send_package("pkg-f.rhop", {"fallback": "shared"})
        assert sent["transport"] == "shared"

    def test_no_media_raises(self):
        sess = Session(role=Role.SEND, crypto=RhopCrypto.from_key(KEY))
        with pytest.raises(IOError):
            sess.send_package("x.rhop", {"a": 1})
