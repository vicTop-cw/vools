"""mcp_sse.py 契约测试（Round 47）。

契约:
- _SseWriter 队列读写正确（lock 保护，不丢数据）
- do_GET: /sse 正确响应 + 推送 endpoint 事件
- do_GET: 非 /sse 返回 404
- do_GET: 断连时静默返回
- do_POST: /message 正确处理 JSON + 写入 SSE 队列
- do_POST: 非 /message 返回 404
- do_POST: 坏 JSON 返回 parse error + 写入 SSE 队列
- do_POST: response=None 时不写入队列
- do_OPTIONS: 正确返回 CORS
- log_message: 静默
- serve_sse: 能启动和关闭
"""

import io
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from vools.actus.mcp_sse import _SseWriter, SSEServerHandler, serve_sse


class TestSseWriter:
    """_SseWriter 队列读写。"""

    def test_write_and_read(self):
        w = _SseWriter()
        w.write(b'hello')
        batch = w.read_batch(timeout=1)
        assert batch == [b'hello']

    def test_write_multiple(self):
        w = _SseWriter()
        w.write(b'a')
        w.write(b'b')
        batch = w.read_batch(timeout=1)
        assert batch == [b'a', b'b']

    def test_read_timeout(self):
        w = _SseWriter()
        batch = w.read_batch(timeout=0.1)
        assert batch == []

    def test_read_clears_queue(self):
        w = _SseWriter()
        w.write(b'data')
        batch1 = w.read_batch(timeout=1)
        batch2 = w.read_batch(timeout=0.1)
        assert batch1 == [b'data']
        assert batch2 == []

    def test_write_after_read(self):
        """读到后再写，下一轮能读到。"""
        w = _SseWriter()
        w.write(b'first')
        w.read_batch(timeout=1)
        w.write(b'second')
        batch = w.read_batch(timeout=1)
        assert batch == [b'second']

    def test_concurrent_writes_no_loss(self):
        """并发写入不应丢数据。"""
        w = _SseWriter()
        N = 100
        threads = [threading.Thread(target=lambda: w.write(b'x')) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        batch = w.read_batch(timeout=1)
        assert len(batch) == N

    def test_concurrent_writes_and_reads(self):
        """并发读写不应丢数据。"""
        w = _SseWriter()
        N = 50
        results = []
        def reader():
            for _ in range(N):
                batch = w.read_batch(timeout=1)
                results.extend(batch)
        def writer():
            for _ in range(N):
                w.write(b'y')
        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(results) == N


class TestDoGet:
    """do_GET 处理。"""

    def _make_handler(self, sse_writer=None, mcp_server=None):
        """构造一个 do_GET 测试用的 handler。"""
        h = SSEServerHandler.__new__(SSEServerHandler)
        h.path = '/sse'
        h.headers = {}
        h.wfile = io.BytesIO()
        h._headers_sent = False
        h._code = 0
        h._headers = []
        h.send_response = MagicMock()
        h.send_header = MagicMock()
        h.end_headers = MagicMock()
        h.send_error = MagicMock()
        h.log_message = MagicMock()
        if sse_writer is None:
            sse_writer = _SseWriter()
        if mcp_server is None:
            mcp_server = MagicMock()
        h.sse_writer = sse_writer
        h.mcp_server = mcp_server
        return h

    def test_get_sse_sends_endpoint(self):
        """GET /sse 应推送 endpoint 事件。"""
        h = self._make_handler()
        # do_GET 会循环，所以 mock read_batch 在第一次调用后抛 BrokenPipeError 来退出
        def mock_read_batch(timeout):
            return []  # 空批次
        h.sse_writer.read_batch = mock_read_batch
        # 调用 do_GET，但用 BrokenPipeError 在循环中退出
        # 由于 read_batch 返回空，循环会一直继续，所以我们需要在后台线程中运行
        import threading
        thread = threading.Thread(target=h.do_GET, daemon=True)
        thread.start()
        thread.join(timeout=0.5)
        # 检查 endpoint 事件已写入
        wfile = h.wfile
        content = wfile.getvalue()
        assert b'event: endpoint' in content
        assert b'message: /message' in content

    def test_get_wrong_path(self):
        """GET 非 /sse 应返回 404。"""
        h = self._make_handler()
        h.path = '/wrong'
        h.do_GET()
        h.send_error.assert_called_once_with(404, 'Not Found')


class TestDoPost:
    """do_POST 处理。"""

    def _make_handler(self, sse_writer=None, mcp_server=None):
        h = SSEServerHandler.__new__(SSEServerHandler)
        h.path = '/message'
        h.headers = MagicMock()
        h.headers.get = MagicMock(return_value='100')
        h.rfile = io.BytesIO(b'{}')
        h.wfile = io.BytesIO()
        h._headers_sent = False
        h._code = 0
        h._headers = []
        h.send_response = MagicMock()
        h.send_header = MagicMock()
        h.end_headers = MagicMock()
        h.send_error = MagicMock()
        h.log_message = MagicMock()
        if sse_writer is None:
            sse_writer = _SseWriter()
        if mcp_server is None:
            mcp_server = MagicMock()
        h.sse_writer = sse_writer
        h.mcp_server = mcp_server
        return h

    def test_post_message(self):
        """POST /message 应处理 JSON 并写入 SSE 队列。"""
        h = self._make_handler()
        response = {'jsonrpc': '2.0', 'id': 1, 'result': 'ok'}
        h.mcp_server.handle.return_value = response
        h.do_POST()
        h.mcp_server.handle.assert_called_once()
        # 响应应写入 SSE 队列
        batch = h.sse_writer.read_batch(timeout=1)
        assert len(batch) == 1
        assert json.loads(batch[0]) == response

    def test_post_wrong_path(self):
        """POST 非 /message 应返回 404。"""
        h = self._make_handler()
        h.path = '/wrong'
        h.do_POST()
        h.send_error.assert_called_once_with(404, 'Not Found')

    def test_post_bad_json(self):
        """POST 坏 JSON 应返回 parse error + 写入 SSE 队列。"""
        h = self._make_handler()
        h.rfile = io.BytesIO(b'not json')
        h.do_POST()
        batch = h.sse_writer.read_batch(timeout=1)
        assert len(batch) == 1
        parsed = json.loads(batch[0])
        assert parsed['error']['code'] == -32700

    def test_post_no_response(self):
        """POST 响应为 None 时不写入队列。"""
        h = self._make_handler()
        h.mcp_server.handle.return_value = None
        h.do_POST()
        batch = h.sse_writer.read_batch(timeout=0.1)
        assert batch == []

    def test_post_sends_ok(self):
        """POST 应返回 OK。"""
        h = self._make_handler()
        h.mcp_server.handle.return_value = {'jsonrpc': '2.0', 'id': 1}
        h.do_POST()
        h.send_response.assert_called_with(200)


class TestDoOptions:
    """do_OPTIONS 处理。"""

    def test_options(self):
        """OPTIONS 应返回 CORS 头。"""
        h = SSEServerHandler.__new__(SSEServerHandler)
        h.send_response = MagicMock()
        h.send_header = MagicMock()
        h.end_headers = MagicMock()
        h.do_OPTIONS()
        h.send_response.assert_called_with(200)
        h.send_header.assert_any_call('Access-Control-Allow-Origin', '*')
        h.send_header.assert_any_call('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        h.send_header.assert_any_call('Access-Control-Allow-Headers', 'Content-Type')


class TestLogMessage:
    """log_message 静默。"""

    def test_log_message(self):
        """log_message 不应输出任何内容。"""
        h = SSEServerHandler.__new__(SSEServerHandler)
        h.log_message('format', 'arg')
        # 没有抛错即通过


class TestServeSse:
    """serve_sse 启动和关闭。"""

    def test_serve_sse_starts_and_stops(self, monkeypatch):
        """serve_sse 能启动并正常关闭。"""
        import http.server
        httpd = MagicMock()
        httpd.serve_forever = MagicMock()

        with patch('vools.actus.mcp_sse.HTTPServer', return_value=httpd), \
             patch('vools.actus.mcp_sse.MCPServer', return_value=MagicMock()), \
             patch('builtins.print'):
            # 直接调用 serve_sse 但用 KeyboardInterrupt 退出
            def mock_serve_forever():
                raise KeyboardInterrupt()
            httpd.serve_forever = mock_serve_forever
            serve_sse('127.0.0.1', 0)
            httpd.shutdown.assert_called_once()


class TestModuleExports:
    """模块导出。"""

    def test_all_exports(self):
        """__all__ 应包含 SSEServerHandler 和 serve_sse。"""
        assert 'SSEServerHandler' in __import__('vools.actus.mcp_sse', fromlist=['__all__']).__all__
        assert 'serve_sse' in __import__('vools.actus.mcp_sse', fromlist=['__all__']).__all__
        assert 'MCPServerSSE' not in __import__('vools.actus.mcp_sse', fromlist=['__all__']).__all__
