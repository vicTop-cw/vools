# -*- coding: utf-8 -*-
"""webhook_server.py 契约测试（第 42 轮，round 32 任务）。

被测对象：``vools/actus/webhook_server.py`` —— `WebhookServer`，即
TriggerEngine 的 HTTP 端点 executor（包装 webhook.py 的 WebhookReceiver 为标准
add/remove/start/stop/status 接口）。

覆盖目标
--------
1. 服务启动/停止：正常启动、正常停止、**端口占用 → 明确报错**、start 幂等；
2. 请求处理（包装层）：路由注册/注销、按 event_type 分发到 callback、未知路由；
3. 错误路径：绑定失败/握手超时向上抛、callback 内部异常、分发失败；
4. 边界：空路由表、并发分发、重复 stop、stop 前未 start；
5. 安全：**默认绑定地址（0.0.0.0 vs 127.0.0.1）**、secret 为空时签名开关、
   回调降级路径。

为什么**不真绑端口、不真发网络**：`WebhookReceiver.start_background()` 用子类替身
（只置 `_running`/`started_at`、不 bind socket）；HTTP 状态码层面的行为属于
webhook.py（另一个文件，已由 `tests/test_webhook_contracts_r32.py` 覆盖），
本文件只测 webhook_server 自己的包装逻辑。分发用 `_SyncThread` 把 Thread 换成
同步执行，断言才确定（并发用真线程的用例除外）。

约定：每条 docstring 写「退步了会怎样」；已确认但**未修**的产品 bug 用
`xfail(strict=True)` 钉「正确语义」—— 产品修好后 strict XPASS 会提醒删标记。
"""

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import webhook_server as ws  # noqa: E402
from vools.actus.triggers import Trigger  # noqa: E402
from vools.actus.webhook import WebhookConfig, WebhookReceiver  # noqa: E402


SECRET = 'r32-webhook-server-secret'


# ── 替身 ──────────────────────────────────────────────────────────────────

class _NoBindReceiver(WebhookReceiver):
    """不绑端口的接收器替身：`start_background()` 只置状态，零 socket、零网络。

    真实 `start_background()` 会 bind socket（端口占用/权限问题在真实环境才出现），
    测试里换成这个替身既避免占用端口，也让 start() 走完它的全部包装逻辑
    （建 config、注册路由、覆盖 _dispatch_action、置 _running）。
    """

    def start_background(self, timeout: float = 5.0):
        self._stats.started_at = time.time()
        self._running = True
        self._ready.set()
        self._thread = None
        return None


class _SyncThread(object):
    """`threading.Thread` 替身：start() 直接同步执行目标函数（断言确定）。"""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **kw):
        self.target = target
        self.args = args or ()
        self.kwargs = kwargs or {}

    def start(self):
        if self.target is not None:
            self.target(*self.args, **self.kwargs)

    def is_alive(self):
        return False

    def join(self, timeout=None):
        return None


def _make_trigger(key, action_id):
    """构造 webhook 触发器（event_type = trigger.key）。"""
    return Trigger(action_id, {'type': 'webhook', 'key': key})


@pytest.fixture
def server(monkeypatch):
    """WebhookServer 实例，其接收器被替换成不绑端口的替身。"""
    monkeypatch.setattr(ws, 'WebhookReceiver', _NoBindReceiver)
    srv = ws.WebhookServer(port=8765, host='127.0.0.1', secret='')
    try:
        yield srv
    finally:
        try:
            srv.stop()
        except Exception:               # noqa: BLE001 —— teardown 不允许掩盖用例结果
            pass


@pytest.fixture
def sync_threads(monkeypatch):
    """把 `webhook_server.threading.Thread` 换成同步执行（等价于内联分发）。"""
    monkeypatch.setattr(ws.threading, 'Thread', _SyncThread)
    return _SyncThread


# ═══════════════════════════════════════════════════════════════════════
# 1) 路由注册 / 注销（add / remove）
# ═══════════════════════════════════════════════════════════════════════

