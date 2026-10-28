"""MVP 判据 2/3: 同机两进程 shared path 收发成功；在线优先/离线回退。"""

import os
import subprocess
import sys

from vools.rhop.crypto import RhopCrypto
from vools.rhop.transport import (
    GitChannel,
    LocalSharedPath,
    SftpChannel,
    select_transport,
)

KEY = "two-process-key"

# 供 subprocess 使用的发送端脚本（进程 A）：加密 JSON 写入 shared path
_SENDER_SCRIPT = r"""
import json, os, sys
sys.path[:0] = os.environ["RHOP_PYTHONPATH"].split(os.pathsep)
from vools.rhop.crypto import RhopCrypto

shared_root = sys.argv[1]
c = RhopCrypto.from_key("two-process-key")
payload = {"task": "cross-process", "n": 7, "src": "process-A"}
token = c.encrypt_json(payload)
path = os.path.join(shared_root, "pkg.rhop")
with open(path, "w", encoding="utf-8") as fh:
    fh.write(token)
print("SENT", os.path.abspath(path))
"""

# 供 subprocess 使用的接收端脚本（进程 B）：读取并解密验证
_RECEIVER_SCRIPT = r"""
import json, os, sys
sys.path[:0] = os.environ["RHOP_PYTHONPATH"].split(os.pathsep)
from vools.rhop.crypto import RhopCrypto

shared_root = sys.argv[1]
c = RhopCrypto.from_key("two-process-key")
path = os.path.join(shared_root, "pkg.rhop")
with open(path, "r", encoding="utf-8") as fh:
    token = fh.read()
res = c.decrypt_verify(token)
print("RESULT", res.ok, res.reason, json.dumps(res.payload, ensure_ascii=False, sort_keys=True))
"""


def _env():
    env = dict(os.environ)
    roots = [p for p in sys.path if p and "vools" in p.replace("\\", "/").lower()]
    env["RHOP_PYTHONPATH"] = os.pathsep.join(roots)
    return env


def _run_py(script, *args):
    proc = subprocess.run(
        [sys.executable, "-c", script] + list(args),
        capture_output=True,
        text=True,
        env=_env(),
        timeout=60,
    )
    assert proc.returncode == 0, "subprocess failed: {0}".format(proc.stderr)
    return proc.stdout.strip()


class TestTwoProcessSharedPath:
    def test_ab_roundtrip(self, tmp_path):
        shared_root = str(tmp_path / "shared")
        os.makedirs(shared_root, exist_ok=True)

        out_a = _run_py(_SENDER_SCRIPT, shared_root)
        assert out_a.startswith("SENT")

        out_b = _run_py(_RECEIVER_SCRIPT, shared_root)
        assert "RESULT True OK" in out_b
        assert '"task": "cross-process"' in out_b
        assert '"src": "process-A"' in out_b

        # 收完后 shared path 上确实存在该包
        shared = LocalSharedPath(shared_root)
        assert shared.exists("pkg.rhop")
        assert shared.available()

    def test_shared_path_api(self, tmp_path):
        shared = LocalSharedPath(str(tmp_path / "s"))
        assert shared.available()
        path = shared.write_text("a.rhop", "hello")
        assert shared.read_text("a.rhop") == "hello"
        assert shared.exists("a.rhop")
        assert shared.remove("a.rhop") is True
        assert not shared.exists("a.rhop")


