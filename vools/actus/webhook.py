"""webhook.py —— 零依赖 HTTP Webhook 接收器（docs/22 §A8-1）。

Python 内置 http.server 实现，支持 HMAC-SHA256 签名验证、
事件路由、IP 白名单、速率限制、异步分发。
"""

import hashlib
import hmac
import json
import os
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs


class WebhookConfig:
    """Webhook 接收器配置。"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765,
                 secret: str = "", require_signature: bool = True,
                 ip_whitelist: List[str] = None,
                 rate_limit_per_minute: int = 60,
                 timestamp_window: int = 300):
        self.host = host
        self.port = port
        self.secret = secret
        self.require_signature = require_signature
        self.ip_whitelist = ip_whitelist or []
        self.rate_limit_per_minute = rate_limit_per_minute
        self.timestamp_window = timestamp_window  # 秒


class WebhookStats:
    """Webhook 运行统计。"""

    def __init__(self):
        self.total_requests: int = 0
        self.accepted: int = 0
        self.rejected_signature: int = 0
        self.rejected_ip: int = 0
        self.rejected_rate: int = 0
        self.rejected_format: int = 0
        self.started_at: float = 0
        self.last_request_at: float = 0
        self._lock = threading.Lock()

    def record_request(self, accepted: bool, reject_reason: str = ""):
        with self._lock:
            self.total_requests += 1
            self.last_request_at = time.time()
            if accepted:
                self.accepted += 1
            elif reject_reason == "signature":
                self.rejected_signature += 1
            elif reject_reason == "ip":
                self.rejected_ip += 1
            elif reject_reason == "rate":
                self.rejected_rate += 1
            elif reject_reason == "format":
                self.rejected_format += 1

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "accepted": self.accepted,
            "rejected_signature": self.rejected_signature,
            "rejected_ip": self.rejected_ip,
            "rejected_rate": self.rejected_rate,
            "rejected_format": self.rejected_format,
            "started_at": self.started_at,
            "last_request_at": self.last_request_at,
            "uptime_seconds": time.time() - self.started_at if self.started_at else 0
        }


class RateLimiter:
    """简单滑动窗口速率限制器。"""

    def __init__(self, max_per_minute: int = 60):
        self._max = max_per_minute
        self._requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, client_ip: str) -> bool:
        """检查是否允许请求。"""
        now = time.time()
        with self._lock:
            if client_ip not in self._requests:
                self._requests[client_ip] = []

            # 清理 60 秒前的记录
            self._requests[client_ip] = [
                t for t in self._requests[client_ip] if now - t < 60
            ]

            if len(self._requests[client_ip]) >= self._max:
                return False

            self._requests[client_ip].append(now)
            return True


class IPWhitelist:
    """IP 白名单检查（支持 CIDR）。"""

    def __init__(self, cidrs: List[str]):
        self._cidrs = cidrs
        self._patterns = []
        for cidr in cidrs:
            self._patterns.append(self._cidr_to_pattern(cidr))

    def is_allowed(self, ip: str) -> bool:
        """检查 IP 是否在白名单中。"""
        if not self._patterns:
            return True  # 无白名单配置则允许所有

        for pattern in self._patterns:
            if pattern(ip):
                return True
        return False

    @staticmethod
    def _cidr_to_pattern(cidr: str) -> Callable[[str], bool]:
        """将 CIDR 转为匹配函数。"""
        if "/" in cidr:
            # CIDR 格式: 192.168.1.0/24
            import ipaddress
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                return lambda ip: ipaddress.ip_address(ip) in network
            except ValueError:
                return lambda ip: False
        else:
            # 精确匹配
            return lambda ip: ip == cidr


class WebhookReceiver:
    """零依赖 HTTP Webhook 接收器。

    使用方式:
        receiver = WebhookReceiver(config)
        receiver.register_route("github.push", "my.action.deploy")
        receiver.start()  # 阻塞
        # 或
        receiver.start_background()  # 非阻塞
     """

    def __init__(self, config: WebhookConfig = None):
        self._config = config or WebhookConfig()
        self._routes: Dict[str, str] = {}  # event_type -> action_id
        self._fallback_action: Optional[str] = None
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._stats = WebhookStats()
        self._rate_limiter = RateLimiter(self._config.rate_limit_per_minute)
        self._ip_whitelist = IPWhitelist(self._config.ip_whitelist)
        self._request_log: List[dict] = []
        self._log_lock = threading.Lock()
        self._running = False

    @property
    def stats(self) -> WebhookStats:
        return self._stats

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 路由注册 ──

    def register_route(self, event_type: str, action_id: str):
        """注册事件路由。

        参数:
            event_type: 事件类型（如 "github.push"）。
            action_id: 触发的动作 id。
        """
        self._routes[event_type] = action_id

    def unregister_route(self, event_type: str) -> Optional[str]:
        """移除事件路由。"""
        return self._routes.pop(event_type, None)

    def set_fallback(self, action_id: str):
        """设置通配符回退动作。"""
        self._fallback_action = action_id

    def get_routes(self) -> Dict[str, str]:
        """获取所有路由。"""
        return dict(self._routes)

    def resolve_action(self, event_type: str) -> Optional[str]:
        """根据事件类型解析目标动作 id。

        优先级:
        1. 精确匹配
        2. 前缀匹配 (github.*)
        3. 通配符回退 (*)
        """
        # 精确匹配
        if event_type in self._routes:
            return self._routes[event_type]

        # 前缀匹配
        parts = event_type.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i]) + ".*"
            if prefix in self._routes:
                return self._routes[prefix]

        # 通配符
        if "*" in self._routes:
            return self._routes["*"]

        # 回退
        return self._fallback_action

    # ── 服务器控制 ──

    def start(self):
        """启动 Webhook 接收器（阻塞）。"""
        self._stats.started_at = time.time()
        self._running = True

        handler = self._make_handler()
        self._server = HTTPServer(
            (self._config.host, self._config.port), handler
        )

        print(f"🚀 Webhook 接收器启动: http://{self._config.host}:{self._config.port}")
        print(f"   已注册路由: {len(self._routes)}")
        print(f"   IP 白名单: {self._config.ip_whitelist or '无限制'}")
        print(f"   签名验证: {'启用' if self._config.require_signature else '禁用'}")

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            print("\n⏹️  停止 Webhook 接收器")
        finally:
            self._running = False

    def start_background(self) -> threading.Thread:
        """启动 Webhook 接收器（后台非阻塞）。"""
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        """停止 Webhook 接收器。"""
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        print("⏹️  Webhook 接收器已停止")

    # ── 请求处理 ──

    def _make_handler(self):
        """创建请求 handler 工厂。"""
        receiver = self

        class WebhookHandler(BaseHTTPRequestHandler):
            """Webhook HTTP 请求处理器。"""

            def log_message(self, format, *args):
                """禁用默认日志。"""
                pass

            def do_POST(self):
                """处理 POST 请求。"""
                receiver._handle_request(self)

            def do_GET(self):
                """健康检查端点。"""
                if self.path == "/health":
                    receiver._respond(self, 200, {
                        "status": "ok",
                        "uptime": time.time() - receiver._stats.started_at
                    })
                else:
                    receiver._respond(self, 404, {"error": "not_found"})

        return WebhookHandler

    def _handle_request(self, handler: BaseHTTPRequestHandler):
        """处理单个 Webhook 请求。"""
        client_ip = handler.client_address[0]

        # 1. IP 白名单检查
        if not self._ip_whitelist.is_allowed(client_ip):
            self._stats.record_request(False, "ip")
            self._respond(handler, 403, {"error": "ip_not_allowed"})
            return

        # 2. 速率限制
        if not self._rate_limiter.check(client_ip):
            self._stats.record_request(False, "rate")
            self._respond(handler, 429, {"error": "rate_limited"})
            return

        # 3. 读取请求体
        content_length = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_length) if content_length else b""

        # 4. 签名验证
        if self._config.require_signature:
            sig = handler.headers.get("X-Hub-Signature-256", "")
            if not self._verify_signature(body, sig):
                self._stats.record_request(False, "signature")
                self._respond(handler, 401, {"error": "invalid_signature"})
                return

        # 5. 解析 JSON
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._stats.record_request(False, "format")
            self._respond(handler, 400, {"error": "invalid_json"})
            return

        # 6. 提取事件类型
        event_type = (
            handler.headers.get("X-GitHub-Event")
            or handler.headers.get("X-GitLab-Event")
            or payload.get("event", "unknown")
        )

        # 7. 时间戳防重放
        ts = payload.get("timestamp") or handler.headers.get("X-Request-Timestamp")
        if ts and self._config.timestamp_window:
            try:
                ts_float = float(ts)
                if abs(time.time() - ts_float) > self._config.timestamp_window:
                    self._stats.record_request(False, "format")
                    self._respond(handler, 400, {"error": "timestamp_expired"})
                    return
            except (ValueError, TypeError):
                pass

        # 8. 路由解析
        action_id = self.resolve_action(event_type)

        # 9. 记录日志
        self._log_request(client_ip, event_type, action_id, payload)

        # 10. 分发触发
        self._stats.record_request(True)

        if action_id:
            # 异步触发动作（不阻塞 HTTP 响应）
            threading.Thread(
                target=self._dispatch_action,
                args=(action_id, event_type, payload),
                daemon=True
            ).start()
            self._respond(handler, 200, {
                "status": "ok",
                "event": event_type,
                "action": action_id,
                "dispatched": True
            })
        else:
            self._respond(handler, 202, {
                "status": "accepted",
                "event": event_type,
                "action": None,
                "dispatched": False,
                "message": "No route registered for this event"
            })

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        """验证 HMAC-SHA256 签名。"""
        if not signature:
            return not self._config.require_signature

        # 支持 "sha256=..." 格式
        if "=" in signature:
            _, sig_hex = signature.split("=", 1)
        else:
            sig_hex = signature

        expected = hmac.new(
            self._config.secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, sig_hex)

    def _dispatch_action(self, action_id: str, event_type: str, payload: dict):
        """分发触发动作执行（异步）。"""
        try:
            from .executor import execute_action
            execute_action(action_id, params={
                "event_type": event_type,
                "payload": payload,
                "triggered_by": "webhook"
            })
        except Exception as e:
            # 记录但不抛出（异步上下文）
            print(f"⚠️  Webhook 触发动作失败 [{action_id}]: {e}")

    def _log_request(self, client_ip: str, event_type: str,
                     action_id: str, payload: dict):
        """记录请求日志。"""
        with self._log_lock:
            self._request_log.append({
                "timestamp": time.time(),
                "client_ip": client_ip,
                "event_type": event_type,
                "action_id": action_id,
                "payload_size": len(json.dumps(payload))
            })
            # 保留最近 1000 条
            if len(self._request_log) > 1000:
                self._request_log = self._request_log[-1000:]

    def get_logs(self, limit: int = 50) -> List[dict]:
        """获取请求日志。"""
        with self._log_lock:
            return self._request_log[-limit:]

    def get_status(self) -> dict:
        """获取运行状态。"""
        return {
            "running": self._running,
            "config": {
                "host": self._config.host,
                "port": self._config.port,
                "require_signature": self._config.require_signature,
                "ip_whitelist": self._config.ip_whitelist
            },
            "routes": self._routes,
            "stats": self._stats.to_dict()
        }

    # ── HTTP 响应辅助 ──

    @staticmethod
    def _respond(handler: BaseHTTPRequestHandler, status: int, body: dict):
        """发送 JSON 响应。"""
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps(body).encode("utf-8"))

    @staticmethod
    def _respond_json(handler: BaseHTTPRequestHandler, status: int, body: dict):
        """发送 JSON 响应（别名）。"""
        WebhookReceiver._respond(handler, status, body)


# ── 便捷函数 ──

def create_receiver(host: str = "0.0.0.0", port: int = 8765,
                    secret: str = "", require_signature: bool = True,
                    ip_whitelist: List[str] = None) -> WebhookReceiver:
    """便捷函数：创建 Webhook 接收器。"""
    config = WebhookConfig(
        host=host, port=port, secret=secret,
        require_signature=require_signature,
        ip_whitelist=ip_whitelist or []
    )
    return WebhookReceiver(config)


def start_webhook(host: str = "0.0.0.0", port: int = 8765,
                  secret: str = "", **kwargs) -> WebhookReceiver:
    """便捷函数：创建并启动 Webhook 接收器（阻塞）。"""
    receiver = create_receiver(host=host, port=port, secret=secret, **kwargs)
    receiver.start()
    return receiver


def start_webhook_background(host: str = "0.0.0.0", port: int = 8765,
                             secret: str = "",
                             **kwargs) -> WebhookReceiver:
    """便捷函数：创建并启动 Webhook 接收器（后台）。"""
    receiver = create_receiver(host=host, port=port, secret=secret, **kwargs)
    receiver.start_background()
    return receiver


__all__ = [
    'IPWhitelist',
    'RateLimiter',
    'WebhookConfig',
    'WebhookReceiver',
    'WebhookStats',
    'create_receiver',
    'start_webhook',
    'start_webhook_background'
]
