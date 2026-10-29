# -*- coding: utf-8 -*-
"""webhook.py 契约测试（第 42 轮，round 32 任务）。

目标：注册/路由/签名/IP/限流/请求处理/统计/分发的真实分支。
**不真发网络、不真绑端口**：HTTP handler 用假对象，HTTPServer/Thread 用替身。
每条 docstring 写「退步了会怎样」；已确认的 bug 只报告，用例用 xfail(strict=True)
钉"正确语义"（修复后 strict xpass 会提醒删标记）。
"""
import hashlib
import hmac
import io
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import webhook as wh  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────

class _FakeHandler(object):
    """BaseHTTPRequestHandler 替身：只实现 webhook 用到的字段/方法。"""

    def __init__(self, body=b'', headers=None, client=('127.0.0.1',)):
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = headers or {}
        self.client_address = client
        self.status = None
        self.sent = []

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent.append((name, value))

    def end_headers(self):
        pass

    def response_json(self):
        return json.loads(self.wfile.getvalue().decode('utf-8'))


@pytest.fixture
def receiver():
    return wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))


def _sync_thread(monkeypatch):
    """把 threading.Thread 换成同步执行，便于断言分发。"""
    class _SyncThread(object):
        def __init__(self, target=None, args=(), daemon=None, **kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    monkeypatch.setattr(wh.threading, 'Thread', _SyncThread)


# ═══════════════════════════════════════════════════════════════════════
# 配置 / 统计
# ═══════════════════════════════════════════════════════════════════════

def test_config_defaults_and_custom():
    """退步了会怎样：默认配置漂移（host/port/签名开关/窗口/限流/上限）→ 部署面/安全面静默变化。"""
    # W1：require_signature=True + 空 secret 是矛盾配置，构造期必须失败
    with pytest.raises(ValueError, match='secret'):
        wh.WebhookConfig()
    c = wh.WebhookConfig(require_signature=False)
    assert c.host == '127.0.0.1' and c.port == 8765      # W1：默认不再对 0.0.0.0 开放
    assert c.require_signature is False and c.secret == ''
    assert c.ip_whitelist == [] and c.rate_limit_per_minute == 60
    assert c.timestamp_window == 300
    assert c.max_body_bytes == wh.MAX_BODY_BYTES > 0
    assert c.max_dispatch_workers == wh.MAX_DISPATCH_WORKERS > 0
    c2 = wh.WebhookConfig(host='127.0.0.1', port=1, secret='s', ip_whitelist=['10.0.0.1'])
    assert (c2.host, c2.port, c2.secret) == ('127.0.0.1', 1, 's')


def test_stats_record_each_reject_reason():
    """退步了会怎样：拒绝原因没分类（全都计入 accepted 或丢弃）→ 线上看不到被谁/为什么拦。"""
    st = wh.WebhookStats()
    st.record_request(True)
    for reason in ('signature', 'ip', 'rate', 'format', 'unknown'):
        st.record_request(False, reason)
    d = st.to_dict()
    assert d['total_requests'] == 6 and d['accepted'] == 1
    assert d['rejected_signature'] == 1 and d['rejected_ip'] == 1
    assert d['rejected_rate'] == 1 and d['rejected_format'] == 1
    assert d['last_request_at'] > 0


def test_rate_limiter_window(monkeypatch):
    """退步了会怎样：限流失效（刷爆接收器）或窗口不滑（60s 后永久拒绝）。"""
    now = {'t': 1000.0}
    monkeypatch.setattr(wh.time, 'time', lambda: now['t'])
    lim = wh.RateLimiter(2)
    assert lim.check('1.1.1.1') is True
    assert lim.check('1.1.1.1') is True
    assert lim.check('1.1.1.1') is False
    now['t'] += 61
    assert lim.check('1.1.1.1') is True
    assert lim.check('2.2.2.2') is True


# ═══════════════════════════════════════════════════════════════════════
# IP 白名单
# ═══════════════════════════════════════════════════════════════════════

def test_ip_whitelist_modes():
    """退步了会怎样：白名单空配置变成全拒（服务不可用）或 CIDR 匹配错（放过非白名单 IP）。"""
    assert wh.IPWhitelist([]).is_allowed('8.8.8.8') is True
    exact = wh.IPWhitelist(['127.0.0.1'])
    assert exact.is_allowed('127.0.0.1') is True
    assert exact.is_allowed('127.0.0.2') is False
    cidr = wh.IPWhitelist(['10.0.0.0/8'])
    assert cidr.is_allowed('10.1.2.3') is True
    assert cidr.is_allowed('11.0.0.1') is False
    # 非法 CIDR 必须 fail-closed（不匹配任何 IP），不能变成"全放行"
    bad = wh.IPWhitelist(['not-a-cidr/99'])
    assert bad.is_allowed('1.2.3.4') is False


def test_ip_whitelist_malformed_client_ip_is_rejected_not_crash():
    """退步了会怎样：非法 client IP 直接抛异常 → 一个坏请求打挂 handler 线程。

    W5 修复后 fail-closed：返回 False（handler 走 403），不抛。"""
    cidr = wh.IPWhitelist(['10.0.0.0/8'])
    assert cidr.is_allowed('not-an-ip') is False


# ═══════════════════════════════════════════════════════════════════════
# 路由解析
# ═══════════════════════════════════════════════════════════════════════

def test_routes_register_resolve_and_fallback(receiver):
    """退步了会怎样：路由优先级错（前缀/通配/回退覆盖精确）→ 事件触发到错的动作。"""
    assert receiver.resolve_action('x.y') is None
    receiver.register_route('github.push', 'a.push')
    receiver.register_route('github.*', 'a.github')
    receiver.register_route('*', 'a.any')
    receiver.set_fallback('a.fallback')

    assert receiver.resolve_action('github.push') == 'a.push'      # 精确优先
    assert receiver.resolve_action('github.issue') == 'a.github'   # 前缀
    assert receiver.resolve_action('gitlab.push') == 'a.any'       # 通配
    assert receiver.get_routes()['github.push'] == 'a.push'
    assert receiver.unregister_route('github.push') == 'a.push'
    assert receiver.unregister_route('nope') is None

    receiver2 = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    receiver2.set_fallback('only.fallback')
    assert receiver2.resolve_action('anything') == 'only.fallback'


# ═══════════════════════════════════════════════════════════════════════
# 签名
# ═══════════════════════════════════════════════════════════════════════

def test_signature_verification_positive_and_negative():
    """退步了会怎样：签名不校验/比较不是恒定时间/缺头默认放行 → 任意伪造请求被接受。"""
    body = b'{"event":"push"}'
    r = wh.WebhookReceiver(wh.WebhookConfig(secret='s3cr3t'))
    good = 'sha256=' + hmac.new(b's3cr3t', body, hashlib.sha256).hexdigest()
    assert r._verify_signature(body, good) is True
    assert r._verify_signature(body, 'sha256=' + '0' * 64) is False
    assert r._verify_signature(body, '') is False
    assert wh.WebhookReceiver(wh.WebhookConfig(secret='s3cr3t',
                                               require_signature=False)
                              )._verify_signature(body, '') is True


def test_signature_rejects_unknown_scheme_prefix():
    """退步了会怎样：任何 `前缀=合法hex` 都算通过 → 方案协商形同虚设。

    W2 修复后只认白名单前缀；sha1 仍可用（算法跟着前缀走）。"""
    body = b'{}'
    r = wh.WebhookReceiver(wh.WebhookConfig(secret='s'))
    good = hmac.new(b's', body, hashlib.sha256).hexdigest()
    assert r._verify_signature(body, 'md5=' + good) is False
    assert r._verify_signature(body, 'anything=' + good) is False
    sha1_sig = hmac.new(b's', body, hashlib.sha1).hexdigest()
    assert r._verify_signature(body, 'sha1=' + sha1_sig) is True


def test_empty_secret_signature_fails_closed():
    """退步了会怎样：空密钥 HMAC 可被任何人计算 → 默认/误配的"签名校验"形同虚设。
    W1 修复后：空 secret 恒返回 False，且 require_signature+空 secret 构造期即拒绝。"""
    body = b'{"x":1}'
    forged = 'sha256=' + hmac.new(b'', body, hashlib.sha256).hexdigest()
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))  # 允许无签名但校验仍须 fail-closed
    assert r._verify_signature(body, forged) is False
    with pytest.raises(ValueError, match='secret'):
        wh.WebhookConfig()