class TestChannelSelection:
    def test_online_preferred_when_available(self, tmp_path):
        git = GitChannel("git@example.invalid:repo.git", probe=lambda: True)
        shared = LocalSharedPath(str(tmp_path / "s"))
        sel = select_transport([git], shared)
        assert sel.is_online is True
        assert sel.transport is git
        assert "在线" in sel.reason

    def test_fallback_to_shared_path_when_offline(self, tmp_path):
        git = GitChannel("git@example.invalid:repo.git", probe=lambda: False)
        sftp = SftpChannel("192.0.2.1", "/srv/rhop", probe=lambda: False)
        shared = LocalSharedPath(str(tmp_path / "s"))
        sel = select_transport([git, sftp], shared)
        assert sel.is_online is False
        assert sel.transport is shared
        assert "回退" in sel.reason

    def test_first_available_online_wins(self, tmp_path):
        git_down = GitChannel("git@example.invalid:repo.git", probe=lambda: False)
        git_up = GitChannel("git@example.invalid:repo2.git", probe=lambda: True)
        shared = LocalSharedPath(str(tmp_path / "s"))
        sel = select_transport([git_down, git_up], shared)
        assert sel.is_online is True
        assert sel.transport is git_up

    def test_all_offline_and_shared_unavailable(self, tmp_path):
        git = GitChannel("git@example.invalid:repo.git", probe=lambda: False)
        # 强制 shared path 不可达：父路径是一个普通文件，无法在其下建目录
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir", encoding="utf-8")
        shared = LocalSharedPath(str(blocker / "sub"))
        sel = select_transport([git], shared)
        assert sel.is_online is False
        assert "不可达" in sel.reason


class _FakeBackend(object):
    """不发网络的 paramiko 后端替身：验证 send/receive 走 backend 优先。"""

    def __init__(self, store=None, fail=False):
        self.store = store if store is not None else {}
        self.fail = fail

    def put(self, filename, content):
        if self.fail:
            raise IOError("boom")
        self.store[filename] = content

    def get(self, filename):
        if self.fail:
            raise IOError("boom")
        return self.store[filename]

    def available(self):
        return not self.fail

    def exists(self, filename):
        return filename in self.store

    def listdir(self, sub=""):
        return sorted(self.store)

    def mkdirs(self, sub=""):
        return None

    def close(self):
        return None


class TestSftpChannelParamiko:
    def test_backend_created_when_paramiko_available(self, monkeypatch):
        ch = SftpChannel("example.invalid", "/srv/rhop", probe=lambda: False)
        assert ch._backend is not None  # paramiko 已安装

    def test_send_receive_uses_backend_first(self, monkeypatch):
        store = {}
        ch = SftpChannel(
            "example.invalid", "/srv/rhop",
            probe=lambda: False,
            writer=lambda *a: store.setdefault("injected", []).append(a),
            reader=lambda *a: "injected-read",
        )
        monkeypatch.setattr(ch, "_backend", _FakeBackend(store))
        ch.send("pkg.rhop", "paramiko-content")
        assert store["pkg.rhop"] == "paramiko-content"
        assert "injected" not in store  # 未走注入

        assert ch.receive("pkg.rhop") == "paramiko-content"
        assert ch.get("pkg.rhop") == "paramiko-content"
        assert ch.read_text("pkg.rhop") == "paramiko-content"
        ch.write_text("b.rhop", "text")
        assert store["b.rhop"] == "text"

    def test_fallback_to_injected_when_backend_fails(self, monkeypatch):
        calls = {}
        ch = SftpChannel(
            "example.invalid", "/srv/rhop",
            probe=lambda: False,
            writer=lambda *a: calls.setdefault("w", []).append(a),
            reader=lambda *a: "injected-read",
        )
        monkeypatch.setattr(ch, "_backend", _FakeBackend(fail=True))
        ch.send("pkg.rhop", "content")
        assert calls["w"]  # 回退注入 writer
        assert ch.receive("pkg.rhop") == "injected-read"  # 回退注入 reader

    def test_no_backend_no_injection_raises(self, monkeypatch):
        ch = SftpChannel("example.invalid", "/srv/rhop", probe=lambda: False)
        monkeypatch.setattr(ch, "_backend", None)
        try:
            ch.send("a.rhop", "x")
            raise AssertionError("expected NotImplementedError")
        except NotImplementedError:
            pass
        try:
            ch.receive("a.rhop")
            raise AssertionError("expected NotImplementedError")
        except NotImplementedError:
            pass

    def test_probe_mode_sftp_uses_backend_available(self, monkeypatch):
        ch = SftpChannel(
            "example.invalid", "/srv/rhop",
            probe=None, probe_mode="sftp",
        )
        monkeypatch.setattr(ch, "_backend", _FakeBackend(fail=False))
        assert ch.available() is True
        monkeypatch.setattr(ch, "_backend", _FakeBackend(fail=True))
        assert ch.available() is False

    def test_explicit_probe_wins(self):
        ch = SftpChannel("example.invalid", "/srv/rhop", probe=lambda: False)
        assert ch.available() is False

    def test_sftp_cfg_merge(self):
        ch = SftpChannel(
            "fallback.invalid", "/fallback",
            sftp_cfg={
                "host": "cfg.invalid", "port": 2222, "user": "cfguser",
                "password": "secret", "dir": "/cfg/dir",
            },
        )
        assert ch.host == "cfg.invalid"
        assert ch.port == 2222
        assert ch.username == "cfguser"
        assert ch.remote_dir == "/cfg/dir"
        assert ch._backend.host == "cfg.invalid"
        assert ch._backend.port == 2222
        assert ch._backend.username == "cfguser"
        assert ch._backend.password == "secret"
        assert ch._backend.remote_dir == "/cfg/dir"

    def test_filesystem_semantics_via_backend(self, monkeypatch):
        store = {"a.rhop": "hello"}
        ch = SftpChannel("example.invalid", "/srv/rhop", probe=lambda: False)
        monkeypatch.setattr(ch, "_backend", _FakeBackend(store))
        assert ch.exists("a.rhop") is True
        assert ch.exists("missing.rhop") is False
        assert ch.listdir() == ["a.rhop"]
        ch.mkdirs("sub")
        ch.close()

    def test_filesystem_semantics_without_backend_raise(self, monkeypatch):
        ch = SftpChannel("example.invalid", "/srv/rhop", probe=lambda: False)
        monkeypatch.setattr(ch, "_backend", None)
        for fn in (lambda: ch.exists("a"), lambda: ch.listdir(), lambda: ch.mkdirs()):
            try:
                fn()
                raise AssertionError("expected NotImplementedError")
            except NotImplementedError:
                pass