def test_add_before_start_only_records_route(server):
    """退步了会怎样：start 之前 add 就构造/触碰接收器 → AttributeError（receiver 为 None）
    或路由丢失（启动后 HTTP 请求全落 202 no route）。"""
    seen = []
    server.add(_make_trigger('hook.a', 'act.a'), seen.append)

    st = server.status()
    assert st['webhooks'] == 1
    assert st['routes'] == {'hook.a': 'act.a'}
    assert st['running'] is False
    assert server._receiver is None          # 未启动时不提前建接收器


def test_add_after_start_registers_route_on_receiver(server):
    """退步了会怎样：启动后新增的触发器没有 register_route → WebhookReceiver 解析不到
    action，事件进来只回 202「没路由」，而 status() 却显示路由存在（两处口径打架）。"""
    server.start()
    server.add(_make_trigger('hook.late', 'act.late'), lambda t: None)

    assert server._receiver.get_routes() == {'hook.late': 'hook.late'}


def test_add_falls_back_to_action_id_when_key_empty(server):
    """退步了会怎样：trigger.key 为空时 event_type 变成空串 → 所有无 key 触发器挤在
    同一个 '' 路由上互相覆盖，只有最后一个能触发。"""
    server.add(Trigger('act.nokey', {'type': 'webhook'}), lambda t: None)

    assert server.status()['routes'] == {'act.nokey': 'act.nokey'}


def test_remove_drops_every_trigger_of_action_and_unregisters(server):
    """退步了会怎样：同一 action 的多个 webhook 触发器只删掉第一个（残留路由继续触发
    已删除的动作），或删了本地表却没 unregister → 接收器仍解析到旧 action。"""
    server.add(_make_trigger('hook.k1', 'act.a'), lambda t: None)
    server.add(_make_trigger('hook.k2', 'act.a'), lambda t: None)
    server.add(_make_trigger('hook.k3', 'act.b'), lambda t: None)
    server.start()

    server.remove('act.a')

    assert server.status()['routes'] == {'hook.k3': 'act.b'}
    assert server._receiver.get_routes() == {'hook.k3': 'hook.k3'}


def test_remove_unknown_action_is_noop(server):
    """退步了会怎样：删不存在的 action 抛 KeyError → 调用方（TriggerEngine.remove_trigger）
    在幂等清理路径上炸掉。"""
    server.add(_make_trigger('hook.a', 'act.a'), lambda t: None)
    server.remove('act.ghost')
    assert server.status()['routes'] == {'hook.a': 'act.a'}


def test_remove_before_start_is_safe(server):
    """退步了会怎样：未启动时 remove 触碰 self._receiver（None）→ AttributeError。"""
    server.add(_make_trigger('hook.a', 'act.a'), lambda t: None)
    server.remove('act.a')
    assert server.status()['routes'] == {}


# ═══════════════════════════════════════════════════════════════════════
# 2) 启动 / 停止
# ═══════════════════════════════════════════════════════════════════════

def test_start_registers_existing_routes_and_sets_running(server):
    """退步了会怎样：启动时没把已登记的 routes 灌进接收器 → 启动前注册的触发器全部
    失效（HTTP 端点收得到请求，但永远匹配不到动作）。"""
    server.add(_make_trigger('hook.a', 'act.a'), lambda t: None)
    server.add(_make_trigger('hook.b', 'act.b'), lambda t: None)

    server.start()

    assert server._receiver is not None and server._receiver.is_running is True
    assert server._receiver.get_routes() == {'hook.a': 'hook.a', 'hook.b': 'hook.b'}
    assert server.status()['running'] is True


def test_start_is_idempotent_and_keeps_same_receiver(server):
    """退步了会怎样：重复 start 重建接收器 → 旧 socket/线程泄漏（端口重复绑定），
    且已注册路由跟着旧接收器一起被丢弃。"""
    server.start()
    first = server._receiver
    server.start()
    assert server._receiver is first
    assert server.status()['running'] is True


def test_start_builds_config_from_server_fields(server):
    """退步了会怎样：host/port/secret 没传到 WebhookConfig → 监听错端口（触发器全收
    不到）或签名开关与配置相反（有 secret 却不校验签名 = 无认证端点）。"""
    server._port = 9123
    server._host = '127.0.0.1'
    server._secret = SECRET
    server.start()

    cfg = server._receiver._config
    assert (cfg.host, cfg.port, cfg.secret) == ('127.0.0.1', 9123, SECRET)
    assert cfg.require_signature is True          # 有 secret → 必须校验签名
    assert cfg.ip_whitelist == []


