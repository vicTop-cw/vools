"""心跳测试：时间戳写入节流、四态判定、closed 停机指令、后台线程与任务解耦。"""

import datetime
import json
import os
import time

import pytest

from vools.rhop.task.errors import HeartbeatError
from vools.rhop.task.heartbeat import (
    STATE_ALIVE,
    STATE_CLOSED,
    STATE_MISSING,
    STATE_STALE,
    STATE_UNKNOWN,
    Heartbeat,
    HeartbeatPump,
)
from vools.rhop.transport.local import LocalSharedPath


def _hb(tmp_path, **kwargs):
    shared = LocalSharedPath(str(tmp_path))
    kwargs.setdefault("filename", "unit.heartbeat")
    return Heartbeat(shared, **kwargs)


class TestReadStates:
    def test_missing(self, tmp_path):
        info = _hb(tmp_path).read()
        assert info["state"] == STATE_MISSING
        assert info["ts"] is None

    def test_alive_after_tick(self, tmp_path):
        hb = _hb(tmp_path, stale_after_sec=30)
        assert hb.tick()["action"] == "written"
        info = hb.read()
        assert info["state"] == STATE_ALIVE
        assert info["ts"] and info["age_sec"] is not None
        assert hb.is_alive() is True

    def test_stale_when_clock_moves_forward(self, tmp_path):
        hb = _hb(tmp_path, stale_after_sec=5)
        hb.tick()
        future = lambda: datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60)
        stale = Heartbeat(hb.shared, hb.filename, stale_after_sec=5, now_fn=future)
        assert stale.read()["state"] == STATE_STALE
        assert stale.read()["age_sec"] > 5
        assert stale.is_alive() is False

    def test_max_age_override(self, tmp_path):
        hb = _hb(tmp_path, stale_after_sec=3600)
        hb.tick()
        assert hb.is_alive(max_age=3600) is True
        assert hb.is_alive(max_age=-1) is False

    def test_closed_token(self, tmp_path):
        hb = _hb(tmp_path)
        hb.write_closed()
        info = hb.read()
        assert info["state"] == STATE_CLOSED
        assert info["raw"] == "closed"
        assert hb.is_closed() is True
        assert hb.is_close_requested() is True

    def test_unknown_content(self, tmp_path):
        hb = _hb(tmp_path)
        hb.shared.write_text(hb.filename, "not-a-timestamp\n")
        info = hb.read()
        assert info["state"] == STATE_UNKNOWN
        assert "不是合法时间戳" in info["error"]

    def test_worker_id_in_content_when_enabled(self, tmp_path):
        hb = _hb(tmp_path, worker_id="b-1", include_worker=True)
        hb.tick()
        assert hb.read()["worker_id"] == "b-1"
        assert hb.read()["state"] == STATE_ALIVE

    def test_read_error_is_reported_not_raised(self):
        class Boom(LocalSharedPath):
            def read_text(self, filename):
                raise OSError("share offline")

        hb = Heartbeat(Boom(str(os.getcwd())), "x.heartbeat")
        assert hb.read()["state"] == STATE_UNKNOWN
        assert "share offline" in hb.read()["error"]

    def test_no_shared_raises_on_use(self):
        hb = Heartbeat(None, "x.heartbeat")
        assert hb.enabled is False
        with pytest.raises(HeartbeatError):
            hb.tick()


class TestTick:
    def test_throttled_then_forced(self, tmp_path):
        hb = _hb(tmp_path, interval_sec=100)
        assert hb.tick()["action"] == "written"
        assert hb.tick()["action"] == "skipped"
        assert hb.tick(force=True)["action"] == "written"

    def test_interval_elapsed_writes_again(self, tmp_path):
        hb = _hb(tmp_path, interval_sec=0.05)
        hb.tick()
        time.sleep(0.08)
        assert hb.tick()["action"] == "written"

    def test_tick_does_not_overwrite_closed(self, tmp_path):
        hb = _hb(tmp_path)
        hb.write_closed()
        result = hb.tick(force=True)
        assert result["action"] == "stop"
        assert hb.current_content() == "closed"

    def test_atomic_write_leaves_no_tmp(self, tmp_path):
        hb = _hb(tmp_path)
        hb.tick()
        leftovers = [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")]
        assert leftovers == []

    def test_remove(self, tmp_path):
        hb = _hb(tmp_path)
        hb.tick()
        assert hb.exists() is True
        assert hb.remove() is True
        assert hb.read()["state"] == STATE_MISSING


class TestPump:
    def test_pump_keeps_beating_while_worker_busy(self, tmp_path):
        """核心诉求：任务在跑（主线程被占住）时心跳照样每 N 秒更新。"""
        hb = _hb(tmp_path, interval_sec=0.1, stale_after_sec=5)
        pump = HeartbeatPump(hb)
        pump.start()
        try:
            first = hb.read()["raw"]
            time.sleep(0.35)          # 模拟主线程在跑长任务，完全不碰心跳
            second = hb.read()["raw"]
            assert hb.read()["state"] == STATE_ALIVE
            assert pump.close_requested is False
            assert second is not None
        finally:
            pump.stop(write_closed=False)
        assert first is not None

    def test_pump_stops_when_operator_writes_closed(self, tmp_path):
        hb = _hb(tmp_path, interval_sec=0.1)
        closed_events = []
        pump = HeartbeatPump(hb, on_close=lambda: closed_events.append(True))
        pump.start()
        try:
            hb.write_closed()                 # 运维/A 端写停机指令
            deadline = time.time() + 5
            while not pump.close_requested and time.time() < deadline:
                time.sleep(0.05)
            assert pump.close_requested is True
            assert closed_events == [True]
            # 线程不再覆盖运维写下的 closed
            time.sleep(0.2)
            assert hb.current_content() == "closed"
        finally:
            pump.stop(write_closed=False)

    def test_stop_writes_closed_by_default(self, tmp_path):
        hb = _hb(tmp_path, interval_sec=0.1)
        pump = HeartbeatPump(hb)
        pump.start()
        pump.stop()
        assert hb.read()["state"] == STATE_CLOSED

    def test_pump_is_idempotent(self, tmp_path):
        hb = _hb(tmp_path, interval_sec=1)
        pump = HeartbeatPump(hb)
        pump.start()
        pump.start()
        pump.stop(write_closed=False)
        assert pump.close_requested is False

    def test_pump_survives_transient_write_failure(self, tmp_path):
        calls = {"n": 0}

        class Flaky(LocalSharedPath):
            def write_text(self, filename, content):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise OSError("temporary share failure")
                return LocalSharedPath.write_text(self, filename, content)

        hb = Heartbeat(Flaky(str(tmp_path)), "flaky.heartbeat", interval_sec=0.05)
        pump = HeartbeatPump(hb)
        pump.start()
        try:
            time.sleep(0.3)
            assert hb.read()["state"] == STATE_ALIVE   # 失败后仍继续跳
        finally:
            pump.stop(write_closed=False)

    def test_describe(self, tmp_path):
        info = _hb(tmp_path).describe()
        assert info["file"] == "unit.heartbeat"
        assert info["interval_sec"] == 5.0
        assert info["closed_token"] == "closed"
        assert json.dumps(info)     # 可序列化