class TestSftpChannelParamikoMissing:
    """paramiko 导入失败：SftpChannel 无后端，只能靠注入式 reader/writer。

    注意 `available()` 的语义（2026-10-28 修正）：无后端且未注入时**直接 False**，
    不再因为 TCP 端口通就报可用——否则 select_transport 会选中一条 send/receive
    必然抛 NotImplementedError 的通道。「端口通不通」改由 `port_reachable()` 回答。
    """

    def test_no_backend_when_paramiko_missing(self, monkeypatch):
        import vools.rhop.transport.online as online_mod

        monkeypatch.setattr(online_mod, "paramiko", None)
        ch = SftpChannel("example.invalid", "/srv/rhop", probe=lambda: False)
        assert ch._backend is None
        assert ch.available() is False  # probe 注入优先

    def test_injected_roundtrip_when_paramiko_missing(self, monkeypatch):
        import vools.rhop.transport.online as online_mod

        store = {}
        monkeypatch.setattr(online_mod, "paramiko", None)
        ch = SftpChannel(
            "example.invalid", "/srv/rhop",
            probe=lambda: False,
            writer=lambda ch_, fn, content: store.__setitem__(fn, content),
            reader=lambda ch_, fn: store[fn],
        )
        ch.send("pkg.rhop", "fallback-content")
        assert store["pkg.rhop"] == "fallback-content"
        assert ch.receive("pkg.rhop") == "fallback-content"

    def test_probe_mode_sftp_without_paramiko_falls_to_tcp(self, monkeypatch):
        import vools.rhop.transport.online as online_mod

        monkeypatch.setattr(online_mod, "paramiko", None)
        calls = []
        monkeypatch.setattr(
            online_mod, "_default_sftp_probe",
            lambda host, port: calls.append((host, port)) or False,
        )
        ch = SftpChannel("example.invalid", "/srv/rhop", probe=None, probe_mode="sftp")
        # 无后端且未注入 ⇒ 不可用；**且不触发网络探测**（不拿端口通冒充可用）
        assert ch.available() is False
        assert calls == []
        # 「端口通不通」是另一个问题：probe_mode="sftp" 在无 paramiko 时降级到 TCP 探测
        assert ch.port_reachable() is False
        assert calls == [("example.invalid", 22)]  # 降级 TCP 探测
