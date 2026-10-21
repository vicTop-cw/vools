"""SftpChannel 一跳配置（FTP_connect 形态 sftp_cfg）真实往返验证。

在当前进程内起线程化 paramiko SFTPServer（临时目录为根、跨连接共享），
用 {host, port, user, password, dir} 形态的一跳（直连）配置驱动
SftpChannel，验证 sftp_cfg 统一入口下 available / send / receive /
read_text / write_text / exists / listdir / mkdirs 全链路真实读写。

paramiko 不可用时整组跳过（与 SftpChannel 的注入式回退语义解耦）。
"""

import os
import socket
import tempfile
import threading

import pytest

try:
    import paramiko
    from paramiko import ServerInterface
    from paramiko.common import AUTH_SUCCESSFUL, AUTH_FAILED, OPEN_SUCCEEDED
    from paramiko.sftp_server import SFTPServer
    from paramiko.sftp_si import SFTPServerInterface
    from paramiko.sftp_handle import SFTPHandle
except Exception:  # pragma: no cover - 环境缺 paramiko 时整组跳过
    paramiko = None

from vools.rhop.transport.online import SftpChannel

pytestmark = pytest.mark.skipif(
    paramiko is None, reason="paramiko 未安装，跳过真实 SFTP 后端测试"
)


# ---- 极简 SFTP 服务端（根目录跨连接共享，模拟远端镜像目录） ----

_ROOT = None


def _make_root():
    global _ROOT
    if _ROOT is None:
        _ROOT = tempfile.mkdtemp(prefix="rhop-sftp-root-")
    return _ROOT


class _AuthServer(ServerInterface):
    def get_allowed_auths(self, username):
        return "p"

    def check_auth_password(self, username, password):
        if username == "test" and password == "pw123456":
            return AUTH_SUCCESSFUL
        return AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        return OPEN_SUCCEEDED


class _Handle(SFTPHandle):
    pass


class _FSServer(SFTPServerInterface):
    """把远端路径映射到全局共享临时根目录的极简 SFTP 服务端。"""

    def __init__(self, server, *args, **kwargs):
        super(_FSServer, self).__init__(server, *args, **kwargs)
        self.root = _make_root()

    def _abs(self, path):
        p = path.replace("\\", "/")
        if not p.startswith("/"):
            p = "/" + p
        return os.path.normpath(self.root + p.replace("/", os.sep))

    def _rel(self, abspath):
        r = os.path.relpath(abspath, self.root).replace(os.sep, "/")
        return "/" + r if r != "." else "/"

    def canonicalize(self, path):
        return self._rel(self._abs(path))

    def list_folder(self, path):
        try:
            names = os.listdir(self._abs(path))
        except OSError:
            return []
        out = []
        for n in sorted(names):
            ap = os.path.join(self._abs(path), n)
            st = os.stat(ap)
            attr = paramiko.SFTPAttributes.from_stat(st)
            attr.filename = n
            attr.longname = n
            out.append(attr)
        return out

    def stat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(os.stat(self._abs(path)))
        except OSError:
            return None

    def lstat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(os.lstat(self._abs(path)))
        except OSError:
            return None

    def open(self, path, flags, attr):
        ap = self._abs(path)
        # paramiko 5.0 SFTPServer 已把协议 flags 转换为 os.open 风格标志
        try:
            fd = os.open(ap, flags, 0o644)
        except OSError:
            return 2  # SFTP_NO_SUCH_FILE
        h = _Handle(flags)
        h.filename = ap
        readable = (flags & os.O_WRONLY) == 0 or (flags & os.O_RDWR) == os.O_RDWR
        writable = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND))
        if readable:
            h.readfile = os.fdopen(os.dup(fd), "rb")
        if writable:
            h.writefile = os.fdopen(fd, "wb")
        return h

    def remove(self, path):
        return 1  # 未实现：删除类操作不进测试链路

    def rename(self, oldpath, newpath):
        return 1

    def mkdir(self, path, attr):
        try:
            os.mkdir(self._abs(path))
            return 0
        except OSError:
            return 1

    def rmdir(self, path):
        return 1

    def chattr(self, path, attr):
        return 1

    def session_ended(self):
        pass


@pytest.fixture(scope="module")
def sftp_server():
    """线程内 paramiko SFTPServer，返回可用端口。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    port = sock.getsockname()[1]

    host_key = paramiko.RSAKey.generate(2048)
    transports = []

    def _accept_loop():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            try:
                t = paramiko.Transport(conn)
                t.add_server_key(host_key)
                t.set_subsystem_handler("sftp", SFTPServer, _FSServer)
                t.start_server(server=_AuthServer())
                transports.append(t)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

    th = threading.Thread(target=_accept_loop, daemon=True)
    th.start()
    yield port
    for t in transports:
        try:
            t.close()
        except Exception:
            pass
    try:
        sock.close()
    except Exception:
        pass


def _onehop_channel(port):
    cfg = {
        "host": "127.0.0.1",
        "port": port,
        "user": "test",
        "password": "pw123456",
        "dir": "/mirror",
    }
    return SftpChannel(host="", remote_dir="", sftp_cfg=cfg, probe_mode="sftp")


def test_onehop_probe(sftp_server):
    ch = _onehop_channel(sftp_server)
    try:
        assert ch.available() is True
    finally:
        ch.close()


def test_onehop_send_receive_roundtrip(sftp_server):
    ch = _onehop_channel(sftp_server)
    try:
        ch.mkdirs("sub")
        ch.send("hello.json", '{"ok": true}')
        assert ch.receive("hello.json") == '{"ok": true}'
        assert ch.get("hello.json") == '{"ok": true}'
    finally:
        ch.close()


def test_onehop_fs_semantics(sftp_server):
    ch = _onehop_channel(sftp_server)
    try:
        assert ch.exists("hello.json") is True
        assert ch.exists("no-such.json") is False
        names = ch.listdir("")
        assert "hello.json" in names
        assert "sub" in names
        ch.write_text("note.txt", "line1\nline2")
        assert ch.read_text("note.txt") == "line1\nline2"
    finally:
        ch.close()