# ═══════════════════════════════════════════════════════════════════════
# 请求处理（假 handler）
# ═══════════════════════════════════════════════════════════════════════

def test_handle_request_ip_and_rate_rejections(monkeypatch):
    """退步了会怎样：IP/限流拦截返回 200 或没记账 → 攻击面与观测面同时失真。"""
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False,
                                            ip_whitelist=['10.0.0.1']))
    h = _FakeHandler(b'{}')
    r._handle_request(h)
    assert h.status == 403 and r.stats.rejected_ip == 1

    r2 = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False,
                                             rate_limit_per_minute=1))
    h2 = _FakeHandler(b'{}')
    r2._handle_request(h2)
    h3 = _FakeHandler(b'{}')
    r2._handle_request(h3)
    assert h3.status == 429 and r2.stats.rejected_rate == 1


def test_handle_request_bad_json(receiver):
    """退步了会怎样：坏 JSON 被当成正常事件分发（下游动作拿到空/坏 payload）。"""
    h = _FakeHandler(b'not-json')
    receiver._handle_request(h)
    assert h.status == 400 and receiver.stats.rejected_format == 1
    assert h.response_json()['error'] == 'invalid_json'


def test_handle_request_no_route_accepted(receiver):
    """退步了会怎样：无路由时返回 500/不记账 → 上游 webhook 平台判定投递失败并重试。"""
    h = _FakeHandler(b'{"event":"unknown.event"}',
                     {'Content-Length': str(len(b'{"event":"unknown.event"}'))})
    receiver._handle_request(h)
    assert h.status == 202
    assert h.response_json()['dispatched'] is False
    assert receiver.stats.accepted == 1
    assert receiver.get_logs()[-1]['event_type'] == 'unknown.event'


