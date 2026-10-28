# -*- coding: utf-8 -*-
"""actus 测试套件全局夹具：**运行时数据目录默认隔离**（测试卫生）。

背景（第 15 轮，真实事故）：测试套件跑完会把真实仓库 `_meta/` 写脏
（`events.jsonl` / `probe_cache.json` / `actions.index.json` / `call_log.db` /
`runs/*.json` / `status.json` / `logs/*`）。它们是 gitignore 的运行时状态，但同属
「测试写真实仓库文件」——与 `calculator.actus.schema.md` 被中断污染同族：
并发跑、CI 次跑之间会互相影响，也让「零副作用」类断言失真。

做法：autouse 把 `ACTUS_META_DIR` 默认指到 per-test tmp 目录。各用例自己
`monkeypatch.setenv("ACTUS_META_DIR", ...)` 时（更具体）仍以用例为准。
本夹具**不碰** `actions/`、`contracts/` 等真实产物目录（那是产物，不是运行时状态）。
"""

import time as _real_time

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_meta_dir(tmp_path, monkeypatch):
    """默认把 `_meta` 运行时目录隔离到 tmp，防止测试写真实仓库的 `_meta/`。"""
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "_meta_runtime"))


# ---------------------------------------------------------------------------
# 共用时间控制夹具：`advance_totp_window(n)`
#
# 为什么要有它（这是本会话 P0 的根因）：
#   14 轮测试全绿，但 L2/L3 的 master_key 曾把**每 60 秒变一次的 TOTP 动态码**
#   掺进 PBKDF2 —— 默认级别 L2 意味着"今天存的密钥明天解不开"（P0）。
#   所有用例都在**同一个 60 秒窗口**内跑 `register → auth → set → get`，
#   于是**测试跑得太快，替 bug 做了掩护**。没有可控时间，这类缺陷永远测不出来。
# ---------------------------------------------------------------------------

class _TotpClock(object):
    """可推进的假时钟（TOTP 窗口 = int(time.time()) // 60）。"""

    def __init__(self, now):
        self.now = float(now)

    def time(self):
        return self.now

    def __getattr__(self, name):
        # vault2 只在 anomaly_check 里用 time.localtime 等；其余属性透传真实模块
        return getattr(_real_time, name)


@pytest.fixture
def advance_totp_window(monkeypatch):
    """返回 `advance(n)`：把 TOTP 时间推进 n 个 60s 窗口（不 sleep）。

    **必须同时 patch 两处 time**（实测踩过）：
      * `vault2.time` —— 会话过期/审计/`used_codes` 时间；
      * `vools.security.otp.time` —— **TOTP 算法本体**定义在 core 的
        `vools/security/otp.py`，vault2 只是 import 引用。只换 vault2.time 时
        动态码仍按真实时间生成 → 推进窗口后第二次 auth 会先撞「动态码已被使用」，
        根本走不到"跨窗口解密"那一步。

    用法：
        def test_x(advance_totp_window):
            ... 窗口 N 写 ...
            advance_totp_window(1)      # 推进 1 个窗口
            ... 窗口 N+1 读 ...
        advance_totp_window(5)          # 推进 5 个窗口

    复原：全部走 monkeypatch，用例结束自动恢复，**不要手动改全局 time**。
    """
    from vools.actus import vault2 as _vault2
    from vools.security import otp as _otp

    clock = _TotpClock(_real_time.time())
    monkeypatch.setattr(_vault2, "time", clock)
    monkeypatch.setattr(_otp, "time", clock)

    def advance(n=1):
        clock.now += float(n) * 60.0
        return clock.now

    def advance_seconds(n=1):
        """秒级推进（TTL / used_codes 清理边界用；TOTP 窗口按 60s 粒度自动跟随）。"""
        clock.now += float(n)
        return clock.now

    advance.clock = clock
    advance.seconds = advance_seconds
    return advance


# ---------------------------------------------------------------------------
# 进程级单例重置（第 18 轮审计 #2/#6：顺序依赖 / xdist 随机红）
#
# `vault2._vault2_singleton`、`security._scanner`、`eventbus._bus`、`mcp_server._TASKS`
# 都是**进程级单例**。此前没有统一重置，测试顺序一变 / xdist 并发就会随机红，
# 而且会掩盖"单例状态未清理"的真实产品缺陷。
# 只在测试侧重置，不改产品代码；每个用例前后各重置一次，保证顺序无关。
# ---------------------------------------------------------------------------

def _reset_process_globals():
    """重置进程级单例（测试卫生；任何失败都不应阻断其它清理）。"""
    try:
        from vools.actus import eventbus as _eventbus
        _eventbus._bus = _eventbus.EventBus()
    except Exception:                      # noqa: BLE001 —— 导入/构造失败不阻断
        pass
    try:
        from vools.actus import mcp_server as _mcp
        try:
            _mcp._detach_event_forwarding()
        except Exception:                  # noqa: BLE001
            pass
        lock = getattr(_mcp, "_TASKS_LOCK", None)
        if lock is not None:
            with lock:
                _mcp._TASKS.clear()
        else:                              # pragma: no cover
            _mcp._TASKS.clear()
    except Exception:                      # noqa: BLE001
        pass
    try:
        from vools.actus import vault2 as _vault2
        _vault2._vault2_singleton = None
    except Exception:                      # noqa: BLE001
        pass
    try:
        from vools.actus import security as _security
        _security._scanner = None
    except Exception:                      # noqa: BLE001
        pass


@pytest.fixture(autouse=True)
def reset_globals():
    """用例前后重置进程级单例（顺序无关；xdist 下也不会互相污染）。"""
    _reset_process_globals()
    yield
    _reset_process_globals()
