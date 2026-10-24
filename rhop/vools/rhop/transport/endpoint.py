"""vools.rhop.transport.endpoint - 端视图抽象：同一介质的各方地址形态

同一物理介质在不同方眼中地址形态不同：
  - A 侧: 本地目录  <share_dir>
  - B 侧: file:///<share_dir>、挂载盘符 <mount_point>:\\share、UNC \\\\NAS\\share
  - C 侧: http://nas:8080/share （本地/局域网文件服务）

要点: **URL 形态 ≠ 联网**。file:// 是本地介质；http(s):// 也可能是本地/局域网
文件服务。它们都属于 shared path 兜底层，不参与"在线优先"判定（在线优先只针对
OnlineChannel：Git / SFTP / 自建中转）。
"""

import abc
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

# 探测函数类型
Probe = Callable[[], bool]


class EndpointView(abc.ABC):
    """介质的一个端视图：描述某一方如何访问 shared path。

    kind:      视图形态（local / file-url / http-url）
    display:   人类可读的地址描述
    """

    kind = "abstract"
    display = ""

    @abc.abstractmethod
    def available(self) -> bool:
        """该视图当前是否可达（可写或可读）。"""

    @abc.abstractmethod
    def exists(self, filename: str) -> bool:
        """判断文件名是否存在。"""

    @abc.abstractmethod
    def read_text(self, filename: str) -> str:
        """读取文本；不存在抛 FileNotFoundError。"""

    @abc.abstractmethod
    def write_text(self, filename: str, content: str) -> str:
        """写入文本，返回定位标识（路径或 URL）。"""

    @abc.abstractmethod
    def remove(self, filename: str) -> bool:
        """删除文件；不存在返回 False。"""


class LocalEndpoint(EndpointView):
    """本地路径视图：普通目录 / UNC / 网络盘符（挂载盘对进程即普通路径）。"""

    kind = "local"

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.display = self.path

    def available(self) -> bool:
        try:
            if os.path.isdir(self.path):
                return True
            os.makedirs(self.path, exist_ok=True)
            return True
        except OSError:
            return False

    def _abs(self, filename: str) -> str:
        return os.path.join(self.path, filename)

    def exists(self, filename: str) -> bool:
        return os.path.isfile(self._abs(filename))

    def read_text(self, filename: str) -> str:
        with open(self._abs(filename), "r", encoding="utf-8") as fh:
            return fh.read()

    def write_text(self, filename: str, content: str) -> str:
        self.available()
        dest = self._abs(filename)
        tmp = dest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, dest)
        return dest

    def remove(self, filename: str) -> bool:
        try:
            os.remove(self._abs(filename))
            return True
        except OSError:
            return False

    def __repr__(self):
        return "<LocalEndpoint {0}>".format(self.display)


class FileUrlEndpoint(LocalEndpoint):
    """file:// URL 视图：解析为本地路径后按本地介质处理（不联网）。"""

    kind = "file-url"

    def __init__(self, url: str):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "file":
            raise ValueError("FileUrlEndpoint 仅接受 file:// URL: {0}".format(url))
        netloc = parsed.netloc
        path = parsed.path
        # Windows 盘符两种写法（示例路径占位 <share_dir>）:
        #   file:///<share_dir> -> netloc="",  path="/<share_dir>"
        #   file://<mount_point>:/share -> netloc="<mount_point>:", path="/share"
        if len(netloc) == 2 and netloc[1] == ":":
            path = netloc + path
        elif path.startswith("/") and len(path) >= 3 and path[2] == ":":
            path = path[1:]
        if netloc and netloc not in ("", "localhost") and not (len(netloc) == 2 and netloc[1] == ":"):
            # file://server/share -> \\server\share（网络共享/挂载语义）
            path = "\\\\{0}{1}".format(netloc, path.replace("/", "\\"))
        LocalEndpoint.__init__(self, path)
        self.url = url
        self.display = url


class HttpEndpoint(EndpointView):
    """HTTP(S) URL 视图：本地/局域网文件服务（WebDAV 风格 PUT/GET/DELETE）。

    注意: URL 形态 ≠ 联网；它仍是 shared path 兜底层，不参与在线优先判定。
    """

    kind = "http-url"

    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 3.0, probe: Optional[Probe] = None):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout
        self._probe = probe
        self.display = self.base_url

    def _headers(self):
        headers = {"Content-Type": "application/octet-stream"}
        if self.token:
            headers["X-RHOP-Token"] = self.token
        return headers

    def _probe_default(self):
        try:
            req = urllib.request.Request(self.base_url, headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status in (200, 404)  # 服务可达即视为可用
        except Exception:
            return False

    def available(self) -> bool:
        if self._probe is not None:
            return self._probe()
        return self._probe_default()

    def _url(self, filename: str) -> str:
        return self.base_url + urllib.parse.quote(filename, safe="")

    def exists(self, filename: str) -> bool:
        try:
            req = urllib.request.Request(self._url(filename), headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as exc:
            return exc.code != 404  # 非 404 视为"存在但出错"
        except Exception:
            return False

    def read_text(self, filename: str) -> str:
        req = urllib.request.Request(self._url(filename), headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError("http endpoint: 无文件 {0}".format(filename))
            raise IOError("http GET failed: {0}".format(exc.code))
        except urllib.error.URLError as exc:
            raise IOError("http unreachable: {0}".format(exc.reason))

    def write_text(self, filename: str, content: str) -> str:
        data = content.encode("utf-8")
        req = urllib.request.Request(
            self._url(filename),
            data=data,
            headers=self._headers(),
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status not in (200, 201):
                    raise IOError("http PUT status={0}".format(resp.status))
        except urllib.error.HTTPError as exc:
            raise IOError("http PUT failed: {0}".format(exc.code))
        except urllib.error.URLError as exc:
            raise IOError("http unreachable: {0}".format(exc.reason))
        return self._url(filename)

    def remove(self, filename: str) -> bool:
        req = urllib.request.Request(self._url(filename), headers=self._headers(), method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status in (200, 204)
        except urllib.error.HTTPError as exc:
            return exc.code == 404
        except Exception:
            return False


def parse_endpoint(spec: str, **kwargs) -> EndpointView:
    """把地址形态解析为端视图。

    支持:
      - 本地路径 / UNC / 网络盘符:  <share_dir>  \\\\NAS\\share  <mount_point>:\\share
      - file:// URL:                file:///<share_dir>
      - http(s):// URL:             http://nas:8080/share
    """
    if not isinstance(spec, str):
        raise TypeError("endpoint spec 必须为字符串")
    stripped = spec.strip()
    if stripped.lower().startswith("file://"):
        return FileUrlEndpoint(stripped)
    if stripped.lower().startswith(("http://", "https://")):
        return HttpEndpoint(stripped, **kwargs)
    return LocalEndpoint(stripped)
