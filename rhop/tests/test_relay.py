"""MVP-3 判据 5/6/7: 双方自建临时服务器中转（异步机器）。

判据5: A 自建临时中转服务器，B 投递加密 JSON 包，A 取回并解密验证 OK
判据6: 中转不可达 -> 自动回退 Git/SFTP -> 再回退 shared path，链路不中断
判据7: TTL 过期自动关闭；包被取走后中转不留明文残留
"""

import json
import os
import subprocess
import sys
import time

import pytest

from vools.rhop.crypto import RhopCrypto
from vools.rhop.transport import (
    GitChannel,
    LocalSharedPath,
    RelayChannel,
    RelayServer,
    SftpChannel,
    select_transport,
)

KEY = "relay-key"
TOKEN = "cfg-shared-token"

# 异步投递方（独立进程 B）脚本：经配置告知的地址 + token 投递加密包
_CLIENT_SCRIPT = r"""
import os, sys
sys.path[:0] = os.environ["RHOP_PYTHONPATH"].split(os.pathsep)
from vools.rhop.crypto import RhopCrypto
from vools.rhop.transport import RelayChannel

host, port, token, key = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
c = RhopCrypto.from_key(key)
token_text = c.encrypt_json({"task": "relay-cross-process", "seq": 5, "src": "process-B"})
ch = RelayChannel(host, port, token=token)
ch.send("pkg.rhop", token_text)
print("SENT", ch.base)
"""


def _env():
    env = dict(os.environ)
    roots = [p for p in sys.path if p and "vools" in p.replace("\\", "/").lower()]
    env["RHOP_PYTHONPATH"] = os.pathsep.join(roots)
    return env


class TestRelayRoundtrip:
    def test_judge5_async_self_hosted_relay(self):
        """判据5: A 自建中转，B(子进程) 投递，A 取回解密验证 OK。"""
        server = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=60).start()
        try:
            # 配置告知: 把 url + token 交给对端（此处模拟写入配置后传给子进程）
            host, port = server.host, server.port
            assert port != 0

            proc = subprocess.run(
                [sys.executable, "-c", _CLIENT_SCRIPT, host, str(port), TOKEN, KEY],
                capture_output=True,
                text=True,
                env=_env(),
                timeout=30,
            )
            assert proc.returncode == 0, proc.stderr
            assert proc.stdout.strip() == "SENT http://{0}:{1}".format(host, port)

            # A 取回并解密验证
            client = RelayChannel(host, port, token=TOKEN)
            assert client.available()
            content = client.receive("pkg.rhop")
            result = RhopCrypto.from_key(KEY).decrypt_verify(content)
            assert result.ok is True
            assert result.payload == {"task": "relay-cross-process", "seq": 5, "src": "process-B"}
        finally:
            server.stop()

    def test_wrong_token_rejected(self):
        """token 不符: 投递被拒，中转不接收。"""
        server = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=30).start()
        try:
            bad = RelayChannel(server.host, server.port, token="wrong")
            with pytest.raises(IOError):
                bad.send("x.rhop", "encrypted-json")
            # 未被接收，包不存在
            good = RelayChannel(server.host, server.port, token=TOKEN)
            with pytest.raises(FileNotFoundError):
                good.receive("x.rhop")
        finally:
            server.stop()


class TestRelayFallback:
    def test_judge6_fallback_to_git_when_relay_down(self, tmp_path):
        """中转不可达 -> 有可用在线通道(Git)则走 Git。"""
        relay_down = RelayChannel("127.0.0.1", 1, token=TOKEN, timeout=0.3)
        git_up = GitChannel("git@example.invalid:repo.git", probe=lambda: True)
        shared = LocalSharedPath(str(tmp_path / "s"))
        sel = select_transport([relay_down, git_up], shared)
        assert sel.is_online is True
        assert sel.transport is git_up

    def test_judge6_fallback_to_shared_path_when_relay_and_online_down(self, tmp_path):
        """中转与 Git/SFTP 均不可达 -> 回退 shared path，链路不中断。"""
        relay_down = RelayChannel("127.0.0.1", 1, token=TOKEN, timeout=0.3)
        git_down = GitChannel("git@example.invalid:repo.git", probe=lambda: False)
        sftp_down = SftpChannel("192.0.2.1", "/srv", probe=lambda: False)
        shared = LocalSharedPath(str(tmp_path / "s"))
        sel = select_transport([relay_down, git_down, sftp_down], shared)
        assert sel.is_online is False
        assert sel.transport is shared
        assert "回退" in sel.reason

    def test_judge6_relay_preferred_over_git_when_up(self, tmp_path):
        """双方可达时自建中转优先于 Git。"""
        server = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=30).start()
        try:
            relay_up = RelayChannel(server.host, server.port, token=TOKEN)
            git_up = GitChannel("git@example.invalid:repo.git", probe=lambda: True)
            shared = LocalSharedPath(str(tmp_path / "s"))
            sel = select_transport([relay_up, git_up], shared)
            assert sel.is_online is True
            assert sel.transport is relay_up
        finally:
            server.stop()


class TestRelayLifecycle:
    def test_judge7_ttl_auto_close(self):
        """TTL 到期自动关闭，alive 变 False、不可再探测。"""
        server = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=1.0).start()
        assert server.alive()
        time.sleep(1.6)
        assert not server.alive()
        ch = RelayChannel(server.host, server.port, token=TOKEN, timeout=0.3)
        assert ch.available() is False

    def test_judge7_no_leftover_after_take(self):
        """包被取走后中转不留明文残留（packages 已清空）。"""
        server = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=30).start()
        try:
            client = RelayChannel(server.host, server.port, token=TOKEN)
            c = RhopCrypto.from_key(KEY)
            client.send("pkg.rhop", c.encrypt_json({"a": 1}))
            assert list(server.packages.keys()) == ["pkg.rhop"]
            client.receive("pkg.rhop")
            assert len(server.packages) == 0, "取走后不应残留密文包"
        finally:
            server.stop()

    def test_stop_clears_all(self):
        """stop() 后清空所有暂存包。"""
        server = RelayServer(host="127.0.0.1", port=0, token=TOKEN, ttl=30).start()
        client = RelayChannel(server.host, server.port, token=TOKEN)
        client.send("a.rhop", RhopCrypto.from_key(KEY).encrypt_json({"a": 1}))
        client.send("b.rhop", RhopCrypto.from_key(KEY).encrypt_json({"b": 2}))
        assert len(server.packages) == 2
        server.stop()
        assert len(server.packages) == 0
        assert not server.alive()
