"""MCP SSE transport（docs/10 §A.1）：零依赖 stdlib http.server 实现。

SSE 模式让浏览器 / 远程 AI 客户端通过 HTTP 长连接接入 Actus：
- GET  /sse    → 建立 SSE 流，推送 server→client 消息
- POST /message → 接收 client→server 请求，同步返回 JSON-RPC 响应

零新增依赖：基于 http.server.BaseHTTPRequestHandler + threading 异步写 SSE。
与 stdio 版共用 MCPServer.handle() 逻辑，仅 I/O 适配层不同。
"""

__all__ = ['SSEServerHandler', 'serve_sse', 'MCPServerSSE']

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO

from actus.mcp_server import MCPServer


class _SseWriter:
    """非阻塞 SSE 写入器：POST handler 把响应推入队列，SSE handler 转发给客户端。"""

    def __init__(self):
        self._queue = []
        self._event = threading.Event()

    def write(self, data: bytes):
        self._queue.append(data)
        self._event.set()

    def read_batch(self, timeout: float = 30.0):
        """阻塞等待下一批数据，超时返回空列表。"""
        if not self._event.wait(timeout=timeout):
            return []
        batch = list(self._queue)
        self._queue.clear()
        self._event.clear()
        return batch


class SSEServerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MCP SSE transport."""

    # 类属性：由 serve_sse 注入
    sse_writer: _SseWriter = None
    mcp_server: MCPServer = None

    def log_message(self, format, *args):
        """静默日志，避免污染 stderr。"""
        pass

    def do_GET(self):
        """GET /sse：建立 SSE 长连接。"""
        if self.path != '/sse':
            self.send_error(404, 'Not Found')
            return

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # 推送 endpoint 事件
        endpoint_msg = f'event: endpoint\nmessage: /message\n\n'
        try:
            self.wfile.write(endpoint_msg.encode('utf-8'))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

        # 持续轮询推送消息
        while True:
            batch = self.sse_writer.read_batch(timeout=30.0)
            for data in batch:
                try:
                    # SSE 格式：每条消息以 \n\n 分隔，data: 前缀
                    for line in data.decode('utf-8').split('\n'):
                        if line:
                            self.wfile.write(f'data: {line}\n'.encode('utf-8'))
                    self.wfile.write(b'\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            # 心跳：定期发送注释保持连接
            try:
                self.wfile.write(b': heartbeat\n\n')
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

    def do_POST(self):
        """POST /message：接收 client 请求，转发给 MCP server，响应入 SSE 队列。"""
        if self.path != '/message':
            self.send_error(404, 'Not Found')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            msg = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            response = {'jsonrpc': '2.0', 'id': None, 'error': {
                'code': -32700, 'message': f'Parse error: {e}'}}
            self.sse_writer.write(json.dumps(response).encode('utf-8'))
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            return

        # 使用 MCP server 处理请求
        response = self.mcp_server.handle(msg)

        if response is not None:
            # 推入 SSE 队列
            self.sse_writer.write(json.dumps(response).encode('utf-8'))

        # POST 返回 200 OK（响应通过 SSE 流推送）
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b'OK')

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def serve_sse(host: str = '127.0.0.1', port: int = 8765) -> None:
    """启动 MCP SSE server（docs/10 §A.1）。"""
    writer = _SseWriter()
    server = MCPServer()
    SSEServerHandler.sse_writer = writer
    SSEServerHandler.mcp_server = server

    httpd = HTTPServer((host, port), SSEServerHandler)
    print(f'Actus MCP SSE server listening on http://{host}:{port}/sse', flush=True)
    print(f'  POST messages to http://{host}:{port}/message', flush=True)
    print('  Press Ctrl+C to stop.', flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down SSE server...', flush=True)
        httpd.shutdown()


if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    serve_sse(port=port)
