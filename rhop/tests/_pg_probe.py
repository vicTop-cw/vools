# -*- coding: utf-8 -*-
"""PG 用例放行探针：修掉「探活一次就放行」造成的**假红**（测试基础设施缺陷）。

背景（实测，不是推测）
----------------------
原实现（``test_pg_store.py::_pg_available``）只做**一次** ``psycopg2.connect`` 就决定
整组 pg 用例跑不跑。但 Windows → WSL 的 localhost 转发是**抖动**的：

    某一刻恰好连得上  → 40+ 条用例被放行 → 随后真实查询超时 → 一片假红
        （实测出现过 ``646 passed + 3 errors``、``637 passed + 11 errors``）
    连接再断          → 恢复 ``604 passed / 45 skipped``

放行条件（三条全满足才跑）
--------------------------
1. **平台 / 显式 opt-in**
   * 非 Windows（WSL / Linux / CI 容器）默认跑 —— 那里 PG 是本地服务，可靠；
   * **Windows 默认 skip**：本机通常没有本地 PG，只可能是抖动转发；
     确认可用时可显式 ``RHOP_PG_TESTS=1`` 进入探活；
   * ``RHOP_PG_TESTS=0`` 在任何平台强制关闭。
2. **多次探活、全部成功**：连续 ``RHOP_PG_PROBE_ATTEMPTS``（默认 3）次，间隔
   ``RHOP_PG_PROBE_INTERVAL_SEC``（默认 0.2s）；**任一次失败即判「转发不稳」并 skip**
   —— 抖动窗口里放行最危险，宁可跳过也不制造假红。
3. **真实查询探活**：每次探活都跑 ``SELECT 1`` + **临时表建/插/查**。只证明「端口通」
   远远不够：转发会「连接成功但查询超时」，这正是假红的直接成因。临时表是会话级的，
   连接关闭即消失，不会污染库。

边界（**重要**）
----------------
本模块**只影响放行判定**。一旦放行，用例里的真实查询失败仍然是 **failure**：
这里没有任何 try/except 去吞用例异常，也不会把「探活不可靠」与「用例失败」混为一谈。
"""

from __future__ import absolute_import

import os
import sys
import time
from functools import lru_cache

#: 与本仓库 pg 测试一致的连接参数（独立一份，避免测试之间互相 import 私有常量）
PG_SPEC = {
    "kind": "postgres",
    "host": "127.0.0.1",
    "port": 5432,
    "user": "postgres",
    "password": "123456",
    "dbname": "postgres",
}

_OPT_IN_ENV = "RHOP_PG_TESTS"
_ATTEMPTS_ENV = "RHOP_PG_PROBE_ATTEMPTS"
_INTERVAL_ENV = "RHOP_PG_PROBE_INTERVAL_SEC"
_DEFAULT_ATTEMPTS = 3
_DEFAULT_INTERVAL_SEC = 0.2
_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("0", "false", "no", "off")


def _env_flag(name):
    """读三态开关：True / False / None（未设置或无法识别）。"""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return None


def _env_int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def probe_once(timeout=3.0):
    """一次「真实查询」探活：连接 → ``SELECT 1`` → 临时表建/插/查。

    任何一步失败都抛异常（由调用方统计），本函数不吞任何错误 —— 探活失败要留证据。
    """
    import psycopg2

    conn = psycopg2.connect(
        host=PG_SPEC["host"], port=PG_SPEC["port"], user=PG_SPEC["user"],
        password=PG_SPEC["password"], dbname=PG_SPEC["dbname"],
        connect_timeout=int(timeout),
    )
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            if cur.fetchone()[0] != 1:
                raise RuntimeError("SELECT 1 返回值异常")
            # 临时表 = 会话级，连接关掉即消失，不会在库里留垃圾
            cur.execute("CREATE TEMP TABLE rhop_pg_probe(x INTEGER)")
            cur.execute("INSERT INTO rhop_pg_probe VALUES (1)")
            cur.execute("SELECT x FROM rhop_pg_probe")
            row = cur.fetchone()
            if not row or row[0] != 1:
                raise RuntimeError("临时表读写结果异常: %r" % (row,))
    finally:
        try:
            conn.close()
        except Exception:
            pass


@lru_cache(maxsize=1)
def _gate():
    """计算一次放行结论（进程内缓存，避免每个测试模块重复探活）。"""
    override = _env_flag(_OPT_IN_ENV)
    if override is False:
        return False, "%s=0：显式关闭 pg 用例。" % _OPT_IN_ENV

    if override is None and sys.platform.startswith("win"):
        return False, (
            "Windows 上默认跳过 pg 用例：本机通常没有本地 PostgreSQL，"
            "Windows→WSL 的 localhost 转发是抖动的（探活一次就放行会制造假红）。"
            "请在 WSL/容器内跑，例如："
            "wsl -d Ubuntu-22.04 -- bash -lc \"cd <repo>/rhop && "
            "python3 -m pytest -q tests/test_pg_store.py\"；"
            "若确认 Windows 侧 PG 稳定可用，可设 %s=1 强制参与探活。" % _OPT_IN_ENV)

    attempts = _env_int(_ATTEMPTS_ENV, _DEFAULT_ATTEMPTS)
    interval = _env_float(_INTERVAL_ENV, _DEFAULT_INTERVAL_SEC)
    successes = 0
    last_error = ""
    for index in range(attempts):
        if index:
            time.sleep(interval)
        try:
            probe_once()
            successes += 1
        except Exception as exc:  # noqa: BLE001 - 探活失败要计数并留证，不吞
            last_error = "%s: %s" % (type(exc).__name__, str(exc).splitlines()[0][:160])

    if successes == attempts:
        return True, ""

    return False, (
        "PostgreSQL 探活不稳（%d/%d 次成功，间隔 %.0fms）→ 跳过 pg 用例；"
        "最近一次错误：%s。转发抖动期放行会制造假红，故此处宁可不跑。"
        "如在 WSL/容器内，请确认 PG 已启动；Windows 侧请改用 "
        "`wsl -d Ubuntu-22.04 -- bash -lc \"cd <repo>/rhop && "
        "python3 -m pytest ...\"`，或确认 PG 稳定可用后设 %s=1 重试。"
        % (successes, attempts, interval * 1000,
           last_error or "（未捕获到异常文本）", _OPT_IN_ENV))


def pg_gate():
    """返回 ``(allowed, reason)``：``allowed=False`` 时 ``reason`` 说明为什么跳过。"""
    return _gate()


def pg_probe_status():
    """诊断用：返回当前放行结论的 dict（不含异常栈）。"""
    allowed, reason = _gate()
    return {
        "allowed": allowed,
        "reason": reason,
        "platform": sys.platform,
        "opt_in": _env_flag(_OPT_IN_ENV),
        "attempts": _env_int(_ATTEMPTS_ENV, _DEFAULT_ATTEMPTS),
        "interval_sec": _env_float(_INTERVAL_ENV, _DEFAULT_INTERVAL_SEC),
    }
