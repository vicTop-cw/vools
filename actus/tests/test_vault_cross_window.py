# -*- coding: utf-8 -*-
"""actus/tests/test_vault_cross_window.py — P0：L2/L3 密钥必须**跨 TOTP 窗口可读**。

这是本会话最严重的 bug（P0）：L2/L3 的 `master_key` 派生把**每 60 秒变一次的动态码**
放进了 KDF：

    dynamic_code = TOTP(seed_key, 当前窗口)          # 60s 变一次
    master_key   = PBKDF2(seed_key_hex + dynamic_code, key_salt)

于是「窗口 N 写入的密钥，窗口 N+1 用新 auth 会话读」必然解密失败
（实测：窗口 1 set→ok，+300s 后 get→「凭证解密失败（密钥错误？）」）。
而 `register()` **默认级别就是 L2** —— 默认配置下今天存的密钥明天读不出来。

为什么之前 15 轮没发现（第四类测试盲区：**时间跨度不够**）
--------------------------------------------------------
所有用例都在**同一个 60 秒窗口**内跑 `register → auth → set → get`；
`pytest -k vault` 54 passed 全绿，恰恰因为**跑得太快**。

本文件用**可控假时钟**（monkeypatch `vault2.time`）把窗口推进到下一/五个窗口，
不 sleep、不依赖真实时间；先写测试看红，修复后必须绿。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import time as real_time  # noqa: E402  — 真实时间模块，仅供 FakeClock 兜底属性

from vools.actus import vault2 as vault2_mod  # noqa: E402
from vools.actus.vault2 import DEFAULT_TIME_STEP, Vault2  # noqa: E402
from vools.security import otp as otp_mod  # noqa: E402

_PIN = "123456"


# ---------------------------------------------------------------------------
# 可控假时钟 + 隔离夹具
# ---------------------------------------------------------------------------

class _FakeClock(object):
    """TOTP 窗口可控制的时钟：只替换 `vault2.time`，不 sleep。"""

    def __init__(self, start: int):
        self.now = int(start)

    def time(self) -> float:
        return float(self.now)

    def __getattr__(self, name):
        # `vault2` 只在 anomaly_check 里用 time.localtime；其余属性透传真实模块
        return getattr(real_time, name)


class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    v2dir = tmp_path / "vault2"
    for directory in (home, meta, v2dir):
        directory.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_VAULT2_DIR", str(v2dir))
    # file-key：避开 OS keyring 交互，确定性
    monkeypatch.setenv("ACTUS_VAULT2_KEY_PROTECTION", "file-key")
    monkeypatch.setenv("ACTUS_VAULT2_NO_PROMPT", "1")
    monkeypatch.delenv("ACTUS_VAULT_KEY", raising=False)
    monkeypatch.delenv("ACTUS_VAULT_LAZY_MIGRATE", raising=False)

    vault2_mod._vault2_singleton = None
    clock = _FakeClock(1_700_000_000)      # 固定时刻，窗口边界确定
    # TOTP 算法定义在 vools.security.otp（vault2 只是 import 引用）——两处都要 patch，
    # 否则窗口推进只影响 vault2 的过期判断，动态码仍按真实时间生成。
    monkeypatch.setattr(vault2_mod, "time", clock)
    monkeypatch.setattr(otp_mod, "time", clock)

    w = _World()
    w.vault = Vault2(vault_dir=str(v2dir))
    w.clock = clock
    return w


def _register_and_auth(vault, identity, level):
    reg = vault.register(identity, _PIN, security_level=level)
    assert reg["status"] == "ok", reg
    auth = vault.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert auth["status"] == "ok", auth
    return reg, auth


def _auth(vault, reg):
    return vault.auth(reg["identity_id"], reg["machine_id"], _PIN)


# ===========================================================================
# ① 核心：L2（默认级别）密钥跨窗口必须仍可读
# ===========================================================================

def test_secret_survives_across_totp_windows(world):
    """退步了会怎样（P0 本体）：L2/L3 的 master_key 派生含**每分钟变化的动态码** ——
    窗口 N 写入的密钥，窗口 N+1 重新 auth 后解密失败（「凭证密钥错误」），
    而 `register()` 默认就是 L2 → 默认配置下用户今天存的密钥明天读不出来。

    断言：窗口 N 写入 → 推进到窗口 N+1 → **重新 auth**（新会话/新 master_key）
    → get 必须成功且值一致。这是密码学前提，不是实现细节。
    """
    reg, auth_n = _register_and_auth(world.vault, "alice", "L2")
    token_n = auth_n["session_token"]
    written = world.vault.set_secret(token_n, "db_pw", "TOP-SECRET")
    assert written["status"] == "ok", written

    # 推进一个完整窗口（+61s，避免边界抖动；不 sleep）
    world.clock.now += DEFAULT_TIME_STEP + 1
    auth_next = _auth(world.vault, reg)
    assert auth_next["status"] == "ok", auth_next

    got = world.vault.get_secret(auth_next["session_token"], "db_pw")

    assert got["status"] == "ok", (
        "跨 TOTP 窗口后密钥解不开了（P0）：%r" % (got,))
    assert got["value"] == "TOP-SECRET"


# ===========================================================================
# ② 对照：L1 不受窗口影响（证明这是 L2/L3 专属问题）
# ===========================================================================

def test_l1_is_unaffected_by_window(world):
    """退步了会怎样：连 L1（`effective_dynamic=''`，本就不该受窗口影响）也跨窗口失效
    —— 说明问题不在"动态码进了 KDF"，而是更底层的密钥管理崩了。

    断言：L1 窗口 N 写入 → 推进窗口 → 重新 auth → get 成功且值一致。
    """
    reg, auth_n = _register_and_auth(world.vault, "bob", "L1")
    assert world.vault.set_secret(auth_n["session_token"], "l1_key", "L1-VALUE")["status"] == "ok"

    world.clock.now += DEFAULT_TIME_STEP + 1
    auth_next = _auth(world.vault, reg)
    assert auth_next["status"] == "ok", auth_next

    got = world.vault.get_secret(auth_next["session_token"], "l1_key")

    assert got["status"] == "ok", got
    assert got["value"] == "L1-VALUE"


# ===========================================================================
# ③ 显式契约：跨多个窗口（5 分钟）仍可读 —— docstring 钉成密码学前提
# ===========================================================================

def test_write_and_read_in_different_windows_is_documented_contract(world):
    """**契约（不是实现细节）**：密钥的生命周期必须比 TOTP 窗口长。

    TOTP 动态码只用于**认证**（证明"此刻持有 seed 的人"），绝不能进入
    `master_key` 的 KDF —— 否则密钥可读性绑定在 60 秒窗口上，而 `register()`
    默认 L2 意味着默认配置下数据一天内必丢。本用例把"跨窗口可读"钉成**显式契约**：
    任何"优化"若让 master_key 依赖当前窗口，这里必须红。

    断言：窗口 N 写入 → 推进 5 个窗口（+300s）→ 重新 auth → get 仍成功、值一致。
    """
    reg, auth_n = _register_and_auth(world.vault, "carol", "L2")
    assert world.vault.set_secret(auth_n["session_token"], "long_lived",
                                  "LONG-LIVED-VALUE")["status"] == "ok"

    world.clock.now += 5 * DEFAULT_TIME_STEP      # 跨 5 个窗口
    auth_later = _auth(world.vault, reg)
    assert auth_later["status"] == "ok", auth_later

    got = world.vault.get_secret(auth_later["session_token"], "long_lived")

    assert got["status"] == "ok", (
        "跨 5 个 TOTP 窗口后密钥不可读 —— 密钥生命周期被绑死在 60s 窗口上：%r"
        % (got,))
    assert got["value"] == "LONG-LIVED-VALUE"