def test_handle_request_dispatches_route(monkeypatch):
    """退步了会怎样：有路由却不分发/分发参数错 → webhook 收得到但动作永不执行。"""
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    r.register_route('github.push', 'a.push')
    dispatched = []
    monkeypatch.setattr(r, '_dispatch_action',
                        lambda action, event, payload: dispatched.append((action, event, payload)))
    _sync_thread(monkeypatch)
    body = b'{"event":"github.push","v":1}'
    h = _FakeHandler(body, {'Content-Length': str(len(body))})
    r._handle_request(h)
    assert h.status == 200 and h.response_json()['dispatched'] is True
    assert dispatched == [('a.push', 'github.push', {'event': 'github.push', 'v': 1})]


def test_handle_request_signature_required(monkeypatch):
    """退步了会怎样：require_signature=True 时缺签名/错签名仍执行 → 任意伪造触发动作。"""
    r = wh.WebhookReceiver(wh.WebhookConfig(secret='s'))
    body = b'{"event":"x"}'
    h = _FakeHandler(body, {'Content-Length': str(len(body))})
    r._handle_request(h)
    assert h.status == 401 and r.stats.rejected_signature == 1
    assert h.response_json()['error'] == 'invalid_signature'


def test_handle_request_timestamp_expired(receiver):
    """退步了会怎样：过期时间戳被接受 → 重放攻击窗口无限。"""
    payload = {'event': 'x', 'timestamp': str(time.time() - 10_000)}
    body = json.dumps(payload).encode()
    h = _FakeHandler(body, {'Content-Length': str(len(body))})
    receiver._handle_request(h)
    assert h.status == 400 and h.response_json()['error'] == 'timestamp_expired'


