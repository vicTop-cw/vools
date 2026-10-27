# -*- coding: utf-8 -*-
"""心跳判活的边界加固（本轮寻虫发现）。

缺陷：
  1. **未来时间戳 fail-open**：`age` 为负时 `age <= stale_after_sec` 恒成立 →
     判 `alive`。B 的时钟超前 9 小时（或有人把 ts 改到未来），会让一个已经
     死掉的 B 再"活"9 小时，A 永远等不到判死。
  2. **`stale_after_sec` / `interval_sec` 零校验**：
     · `stale_after_sec=-5` 被接受 → `age <= -5` 几乎永不成立 → **B 永远被判死**
     · `stale_after_sec=0` / `interval_sec=0` 因 `x or 默认值` 被**静默替换**成
       默认值（配了 0 却跑成 15），配置与行为不符
     · `interval_sec=-1` 被接受 → 心跳泵变成忙循环
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from vools.rhop.task.heartbeat import (STATE_ALIVE, STATE_STALE,
                                       STATE_UNKNOWN, Heartbeat)
from vools.rhop.transport.local import LocalSharedPath


@pytest.fixture()
def shared(tmp_path):
    return LocalSharedPath(str(tmp_path))


def _write(shared, name, text):
    shared.write_text(name, text)


def _ts(delta_sec):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_sec)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


# --------------------------------------------------------------------------
# 参数校验
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kwargs", [
    {"interval_sec": 0},
    {"interval_sec": -1},
    {"stale_after_sec": 0},
    {"stale_after_sec": -5},
])
def test_bad_params_rejected(shared, kwargs):
    with pytest.raises(ValueError):
        Heartbeat(shared, "x.heartbeat", **kwargs)


def test_zero_is_not_silently_replaced(shared):
    """0 曾因 `x or 默认值` 被静默替换（配 0 却跑成默认），现在必须报错。"""
    with pytest.raises(ValueError) as exc:
        Heartbeat(shared, "x.heartbeat", stale_after_sec=0)
    assert "stale_after_sec" in str(exc.value), exc.value


def test_defaults_ok(shared):
    hb = Heartbeat(shared, "x.heartbeat")
    assert hb.interval_sec == 5.0 and hb.stale_after_sec == 15.0


def test_none_falls_back_to_default(shared):
    """显式 None 仍走默认（向后兼容）。"""
    hb = Heartbeat(shared, "x.heartbeat", interval_sec=None, stale_after_sec=None)
    assert hb.interval_sec == 5.0 and hb.stale_after_sec == 15.0


def test_small_stale_for_readonly_use_still_allowed(shared):
    """只读场景用很小的 stale 阈值是合法用法，不能被 `stale >= interval` 挡掉。"""
    hb = Heartbeat(shared, "x.heartbeat", stale_after_sec=0.5)
    _write(shared, "x.heartbeat", _ts(-0.1))
    assert hb.read()["state"] == STATE_ALIVE


# --------------------------------------------------------------------------
# 未来时间戳
# --------------------------------------------------------------------------
def test_far_future_timestamp_is_unknown_not_alive(shared):
    """核心回归：时钟超前 9 小时不能被判 alive。"""
    hb = Heartbeat(shared, "x.heartbeat")
    _write(shared, "x.heartbeat", _ts(+9 * 3600))
    info = hb.read()
    assert info["state"] == STATE_UNKNOWN, info
    assert "未来" in (info.get("error") or ""), info
    assert hb.is_alive() is False


def test_small_future_skew_still_alive(shared):
    """小范围时钟偏差（容差内）仍应判 alive，不能误杀。"""
    hb = Heartbeat(shared, "x.heartbeat")
    _write(shared, "x.heartbeat", _ts(+2))
    assert hb.read()["state"] == STATE_ALIVE


def test_future_skew_tolerance_configurable(shared):
    hb = Heartbeat(shared, "x.heartbeat", max_future_skew_sec=1.0)
    _write(shared, "x.heartbeat", _ts(+30))
    assert hb.read()["state"] == STATE_UNKNOWN


# --------------------------------------------------------------------------
# 正常四态不回归
# --------------------------------------------------------------------------
def test_alive_stale_closed_missing(shared):
    hb = Heartbeat(shared, "x.heartbeat", stale_after_sec=15.0)
    assert hb.read()["state"] == "missing"

    _write(shared, "x.heartbeat", _ts(-1))
    assert hb.read()["state"] == STATE_ALIVE

    _write(shared, "x.heartbeat", _ts(-120))
    assert hb.read()["state"] == STATE_STALE

    _write(shared, "x.heartbeat", "closed")
    assert hb.read()["state"] == "closed"
    assert hb.is_closed() and not hb.is_alive()


def test_worker_id_parsed(shared):
    hb = Heartbeat(shared, "x.heartbeat", include_worker=True, worker_id="w1")
    hb.tick(force=True)
    info = hb.read()
    assert info["worker_id"] == "w1", info