def test_start_propagates_oserror_when_port_in_use(monkeypatch):
    """退步了会怎样：端口占用被吞掉/只打日志 → start() 看着成功，实际没有任何 HTTP
    服务在监听（静默不可用），上层还以为 webhook 已就绪。"""
    class _Busy(_NoBindReceiver):
        def start_background(self, timeout: float = 5.0):
            raise OSError(10048, 'Only one usage of each socket address')

    monkeypatch.setattr(ws, 'WebhookReceiver', _Busy)
    srv = ws.WebhookServer(port=8765, host='127.0.0.1')

    with pytest.raises(OSError, match='socket address'):
        srv.start()

    assert srv.status()['running'] is False        # 失败后不谎报 running
    assert srv._receiver is not None and srv._receiver.is_running is False
    srv.stop()


def test_start_propagates_handshake_timeout(monkeypatch):
    """退步了会怎样：start_background 的握手超时被吞 → 调用方认为端口已绑好，随后
    stop() 看到 _server is None 跳过 shutdown，接收器线程自己 bind 成功后再也停不掉。"""
    class _Slow(_NoBindReceiver):
        def start_background(self, timeout: float = 5.0):
            raise TimeoutError('未能在 %ss 内绑定' % timeout)

    monkeypatch.setattr(ws, 'WebhookReceiver', _Slow)
    srv = ws.WebhookServer(port=8765, host='127.0.0.1')
    with pytest.raises(TimeoutError):
        srv.start()
    assert srv.status()['running'] is False
    srv.stop()


def test_stop_before_start_is_safe(server):
    """退步了会怎样：未启动就 stop 触碰 None 接收器 → AttributeError（TriggerEngine
    stop() 无条件调用它）。"""
    server.stop()
    assert server.status()['running'] is False
    assert server.status()['webhooks'] == 0


def test_stop_keeps_routes_and_is_idempotent(server):
    """退步了会怎样：stop 只关服务器**不擦**路由 → 重启后已注册的 webhook 路由还在；
    重复 stop 若二次 shutdown 则抛异常（幂等：不抛）。

    修复前：stop() 清空 `_routes`/`_callbacks`，重启后路由表为空、触发器永久失联。
    """
    server.add(_make_trigger('hook.a', 'act.a'), lambda t: None)
    server.start()

    server.stop()
    st = server.status()
    assert st['running'] is False
    # routes 必须保留（stop 不擦）
    assert st['routes'] == {'hook.a': 'act.a'}

    server.stop()                                   # 幂等：不抛
    assert server.status()['running'] is False
    assert server.status()['routes'] == {'hook.a': 'act.a'}


def test_stop_then_start_keeps_registered_routes(server):
    """退步了会怎样：重启后已注册的 webhook 路由必须还在。

    `WebhookServer.stop()` 只停监听，**不擦** `_routes`/`_callbacks` ——
    `engine.stop() → engine.start()` 之后 webhook 触发器应该仍能命中路由表。
    （修复前：stop() 清空路由表，start() 不重建，触发器永久失联，
    进站事件一律走「No route registered」202，无报错。）
    """
    server.add(_make_trigger('hook.a', 'act.a'), lambda t: None)
    server.start()
    server.stop()
    server.start()

    assert server.status()['routes'] == {'hook.a': 'act.a'}


# ═══════════════════════════════════════════════════════════════════════
# 3) 状态摘要（status）
# ═══════════════════════════════════════════════════════════════════════

def test_status_before_start_has_no_receiver_stats(server):
    """退步了会怎样：未启动时 status() 硬读接收器 → AttributeError，TriggerEngine.status()
    整体崩掉（它无条件调用 self._webhooks.status()）。"""
    st = server.status()
    assert st['webhooks'] == 0
    assert st['port'] == 8765
    assert st['running'] is False
    assert st['routes'] == {}
    assert 'total_requests' not in st        # 没接收器就不该有运行统计