def test_handle_request_invalid_timestamp_is_rejected(receiver):
    """退步了会怎样：`timestamp: "abc"` 静默放行 → 只要把时间戳写成非数字就绕过防重放。

    W3 修复后：非法 timestamp → 400 invalid_timestamp。"""
    body = b'{"event":"x","timestamp":"abc"}'
    h = _FakeHandler(body, {'Content-Length': str(len(body))})
    receiver._handle_request(h)
    assert h.status == 400
    assert h.response_json()['error'] == 'invalid_timestamp'


def test_handle_request_malformed_content_length_is_structured_error(receiver):
    """退步了会怎样：一个坏 header 打挂请求线程 → 连接被断开而不是返回 4xx。
    W4 修复后：非整数/负值都返回 400 invalid_content_length（不再 ValueError/read(-1)）。"""
    for bad in ('abc', '-1', '-999'):
        h = _FakeHandler(b'{}', {'Content-Length': bad})
        receiver._handle_request(h)
        assert h.status == 400, bad
        assert h.response_json()['error'] == 'invalid_content_length'


def test_handle_request_header_event_precedence(receiver):
    """退步了会怎样：X-GitHub-Event / X-GitLab-Event 被 payload.event 覆盖 → 路由错。"""
    body = b'{"event":"payload.event"}'
    h = _FakeHandler(body, {'Content-Length': str(len(body)),
                            'X-GitHub-Event': 'github.push'})
    receiver._handle_request(h)
    assert receiver.get_logs()[-1]['event_type'] == 'github.push'


# ═══════════════════════════════════════════════════════════════════════
# 分发 / 日志 / 状态 / 响应
# ═══════════════════════════════════════════════════════════════════════

def test_dispatch_action_calls_executor(monkeypatch):
    """退步了会怎样：分发不调用 executor（当前实现曾 ImportError 被吞）→ webhook 永不触发动作。"""
    import vools.actus.executor as ex
    seen = {}

    def fake_execute(action_id, params=None, **kwargs):
        seen['action'] = action_id
        seen['params'] = params
        return {'status': 'ok'}

    monkeypatch.setattr(ex, 'execute', fake_execute)
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    assert r._dispatch_action('a.b', 'github.push', {'x': 1}) == {'status': 'ok'}
    assert seen['action'] == 'a.b'
    assert seen['params'] == {'event_type': 'github.push', 'payload': {'x': 1},
                              'triggered_by': 'webhook'}


def test_dispatch_action_failure_is_logged_not_silent(monkeypatch, caplog):
    """退步了会怎样：异步分发失败完全静默 → 上游只会看到 dispatched:true，事故无从复盘。
    W6 修复后：结构化 logger.warning + get_status().dispatch 可查（返回值保持 None 兼容）。"""
    import vools.actus.executor as ex
    monkeypatch.setattr(ex, 'execute', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    with caplog.at_level('WARNING', logger='vools.actus.webhook'):
        assert r._dispatch_action('a.b', 'e', {}) is None
    assert any('Webhook 触发动作失败' in rec.message for rec in caplog.records), caplog.text
    d = r.get_status()['dispatch']
    assert d['errors'] == 1 and 'boom' in d['last_error']


def test_handle_request_rejects_oversize_body(receiver):
    """退步了会怎样（W7）：无上限读 body → 一个超大请求打爆内存。修复后超限 413。"""
    receiver._config.max_body_bytes = 8
    body = b'{"event":"x"}'          # 13 bytes > 8
    h = _FakeHandler(body, {'Content-Length': str(len(body))})
    receiver._handle_request(h)
    assert h.status == 413
    assert h.response_json()['error'] == 'payload_too_large'


def test_dispatch_saturation_returns_503(monkeypatch):
    """退步了会怎样（W7）：并发分发无上限 → 线程爆炸；或饱和时仍谎报 dispatched:true。
    修复后：有界信号量，饱和 → 503 dispatch_saturated。"""
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False,
                                            max_dispatch_workers=1))
    r.register_route('e', 'a')
    assert r._dispatch_slots.acquire(blocking=False) is True   # 占满唯一槽位
    body = b'{"event":"e"}'
    h = _FakeHandler(body, {'Content-Length': str(len(body))})
    r._handle_request(h)
    assert h.status == 503
    assert h.response_json()['error'] == 'dispatch_saturated'
    assert h.response_json()['dispatched'] is False
    r._dispatch_slots.release()


