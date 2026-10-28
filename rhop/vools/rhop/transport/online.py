"""vools.rhop.transport.online - 在线通道（Git 仓库中继 / SFTP 镜像）

MVP 阶段: 通道可用性探测（available）优先落地，send/receive 给出基础实现；
测试中可注入 probe 函数模拟"有网/无网"以验证在线优先 / 离线回退选择。

GitChannel:
    把加密 JSON 作为文件提交并推送 / 拉取。可用性探测: 远端可连通（git ls-remote）。
SftpChannel:
    把加密 JSON 写到 SFTP 镜像目录 / 从镜像目录读取。paramiko 优先（真实读写），
    paramiko 缺失或连接失败时回退注入式 reader/writer。
"""

import os
import subprocess
import tempfile
from typing import Callable, Optional

from .base import OnlineChannel

try:  # paramiko 为可选依赖：缺失时回退注入式读写
    import paramiko  # type: ignore
except Exception:  # pragma: no cover - 取决于运行环境
    paramiko = None

# 探测函数类型: 返回 (ok, 说明)
Probe = Callable[[], bool]


def _default_git_probe(remote_url: str, timeout: float = 5.0) -> bool:
    """默认 Git 可用性探测: git ls-remote --heads <url>。"""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", remote_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def _default_sftp_probe(host: str, port: int = 22, timeout: float = 5.0) -> bool:
    """默认 SFTP 可用性探测: 尝试 TCP 连接目标端口。"""
    import socket

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


