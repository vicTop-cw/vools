"""Step 2 判据：rhop.actions 公开动作集（jump.probe/push/pull/sync）+ Ω-gate 容错解包。

- 复用 test_sftp_live 的线程化 paramiko SFTPServer 装置做真实往返验证
- 判据：动作集测试全绿；本机配置下 jump.push 一文件 + jump.pull 拉回验证
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
except Exception:  # pragma: no cover
    paramiko = None

from vools.rhop.actions import ACTIONS, omega_unwrap, run_action
from vools.rhop.actions.jump import jump_probe, jump_pull, jump_push, jump_sync

pytestmark = pytest.mark.skipif(
    paramiko is None, reason="paramiko 未安装，跳过真实 SFTP 后端测试"
)


# ---- 线程化 paramiko SFTPServer（复用 test_sftp_live 极简实现） ----

_ROOT = None


def _make_root():
    global _ROOT
    if _ROOT is None:
        _ROOT = tempfile.mkdtemp(prefix="rhop-actions-root-")
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
        try:
            fd = os.open(ap, flags, 0o644)
        except OSError:
            return 2
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
        return 1

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
    """线程内 paramiko SFTPServer，返回 (port, root)。"""
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
    yield port, _make_root()
    for t in transports:
        try:
            t.close()
        except Exception:
            pass
    try:
        sock.close()
    except Exception:
        pass


def _cfg(port, **over):
    base = {
        "host": "127.0.0.1",
        "port": port,
        "user": "test",
        "password": "pw123456",
        "timeout": 20,
    }
    base.update(over)
    return {"sftp": base}


class TestJumpProbe:
    def test_probe_reachable(self, sftp_server):
        port, _ = sftp_server
        result = jump_probe(_cfg(port))
        assert result["status"] == "ok"
        assert result["reachable"] is True
        assert result["transport"] == "paramiko"

    def test_probe_missing_host(self):
        result = jump_probe({"sftp": {"port": 22}})
        assert result["status"] == "ok"
        assert result["reachable"] is False
        assert "host" in result["detail"]

    def test_probe_unreachable_port(self):
        result = jump_probe(_cfg(1, timeout=3))
        assert result["status"] == "ok"
        assert result["reachable"] is False


class TestJumpPushPull:
    def test_judge_push_pull_roundtrip(self, sftp_server, tmp_path):
        """判据：jump.push 一文件 + jump.pull 拉回，内容往返一致。"""
        port, root = sftp_server
        src = tmp_path / "src.txt"
        src.write_text("rhop actions roundtrip", encoding="utf-8")

        pushed = jump_push(_cfg(port), {
            "local_path": str(src),
            "remote_path": "/rhop-actions/roundtrip/src.txt",
        })
        assert pushed["status"] == "ok"
        assert pushed["files_transferred"] == 1
        assert pushed["bytes"] > 0
        assert pushed["transport"] == "paramiko"

        # 远端落盘确认
        assert os.path.isfile(os.path.join(root, "rhop-actions", "roundtrip", "src.txt"))

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        pulled = jump_pull(_cfg(port), {
            "remote_path": "/rhop-actions/roundtrip/src.txt",
            "local_path": str(out_dir),
        })
        assert pulled["status"] == "ok"
        assert pulled["files_transferred"] == 1
        assert (out_dir / "src.txt").read_text(encoding="utf-8") == "rhop actions roundtrip"

    def test_push_dir_recursive_with_exclude(self, sftp_server, tmp_path):
        port, root = sftp_server
        tree = tmp_path / "tree"
        (tree / "sub").mkdir(parents=True)
        (tree / "a.txt").write_text("a", encoding="utf-8")
        (tree / "sub" / "b.txt").write_text("b", encoding="utf-8")
        (tree / "sub" / "skip.tmp").write_text("x", encoding="utf-8")

        pushed = jump_push(_cfg(port), {
            "local_path": str(tree),
            "remote_path": "/rhop-actions/tree",
            "exclude": ["*.tmp"],
        })
        assert pushed["status"] == "ok"
        assert pushed["files_transferred"] == 2
        base = os.path.join(root, "rhop-actions", "tree")
        assert os.path.isfile(os.path.join(base, "a.txt"))
        assert os.path.isfile(os.path.join(base, "sub", "b.txt"))
        assert not os.path.exists(os.path.join(base, "sub", "skip.tmp"))

    def test_push_missing_payload_fields(self, sftp_server):
        port, _ = sftp_server
        result = jump_push(_cfg(port), {"local_path": "x"})
        assert result["status"] == "error"
        assert "remote_path" in result["message"]

    def test_push_dry_run(self, sftp_server, tmp_path):
        port, _ = sftp_server
        src = tmp_path / "d.txt"
        src.write_text("d", encoding="utf-8")
        result = jump_push(_cfg(port), {
            "local_path": str(src),
            "remote_path": "/rhop-actions/dry.txt",
            "dry_run": True,
        })
        assert result["status"] == "ok"
        assert result["dry_run"] is True
        assert result["files_transferred"] == 0

    def test_pull_missing_local_dir(self, sftp_server):
        port, _ = sftp_server
        result = jump_pull(_cfg(port), {"remote_path": "/nope.txt"})
        assert result["status"] == "error"


class TestJumpSync:
    def test_sync_upload_missing_only(self, sftp_server, tmp_path):
        port, root = sftp_server
        # 远端已存在同名文件（新内容），本地有另一个新文件
        os.makedirs(os.path.join(root, "rhop-sync"), exist_ok=True)
        with open(os.path.join(root, "rhop-sync", "same.txt"), "w", encoding="utf-8") as fh:
            fh.write("remote-old")

        local = tmp_path / "sync"
        local.mkdir()
        (local / "same.txt").write_text("same-remote", encoding="utf-8")
        (local / "new.txt").write_text("new", encoding="utf-8")

        result = jump_sync(_cfg(port), {
            "local_path": str(local),
            "remote_path": "/rhop-sync",
            "direction": "upload",
        })
        assert result["status"] == "ok"
        # 对齐 actus 语义：单向 upload 以本地为权威，冲突文件被覆盖
        assert result["uploaded"] == 2
        assert result["downloaded"] == 0
        assert os.path.isfile(os.path.join(root, "rhop-sync", "new.txt"))
        assert open(os.path.join(root, "rhop-sync", "same.txt"), encoding="utf-8").read() == "same-remote"

    def test_sync_dry_run_plan(self, sftp_server, tmp_path):
        port, _ = sftp_server
        local = tmp_path / "sd"
        local.mkdir()
        (local / "only-local.txt").write_text("x", encoding="utf-8")
        result = jump_sync(_cfg(port), {
            "local_path": str(local),
            "remote_path": "/rhop-sync-dry",
            "direction": "both",
            "dry_run": True,
        })
        assert result["status"] == "ok"
        assert result["dry_run"] is True
        assert result["upload"] == 1

    def test_sync_bytes_counted_for_download(self, sftp_server, tmp_path):
        """BUG-301 回归：双向同步时 downloaded 文件的 bytes 必须被累加。

        修复前：下载循环只累加 counter["files"]，不累加 counter["bytes"]，
        导致 bytes 字段只反映上传量，丢失下载量。
        """
        port, root = sftp_server
        # 远端放一个只有远端有的文件（下载方向）
        os.makedirs(os.path.join(root, "rhop-bug301"), exist_ok=True)
        with open(os.path.join(root, "rhop-bug301", "remote-only.txt"), "w", encoding="utf-8") as fh:
            fh.write("remote-content-here")

        # 本地放一个只有本地有的文件（上传方向）
        local = tmp_path / "bug301"
        local.mkdir()
        (local / "local-only.txt").write_text("local-content-here", encoding="utf-8")

        result = jump_sync(_cfg(port), {
            "local_path": str(local),
            "remote_path": "/rhop-bug301",
            "direction": "both",
        })
        assert result["status"] == "ok"
        assert result["uploaded"] == 1
        assert result["downloaded"] == 1
        # bytes 必须同时包含上传和下载的字节数
        expected_bytes = (
            os.path.getsize(str(local / "local-only.txt"))
            + os.path.getsize(os.path.join(root, "rhop-bug301", "remote-only.txt"))
        )
        assert result["bytes"] == expected_bytes, (
            "BUG-301: bytes=%d 应为 %d（上传+下载）" % (result["bytes"], expected_bytes)
        )


class TestActionRegistry:
    def test_registry_contains_all_jump_actions(self):
        assert set(ACTIONS.keys()) == {"jump.probe", "jump.push", "jump.pull", "jump.sync"}

    def test_run_action_unknown(self):
        result = run_action("jump.nope", {})
        assert result["status"] == "error"
        assert "omega_gate" in result
        assert "未知动作" in result["omega_gate"]["error"]

    def test_run_action_ok(self, sftp_server):
        port, _ = sftp_server
        result = run_action("jump.probe", _cfg(port))
        assert result["status"] == "ok"
        assert result["action"] == "jump.probe"
        assert result["data"]["reachable"] is True

    def test_omega_unwrap_ok(self):
        inner = {"status": "ok", "files_transferred": 3, "bytes": 99}
        result = omega_unwrap({"status": "ok", "action": "jump.push", "data": inner})
        assert result is inner

    def test_omega_unwrap_partial_is_ok(self):
        inner = {"status": "partial", "files_transferred": 1, "bytes": 5, "errors": ["x"]}
        result = omega_unwrap({"status": "ok", "action": "jump.push", "data": inner})
        assert result is inner

    def test_omega_unwrap_inner_error(self):
        inner = {"status": "error", "message": "连接失败"}
        result = omega_unwrap({"status": "ok", "action": "jump.push", "data": inner})
        assert result["status"] == "error"
        assert result["omega_gate"]["action"] == "jump.push"
        assert "内层 status=error" in result["omega_gate"]["error"]

    def test_omega_unwrap_outer_error(self):
        result = omega_unwrap({"status": "error", "omega_gate": {"error": "未知动作"}})
        assert result["status"] == "error"
        assert result["omega_gate"]["error"] == "未知动作"

    def test_omega_unwrap_non_dict(self):
        result = omega_unwrap("boom")
        assert result["status"] == "error"