def test_dispatch_thread_start_failure_returns_503(monkeypatch):
    """退步了会怎样（W7）：线程起不来仍返回 200 dispatched:true → 请求被"假成功"。
    修复后：503 dispatch_thread_failed，并记录到 dispatch.errors。"""
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    r.register_route('e', 'a')

    class _BadThread(object):
        def __init__(self, *a, **k):
            pass

        def start(self):
            raise RuntimeError('thread pool exhausted')

    monkeypatch.setattr(wh.threading, 'Thread', _BadThread)
    body = b'{"event":"e"}'
    h = _FakeHandler(body, {'Content-Length': str(len(body))})
    r._handle_request(h)
    assert h.status == 503 and h.response_json()['dispatched'] is False
    assert r.get_status()['dispatch']['errors'] == 1


def test_rate_limiter_key_table_is_bounded(monkeypatch):
    """退步了会怎样（W8）：按 IP 建 key 永不清 → 伪造大量 IP 时内存持续增长。
    修复后：超过 MAX_TRACKED_IPS 时淘汰最老 key。"""
    monkeypatch.setattr(wh, 'MAX_TRACKED_IPS', 5)
    lim = wh.RateLimiter(1000)
    for i in range(20):
        lim.check('10.0.0.%d' % i)
    assert len(lim._requests) <= 5, len(lim._requests)


def test_request_log_limit_and_get_logs(receiver):
    """退步了会怎样：日志无限增长（内存泄漏）或 get_logs 返回顺序反了。"""
    for i in range(1005):
        receiver._log_request('1.1.1.1', 'e', 'a', {'i': i})
    logs = receiver.get_logs(limit=1000)
    assert len(logs) == 1000 and logs[0]['payload_size'] > 0
    assert receiver.get_logs(limit=3)[-1]['payload_size'] > 0


def test_get_status_shape(receiver):
    """退步了会怎样：状态缺 running/config/stats → 运维面板/健康检查拿不到关键字段。"""
    receiver.register_route('e', 'a')
    d = receiver.get_status()
    assert d['running'] is False
    assert d['routes'] == {'e': 'a'}
    assert d['config']['require_signature'] is False
    assert 'stats' in d and 'total_requests' in d['stats']


def test_respond_writes_json(receiver):
    """退步了会怎样：响应 Content-Type/JSON 编码错 → 上游解析失败并无限重试。"""
    h = _FakeHandler()
    wh.WebhookReceiver._respond(h, 201, {'ok': True})
    assert h.status == 201
    assert ('Content-Type', 'application/json') in h.sent
    assert h.response_json() == {'ok': True}
    h2 = _FakeHandler()
    wh.WebhookReceiver._respond_json(h2, 202, {'x': 1})
    assert h2.status == 202 and h2.response_json() == {'x': 1}


def test_get_handler_routes_post_and_health(receiver, monkeypatch):
    """退步了会怎样：GET /health 不可用或未知路径返回 200 → 健康检查失真。"""
    handler_cls = receiver._make_handler()
    responses = []
    monkeypatch.setattr(receiver, '_respond',
                        lambda h, status, body: responses.append((status, body)))
    h = type('H', (), {'path': '/health'})()
    handler_cls.do_GET(h)
    assert responses[-1][0] == 200 and responses[-1][1]['status'] == 'ok'
    h.path = '/other'
    handler_cls.do_GET(h)
    assert responses[-1] == (404, {'error': 'not_found'})