class GitChannel(OnlineChannel):
    """Git 仓库中继在线通道。"""

    def __init__(
        self,
        remote_url: str,
        local_workdir: Optional[str] = None,
        branch: str = "main",
        probe: Optional[Probe] = None,
    ):
        self.remote_url = remote_url
        self.workdir = local_workdir or tempfile.mkdtemp(prefix="rhop-git-")
        self.branch = branch
        self._probe = probe or (lambda: _default_git_probe(remote_url))
        self.name = "git:{0}".format(remote_url)
        self._prepared = False

    def available(self) -> bool:
        return self._probe()

    def _prepare(self) -> None:
        if self._prepared:
            return
        if not os.path.isdir(os.path.join(self.workdir, ".git")):
            subprocess.run(
                ["git", "clone", "--depth", "1", "-b", self.branch, self.remote_url, self.workdir],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
                check=False,
            )
        self._prepared = True

    def send(self, filename: str, content: str) -> None:
        self._prepare()
        path = os.path.join(self.workdir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        subprocess.run(["git", "-C", self.workdir, "add", filename], check=False)
        subprocess.run(
            ["git", "-C", self.workdir, "commit", "-m", "rhop send {0}".format(filename)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        subprocess.run(
            ["git", "-C", self.workdir, "push", "origin", self.branch],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )

    def receive(self, filename: str) -> str:
        self._prepare()
        subprocess.run(
            ["git", "-C", self.workdir, "pull", "--rebase", "origin", self.branch],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        path = os.path.join(self.workdir, filename)
        if not os.path.isfile(path):
            raise FileNotFoundError("rhop: 远端无文件 {0}".format(filename))
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()


class _ParamikoSftpBackend(object):
    """paramiko SFTP 后端：真实读写远端目录。

    仅在 paramiko 可导入且配置完整时构造；SSH 客户端懒建立、可复用，
    每次文件操作独立打开/关闭 SFTP 通道，异常安全。
    """

    def __init__(
        self,
        host,
        port=22,
        username="",
        password=None,
        key_path=None,
        remote_dir="",
        timeout=10.0,
    ):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.key_path = key_path
        self.remote_dir = (remote_dir or "").replace("\\", "/")
        self.timeout = float(timeout)
        self._client = None

    # ---- 连接管理 ----
    def _open_client(self):
        """建立 SSH 客户端（调用方负责 close）。"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            key_filename=self.key_path,
            timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        return client

    def _sftp(self):
        if self._client is None:
            self._client = self._open_client()
        return self._client.open_sftp()

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _remote(self, filename):
        base = self.remote_dir.rstrip("/")
        name = filename.replace("\\", "/").lstrip("/")
        return base + "/" + name if base else name

    def available(self):
        try:
            sftp = self._sftp()
            sftp.close()
            return True
        except Exception:
            return False
        finally:
            self.close()

    def put(self, filename, content):
        sftp = self._sftp()
        try:
            with sftp.open(self._remote(filename), "w") as fh:
                fh.write(content.encode("utf-8"))
        finally:
            sftp.close()

    def get(self, filename):
        sftp = self._sftp()
        try:
            with sftp.open(self._remote(filename), "r") as fh:
                data = fh.read()
            return data.decode("utf-8")
        finally:
            sftp.close()

    def read_text(self, filename, encoding="utf-8"):
        return self.get(filename)

    def write_text(self, filename, text, encoding="utf-8"):
        self.put(filename, text)

    def exists(self, filename):
        sftp = self._sftp()
        try:
            sftp.stat(self._remote(filename))
            return True
        except IOError:
            return False
        finally:
            sftp.close()

    def listdir(self, sub=""):
        sftp = self._sftp()
        try:
            path = self._remote(sub) if sub else (self.remote_dir or ".")
            return [e.filename for e in sftp.listdir_attr(path)]
        finally:
            sftp.close()

    def mkdirs(self, sub=""):
        sftp = self._sftp()
        try:
            target = self._remote(sub) if sub else self.remote_dir
            cur = ""
            for part in target.split("/"):
                if not part:
                    continue
                cur = cur + "/" + part if cur else part
                try:
                    sftp.stat(cur)
                except IOError:
                    sftp.mkdir(cur)
        finally:
            sftp.close()


class SftpChannel(OnlineChannel):
    """SFTP 镜像在线通道：paramiko 优先，注入式 reader/writer 回退。

    - paramiko 可导入：内建 paramiko 后端，send/receive 真实读写（put/get）；
      连接失败且存在注入 writer/reader 时回退注入式
    - paramiko 缺失：完全回退注入式 reader/writer（兼容旧 MVP 形态）；
      **此时若没有注入，`available()` 直接 False**（没有后端就没有搬数据的能力），
      想知道端口通不通请用 `port_reachable()`
    - 可用性探测：`available()` = 有搬数据的能力 **且** 对端可达。
      其中「对端可达」的探测顺序：probe 注入优先 →
      probe_mode="sftp"（paramiko 可用时走真实 SFTP 连接）→ TCP 端口探测
    - sftp_cfg 统一入口：兼容 vq/sparksql-exe configs.py FTP_connect 形态
      {host, port, user, password, key_path, dir}，显式参数优先
    """

    def __init__(
        self,
        host,
        remote_dir,
        username="",
        port=22,
        password=None,
        key_path=None,
        probe=None,
        reader=None,
        writer=None,
        probe_mode="tcp",
        sftp_cfg=None,
    ):
        if sftp_cfg:
            host = sftp_cfg.get("host") or host
            port = int(sftp_cfg.get("port", port))
            username = sftp_cfg.get("user") or sftp_cfg.get("username") or username
            password = sftp_cfg.get("password") or password
            key_path = sftp_cfg.get("key_path") or key_path
            remote_dir = sftp_cfg.get("dir") or sftp_cfg.get("remote_dir") or remote_dir
        self.host = host
        self.remote_dir = remote_dir
        self.username = username
        self.port = port
        self._password = password
        self._key_path = key_path
        self._probe = probe
        self._probe_mode = probe_mode
        self._reader = reader
        self._writer = writer
        self._backend = None
        if paramiko is not None:
            self._backend = _ParamikoSftpBackend(
                host=host,
                port=port,
                username=username,
                password=password,
                key_path=key_path,
                remote_dir=remote_dir,
            )
        self.name = "sftp:{0}@{1}:{2}".format(username or "*", host, remote_dir)

    def _can_transfer(self):
        """是否**真的有搬数据的能力**：paramiko 后端存在，或注入了 writer/reader。

        「能力」与「对端可达」是两件事，见 `available()` 与 `port_reachable()` 的分工。
        """
        return (self._backend is not None
                or self._writer is not None
                or self._reader is not None)

    def port_reachable(self):
        """只回答「对端端口通不通」（诊断用），**不代表本通道能读写**。

        与 `available()` 拆开的原因：paramiko 缺失时 TCP 端口照样可能通，
        但此时没有后端、也没有注入 reader/writer —— `send()`/`receive()` 会抛
        `NotImplementedError`。把「端口通」当成「可用」就是拿合法假值冒充真实值。
        探测顺序保持历史语义：注入 probe > probe_mode（sftp 走真实连接）> TCP。
        """
        if self._probe is not None:
            return bool(self._probe())
        if self._probe_mode == "sftp" and self._backend is not None:
            return self._backend.available()
        return _default_sftp_probe(self.host, self.port)

    def available(self):
        """能否真正读写 = **既有搬数据的能力** 且 **对端可达**。

        历史缺陷（2026-10-28 修正）：此前只做 TCP 端口探测。paramiko 缺失且未注入
        reader/writer 时，端口通 → `available()` 返回 True，但 `send()`/`receive()`
        立刻抛 `NotImplementedError` —— `select_transport` 会把这条通道选中，随后
        同步全线失败，症状是「选上了却什么都传不过去」。

        现在「无后端且无注入」直接 False（不触发网络探测）。想知道端口通不通仍可调
        `port_reachable()`，那两个信号从此不会互相冒充。
        """
        if not self._can_transfer():
            return False
        return bool(self.port_reachable())

    def send(self, filename, content):
        if self._backend is not None:
            try:
                self._backend.put(filename, content)
                return
            except Exception:
                if self._writer is None:
                    raise
        if self._writer is None:
            raise NotImplementedError(
                "rhop: SftpChannel 无 paramiko 且未注入 writer，无法实际写入"
            )
        self._writer(self, filename, content)

    def receive(self, filename):
        if self._backend is not None:
            try:
                return self._backend.get(filename)
            except Exception:
                if self._reader is None:
                    raise
        if self._reader is None:
            raise NotImplementedError(
                "rhop: SftpChannel 无 paramiko 且未注入 reader，无法实际读取"
            )
        return self._reader(self, filename)

    # ---- 兼容 SFTPClient 语义的公开方法（paramiko 后端） ----

    def put(self, filename, content):
        return self.send(filename, content)

    def get(self, filename):
        return self.receive(filename)

    def read_text(self, filename, encoding="utf-8"):
        return self.receive(filename)

    def write_text(self, filename, text, encoding="utf-8"):
        return self.send(filename, text)

    def exists(self, filename):
        if self._backend is None:
            raise NotImplementedError("rhop: SftpChannel 无 paramiko 后端，无法检查远端")
        return self._backend.exists(filename)

    def listdir(self, sub=""):
        if self._backend is None:
            raise NotImplementedError("rhop: SftpChannel 无 paramiko 后端，无法列目录")
        return self._backend.listdir(sub)

    def mkdirs(self, sub=""):
        if self._backend is None:
            raise NotImplementedError("rhop: SftpChannel 无 paramiko 后端，无法建目录")
        return self._backend.mkdirs(sub)

    def close(self):
        if self._backend is not None:
            self._backend.close()
