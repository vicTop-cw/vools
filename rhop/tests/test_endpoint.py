"""MVP-2 打磨: shared path 多端视图抽象（A/B/C 地址形态异构）。"""

import http.server
import os
import sys
import threading

import pytest

from vools.rhop.transport import (
    FileUrlEndpoint,
    HttpEndpoint,
    LocalEndpoint,
    LocalSharedPath,
    SharedPathView,
    make_shared_path,
    parse_endpoint,
)


class _FileStoreHandler(http.server.BaseHTTPRequestHandler):
    """极简文件服务：GET 读 / PUT 写 / DELETE 删。用于模拟"URL 形态不代表联网"的本地文件服务。"""

    def log_message(self, fmt, *args):
        pass

    def _resolve(self):
        return os.path.join(self.server.root, self.path.lstrip("/"))

    def do_GET(self):
        path = self._resolve()
        if self.path in ("/", "") or os.path.isdir(path):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        path = self._resolve()
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, "wb") as fh:
            fh.write(data)
        self.send_response(201)
        self.end_headers()

    def do_DELETE(self):
        path = self._resolve()
        try:
            os.remove(path)
            self.send_response(204)
        except OSError:
            self.send_response(404)
        self.end_headers()


@pytest.fixture()
def http_server(tmp_path):
    root = tmp_path / "http-root"
    root.mkdir()
    handler = type("Handler", (_FileStoreHandler,), {})

    # py3.6 兼容：http.server.ThreadingHTTPServer 是 3.7+ 才引入，
    # 低版本用 ThreadingMixIn + HTTPServer 组合等价实现。
    import socketserver
    class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    server = _ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.root = str(root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"server": server, "root": str(root), "url": "http://127.0.0.1:{0}".format(server.server_port)}
    server.shutdown()


class TestParseEndpoint:
    def test_local_path(self):
        ep = parse_endpoint(r"D:\share")
        assert isinstance(ep, LocalEndpoint)
        assert ep.kind == "local"

    def test_unc_path(self):
        ep = parse_endpoint(r"\\NAS\share")
        assert isinstance(ep, LocalEndpoint)

    def test_drive_letter(self):
        ep = parse_endpoint("Z:\\share")
        assert isinstance(ep, LocalEndpoint)

    def test_file_url(self):
        ep = parse_endpoint("file:///D:/share")
        assert isinstance(ep, FileUrlEndpoint)
        assert ep.path == os.path.abspath("D:/share")

    def test_http_url(self):
        ep = parse_endpoint("http://nas:8080/share")
        assert isinstance(ep, HttpEndpoint)
        assert ep.kind == "http-url"

    @pytest.mark.skipif(sys.platform != "win32", reason="UNC 路径为 Windows 专属语义（Linux 上 os.path 不识别反斜杠 UNC）")
    def test_file_url_unc_host(self):
        ep = parse_endpoint("file://nas/share")
        assert ep.path.startswith("\\\\nas\\") or ep.path == "\\\\nas\\share"
        assert ep.display == "file://nas/share"

    def test_unknown_spec_raises(self):
        with pytest.raises(TypeError):
            parse_endpoint(None)


class TestMultiViewSharedPath:
    def test_a_local_b_fileurl_same_medium(self, tmp_path):
        """判据 8: A 以本地路径写，B 以 file:// URL 读（同一介质）。"""
        root = str(tmp_path / "medium")
        os.makedirs(root, exist_ok=True)
        shared = make_shared_path(root, "file://" + root.replace("\\", "/"))
        assert isinstance(shared, SharedPathView)
        assert shared.write_view.kind == "local"
        assert shared.read_view.kind == "file-url"

        loc = shared.write_text("pkg.rhop", "hello-from-A")
        assert os.path.isfile(loc)
        assert shared.read_text("pkg.rhop") == "hello-from-A"
        assert shared.exists("pkg.rhop")
        assert shared.remove("pkg.rhop")
        assert not shared.exists("pkg.rhop")

    def test_a_local_b_local_same_spec(self, tmp_path):
        """单 spec 兼容: make_shared_path(root) 写读同视图。"""
        root = str(tmp_path / "medium")
        shared = make_shared_path(root)
        assert isinstance(shared, SharedPathView)
        assert shared.write_view is shared.read_view
        shared.write_text("a.txt", "x")
        assert shared.read_text("a.txt") == "x"

    def test_local_shared_path_still_works(self, tmp_path):
        """旧 API LocalSharedPath 兼容。"""
        shared = LocalSharedPath(str(tmp_path / "s"))
        assert shared.available()
        shared.write_text("a.rhop", "hello")
        assert shared.read_text("a.rhop") == "hello"
        assert shared.remove("a.rhop") is True

    def test_file_url_unc_view(self):
        """file:// 带主机名解析为 UNC 形态（挂载盘/网络盘语义）。"""
        ep = FileUrlEndpoint("file://NAS/share")
        assert ep.kind == "file-url"
        assert "NAS" in ep.display


class TestHttpEndpoint:
    def test_url_shape_but_offline_medium(self, http_server):
        """判据 9: URL 形态不代表联网——本地/局域网文件服务仍属 shared path 兜底层。"""
        ep = HttpEndpoint(http_server["url"], timeout=2.0)
        assert ep.available()

        loc = ep.write_text("pkg.rhop", "content-via-http")
        assert loc.startswith(http_server["url"])
        assert ep.read_text("pkg.rhop") == "content-via-http"
        assert ep.exists("pkg.rhop")
        assert ep.remove("pkg.rhop")
        assert not ep.exists("pkg.rhop")

    def test_http_unreachable(self):
        ep = HttpEndpoint("http://127.0.0.1:1", timeout=0.5)
        assert not ep.available()
        with pytest.raises(IOError):
            ep.read_text("x.txt")

    def test_make_shared_path_http_read_view(self, http_server):
        """A 写本地、B 经 HTTP 文件服务读：写端 local、读端 http-url。"""
        root = http_server["root"]
        shared = make_shared_path(root, http_server["url"])
        assert shared.write_view.kind == "local"
        assert shared.read_view.kind == "http-url"
        shared.write_text("pkg.rhop", "payload")
        assert shared.read_text("pkg.rhop") == "payload"