def test_status_after_start_exposes_receiver_stats(server):
    """退步了会怎样：把 `self._receiver.stats`（property）写成 `stats()` → TypeError；
    历史上被 except-pass 吞掉，于是运行统计在 status() 里恒缺且无人报错。"""
    server.add(_make_trigger('hook.a', 'act.a'), lambda t: None)
    server.start()

    st = server.status()
    assert st['webhooks'] == 1
    assert st['running'] is True
    assert st['routes'] == {'hook.a': 'act.a'}
    # 接收器统计必须真的并进来（total_requests/accepted/uptime_seconds 都是真字段）
    assert st['total_requests'] == 0
    assert st['accepted'] == 0
    assert st['uptime_seconds'] >= 0


# ═══════════════════════════════════════════════════════════════════════
# 4) 分发接线（_dispatch_action 覆盖 + 回调执行）
# ═══════════════════════════════════════════════════════════════════════

def test_dispatch_exact_route_runs_callback_with_trigger(server, sync_threads):
    """退步了会怎样：覆盖 _dispatch_action 的接线断了 → 事件能解析到 action_id，但
    没有任何 callback 被执行（webhook 收得到、动作永不触发）。"""
    calls = []
    server.add(_make_trigger('hook.a', 'act.a'), calls.append)
    server.start()

    server._receiver._dispatch_action('hook.a', 'hook.a', {'k': 'v'})

    assert len(calls) == 1
    assert isinstance(calls[0], Trigger) and calls[0].action_id == 'act.a'


def test_dispatch_falls_back_to_matching_action_id(server, sync_threads):
    """退步了会怎样：接收器传来的 action_id 与路由 key 不一致时（前缀路由 `github.*`
    解析成自己的 action_id）找不到 callback → 该事件静默丢失。降级分支必须能按
    `trigger.action_id` 反查。"""
    calls = []
    server.add(_make_trigger('hook.b', 'act.b'), calls.append)
    server.start()

    # 模拟 resolve_action 返回 action_id 而非 event_type 的情形
    server._receiver._dispatch_action('act.b', 'hook.b', {})

    assert len(calls) == 1 and calls[0].action_id == 'act.b'


def test_dispatch_unknown_route_is_silent_noop(server, sync_threads):
    """退步了会怎样：未知 action_id 让覆盖函数抛 KeyError → 分发线程带异常退出
    （异常落在线程里，请求方只看到 200 dispatched=true，实际什么也没发生）。"""
    calls = []
    server.add(_make_trigger('hook.a', 'act.a'), calls.append)
    server.start()

    server._receiver._dispatch_action('ghost.action', 'ghost.event', {})
    assert calls == []                       # 不匹配任何路由：什么都不做、也不抛


def test_dispatch_does_not_forward_event_payload_to_callback(server, sync_threads):
    """审计发现（已报告，未修）：`_safe_call(cb, trigger, payload)` 里的 payload
    从未传给回调 —— `callback(trigger)` 只收到触发器，HTTP 请求体丢了。

    现状与 TriggerEngine 的回调契约 `callback(trigger)` 一致（不会崩），所以本用例
    钉的是**当前行为**；若产品改为把 payload 传下去（例如 `callback(trigger, payload)`
    或塞进 trigger.args），本用例会红 —— 那是行为变更，请同步更新断言。
    """
    seen = []
    server.add(_make_trigger('hook.a', 'act.a'),
               lambda *a, **kw: seen.append((a, kw)))
    server.start()

    server._receiver._dispatch_action('hook.a', 'hook.a', {'secret': 'payload'})

    assert len(seen) == 1
    args, kwargs = seen[0]
    assert len(args) == 1 and isinstance(args[0], Trigger)
    assert kwargs == {}


