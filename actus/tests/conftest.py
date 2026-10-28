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

    advance.clock = clock
    return advance
