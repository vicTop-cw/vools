"""vools.rhop.transport.relay - MVP-3 双方自建临时服务器中转

异步机器: 中转方(RelayHost)临时启动本地 HTTP 服务，投递方(RelayClient)择机
PUT 加密 JSON 包后即走；中转方 TTL 到期自动关闭。地址与 token 由配置侧告知
对端（不做 shared path 发现）。

通道选择链: 自建中转(双方可达) -> Git/SFTP 在线通道 -> shared path 回退。
RelayChannel 实现 OnlineChannel，可直接接入 select_transport。
"""

import http.server
import socketserver
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from .base import OnlineChannel

# 探测函数类型
Probe = Callable[[], bool]

# Python 3.6 无 http.server.ThreadingHTTPServer（3.7+ 引入），手动组合兜底
if hasattr(http.server, "ThreadingHTTPServer"):
    _ThreadingHTTPServer = http.server.ThreadingHTTPServer
else:  # pragma: no cover - py3.6 兼容分支
    class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True


class _RelayHTTPServer(_ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, addr, handler, relay):
        _ThreadingHTTPServer.__init__(self, addr, handler)
        self.relay = relay


class _RelayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静默日志
        pass

    # ---- 内部辅助 ----
    def _relay(self):
        return self.server.relay

    def _check_token(self):
        relay = self._relay()
        if relay.token is None:
            return True
        return self.headers.get("X-RHOP-Token") == relay.token

    def _parse_pkg(self):
        """从 /pkg/<filename> 解析文件名，非法返回 None。"""
        prefix = "/pkg/"
        if not self.path.startswith(prefix):
            return None
        name = self.path[len(prefix):]
        if not name or "/" in name or "\\" in name:
            return None
        return name

    def _send_empty(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self):
        relay = self._relay()
        if not self._check_token():
            self.send_error(403, "bad token")
            return
        filename = self._parse_pkg()
        if filename is None:
            self.send_error(400, "bad filename")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        with relay._lock:
            relay.packages[filename] = body
        self._send_empty(201)

    def do_GET(self):
        relay = self._relay()
        if self.path == "/health":
            self._send_empty(200)
            return
        if not self._check_token():
            self.send_error(403, "bad token")
            return
        filename = self._parse_pkg()
        if filename is None:
            self.send_error(400, "bad filename")
            return
        with relay._lock:
            data = relay.packages.pop(filename, None)  # 取走即删，不留明文残留
        if data is None:
            self.send_error(404, "no such pkg")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class RelayServer(object):
    """临时 HTTP 中转服务器（RelayHost 侧）。

    start() 后经配置侧把 (host, port, token) 告知对端；TTL 到期自动关闭并清空。
    """

    def __init__(self, host="127.0.0.1", port=0, token=None, ttl=300.0):
        self.host = host
        self.port = port
        self.token = token
        self.ttl = ttl
        self.packages = {}
        self._lock = threading.Lock()
        self._httpd = None
        self._thread = None
        self._timer = None
        self.started_at = None

    @property
    def url(self):
        return "http://{0}:{1}".format(self.host, self.port)

    def start(self):
        if self._httpd is not None:
            return self
        self._httpd = _RelayHTTPServer((self.host, self.port), _RelayHandler, self)
        self.port = self._httpd.server_address[1]
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        if self.ttl and self.ttl > 0:
            self._timer = threading.Timer(self.ttl, self.stop)
            self._timer.daemon = True
            self._timer.start()
        return self

    def stop(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        with self._lock:
            self.packages.clear()

    def alive(self):
        return self._httpd is not None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


class RelayChannel(OnlineChannel):
    """投递方通道：经配置告知的 (host, port, token) 访问中转。

    配置告知形态: RelayHost 启动后，把 server.url + token 作为配置项告知对端；
    对端用 RelayChannel(host, port, token) 构造通道。
    """

    def __init__(self, host, port, token=None, timeout=3.0, probe=None):
        self.base = "http://{0}:{1}".format(host, port)
        self.token = token
        self.timeout = timeout
        self._probe = probe
        self.name = "relay:{0}".format(self.base)

    def _headers(self):
        headers = {"Content-Type": "application/octet-stream"}
        if self.token:
            headers["X-RHOP-Token"] = self.token
        return headers

    def _probe_default(self):
        try:
            req = urllib.request.Request(self.base + "/health", headers=self._headers())
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def available(self):
        if self._probe is not None:
            return self._probe()
        return self._probe_default()

    def send(self, filename, content):
        data = content.encode("utf-8")
        req = urllib.request.Request(
            self.base + "/pkg/" + filename,
            data=data,
            method="PUT",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status not in (200, 201):
                    raise IOError("relay PUT status={0}".format(resp.status))
        except urllib.error.HTTPError as exc:
            raise IOError("relay PUT failed: {0}".format(exc.code))
        except urllib.error.URLError as exc:
            raise IOError("relay unreachable: {0}".format(exc.reason))

    def receive(self, filename):
        req = urllib.request.Request(self.base + "/pkg/" + filename, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError("relay: 中转无包 {0}".format(filename))
            raise IOError("relay GET failed: {0}".format(exc.code))
        except urllib.error.URLError as exc:
            raise IOError("relay unreachable: {0}".format(exc.reason))