# ═══════════════════════════════════════════════════════════════════════
# 启动 / 停止（HTTPServer 替身，不真绑端口）
# ═══════════════════════════════════════════════════════════════════════

class _FakeServer(object):
    def __init__(self, *a, **k):
        self.shutdown_called = False

    def serve_forever(self):
        raise KeyboardInterrupt

    def shutdown(self):
        self.shutdown_called = True


def test_start_and_stop_with_fake_server(monkeypatch, capsys):
    """退步了会怎样：start 不置 running/started_at（状态机撒谎）或 stop 不 shutdown
    （端口泄漏，下次启动 EADDRINUSE）。"""
    monkeypatch.setattr(wh, 'HTTPServer', _FakeServer)
    r = wh.WebhookReceiver(wh.WebhookConfig(host='127.0.0.1', port=0,
                                            require_signature=False))
    r.start()
    assert r.is_running is False          # KeyboardInterrupt 后的 finally
    assert r.stats.started_at > 0
    assert r._ready.is_set()

    r2 = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    server = _FakeServer()
    r2._server = server
    r2.stop()
    assert server.shutdown_called is True and r2._server is None
    assert '已停止' in capsys.readouterr().out


def test_start_background_reports_bind_error(monkeypatch):
    """退步了会怎样：端口占用/权限不足被吞 → 调用方拿到"看似启动成功"的线程，
    后续所有 webhook 静默丢失。"""
    class _BadServer(object):
        def __init__(self, *a, **k):
            raise OSError('EADDRINUSE')

    monkeypatch.setattr(wh, 'HTTPServer', _BadServer)
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    with pytest.raises(OSError, match='EADDRINUSE'):
        r.start_background(timeout=1.0)


def test_start_background_success_and_stop(monkeypatch):
    """退步了会怎样：后台启动返回时端口未绑（is_running 可能 False）→ 调用方立刻发请求失败。"""
    monkeypatch.setattr(wh, 'HTTPServer', _FakeServer)
    r = wh.WebhookReceiver(wh.WebhookConfig(host='127.0.0.1', port=0,
                                            require_signature=False))
    # 假 server 在后台线程里 print 中文；必须等线程彻底结束后再让 pytest 回收
    # capture（否则后台 print 与 capture 关闭竞争，会把整场 capture 流解码搞坏）。
    thread = r.start_background(timeout=2.0)
    assert thread is not None
    thread.join(timeout=2.0)
    assert r._ready.is_set()


def test_start_background_timeout(monkeypatch):
    """退步了会怎样：线程没起来时无限等待/假装成功 → 启动流程挂死或静默失败。"""
    class _DeadThread(object):
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    monkeypatch.setattr(wh.threading, 'Thread', _DeadThread)
    r = wh.WebhookReceiver(wh.WebhookConfig(require_signature=False))
    with pytest.raises(TimeoutError, match='未能'):
        r.start_background(timeout=0.01)


def test_create_receiver_and_start_webhook_background(monkeypatch):
    """退步了会怎样：便捷函数不传参/不启动 → 与主 API 行为分叉。"""
    rec = wh.create_receiver(host='127.0.0.1', port=1, secret='s',
                             require_signature=False, ip_whitelist=['1.1.1.1'])
    assert rec.get_status()['config']['port'] == 1
    assert rec.get_status()['config']['ip_whitelist'] == ['1.1.1.1']

    started = []
    monkeypatch.setattr(wh.WebhookReceiver, 'start_background',
                        lambda self, timeout=5.0: started.append(True) or self)
    rec2 = wh.start_webhook_background(host='127.0.0.1', port=2, secret='x')
    assert isinstance(rec2, wh.WebhookReceiver) and started == [True]