def test_concurrent_dispatch_runs_every_callback(server):
    """退步了会怎样：分发在锁里丢事件/串行饿死 → 高并发下部分 webhook 事件被吞
    （请求都回 200 dispatched，但没有对应回调执行）。"""
    total = 20
    done = threading.Event()
    calls = []
    lock = threading.Lock()

    def _cb(trigger):
        with lock:
            calls.append(trigger.action_id)
            if len(calls) >= total:
                done.set()

    server.add(_make_trigger('hook.a', 'act.a'), _cb)
    server.start()

    for _ in range(total):
        server._receiver._dispatch_action('hook.a', 'hook.a', {})

    assert done.wait(10), '并发分发丢事件：%d/%d' % (len(calls), total)
    assert calls == ['act.a'] * total


def test_safe_call_invokes_callback_and_returns_none():
    """退步了会怎样：_safe_call 不再调用回调（或改了返回契约）→ 分发静默失效。"""
    seen = []
    assert ws._safe_call(lambda t: seen.append(t), 'T') is None
    assert seen == ['T']


def test_safe_call_swallows_callback_exception(monkeypatch):
    """审计发现（已报告，未修）：回调异常被 `except Exception: pass` **完全吞掉**，
    既不记日志也不计数 —— 线上动作执行失败时没有任何可观测面。

    本用例钉当前「不向分发线程抛」的契约（避免一个坏回调打挂请求处理）；若产品改为
    记日志/计数后重抛，请同步更新断言并删除 finding 标记。
    """
    from vools.actus import webhook_server as mod

    def _boom(_trigger):
        raise RuntimeError('callback exploded')

    # 当前行为：吞掉、返回 None、不抛（进程内没有任何失败痕迹）
    assert ws._safe_call(_boom, 'T') is None
    assert not hasattr(mod, '_safe_call_errors')      # 没有失败计数面（finding）


# ═══════════════════════════════════════════════════════════════════════
# 5) 安全默认值
# ═══════════════════════════════════════════════════════════════════════

def test_default_bind_host_is_all_interfaces_and_signature_off(monkeypatch):
    """安全审计（已报告，未修）：WebhookServer 默认 `host='0.0.0.0'` + 空 secret，
    因而 `require_signature=False`。webhook 触发的是**动作执行**，于是默认配置 =
    「监听所有网卡 + 不校验签名 + 无 IP 白名单」的端点，同网段任何人可触发动作。

    对照：webhook.py 的 `WebhookConfig` 默认 `host='127.0.0.1'` 且默认
    require_signature=True —— 同一能力两套默认，包装层把安全默认放宽了。

    退步了会怎样：这条钉的是**当前不安全默认**。一旦产品收紧（改 127.0.0.1 或强制
    secret），本用例会红 —— 那是修好了，请把断言改成安全值并删掉这段说明。
    """
    monkeypatch.setattr(ws, 'WebhookReceiver', _NoBindReceiver)
    srv = ws.WebhookServer()                 # 全默认参数

    assert srv._host == '0.0.0.0'            # 全网卡可达
    assert srv._secret == ''                 # 无密钥
    srv.start()
    cfg = srv._receiver._config
    assert cfg.require_signature is False    # 于是签名校验被关闭
    assert cfg.ip_whitelist == []            # 且没有 IP 白名单
    srv.stop()

    # 对照：底层 WebhookConfig 的默认是回环地址
    assert WebhookConfig(require_signature=False).host == '127.0.0.1'


def test_start_sets_nonexistent_fallback_attribute_dead_code(server):
    """审计发现（已报告，低级）：`start()` 里的 `self._receiver._fallback_action_id = None`
    写的是一个**不存在的属性** —— WebhookReceiver 上真正的名字是 `_fallback_action`。

    这一行是死代码（真正的回退动作本来默认就是 None，所以当前没有安全影响）；
    但它掩盖了意图：若将来接收器带上了回退动作，这行「想清空回退」的写法根本清不掉。

    退步了会怎样：谁删掉这行，本用例的 `hasattr` 断言会红，提醒连注释一起清理；
    真正要守的是后半段 —— 未注册事件不得落到任何回退动作上。
    """
    server.start()
    receiver = server._receiver

    assert getattr(receiver, '_fallback_action', None) is None   # 真正的回退动作未被设置
    assert receiver.resolve_action('never.registered') is None   # 未注册事件不落任何动作
    assert hasattr(receiver, '_fallback_action_id')              # 死代码留下的影子属性
