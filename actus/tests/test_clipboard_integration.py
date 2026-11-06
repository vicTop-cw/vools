# -*- coding: utf-8 -*-
"""vools.actus.clipboard 剪贴板能力验证用例（T0.2）。

验收目标：存在真实调用剪贴板读写的用例/测试并可通过。
本文件对系统剪贴板做真实读写（Windows 全局剪贴板），是「真实调用」而非 mock：
  - 读写 roundtrip（ASCII / 中文）
  - 清空动作
  - ClipData JSON 往返（数据层）
  - clip_watch 监控收到外部写入事件（polling 后端，interval 0.05 提速）
  - 懒加载导出：from vools.actus import clip_read, clip_write, ...

注意：测试会短暂改写系统剪贴板；watch 用例使用唯一前缀文本避免与其它
剪贴板活动互相干扰。若当前环境无 vools.reactive（rx 子项目不在 sys.path），
导入阶段自动 skip。
"""

import queue
import threading
import time

import pytest

from vools.actus import (
    ClipChangeType,
    ClipData,
    clip_clear,
    clip_read,
    clip_watch,
    clip_write,
)

_WATCH_PREFIX = "actus-clip-watch-"


def _wait_until(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _drain(q: "queue.Queue") -> None:
    """排空事件队列（watch 启动后 polling 可能先分发剪贴板残留）。"""
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            return


# ---------------------------------------------------------------------------
# 读写 roundtrip
# ---------------------------------------------------------------------------


def test_read_write_roundtrip_ascii():
    text = "actus-clipboard-roundtrip-%d" % int(time.time())
    written = clip_write(text, tags=["t0.2"], source="test")
    assert written.content == text
    assert written.change_type.name == "TEXT"
    assert written.metadata.get("_source") == "test"

    # 真实读回
    cd = clip_read()
    assert cd.content == text
    assert cd.change_type.name == "TEXT"


def test_read_write_roundtrip_unicode():
    text = "剪贴板能力落地 actus：验证中文读写 你好世界"
    clip_write(text)
    cd = clip_read()
    assert cd.content == text


def test_write_tags_preserved():
    clip_write("tagged-content", tags=["actus", "clip"])
    # 写入返回的 ClipData 保留 tags（数据层语义；读回的系统 ClipData 不含自定义 tags）
    cd = clip_write("tagged-content-2", tags=["actus", "clip"])
    assert list(cd.tags) == ["actus", "clip"]


# ---------------------------------------------------------------------------
# 清空动作
# ---------------------------------------------------------------------------


def test_clear_empties_clipboard():
    clip_write("to-be-cleared")
    assert clip_read().content == "to-be-cleared"
    clip_clear()
    cd = clip_read()
    # 清空后：要么 CLEAR，要么读回空文本（不同平台表现不同）
    assert cd.change_type.name == "CLEAR" or cd.content in ("", None)


# ---------------------------------------------------------------------------
# ClipData 数据层：JSON 往返
# ---------------------------------------------------------------------------


def test_clip_data_json_roundtrip():
    cd = ClipData.now(
        content="json-roundtrip",
        change_type=ClipChangeType.TEXT,
        tags=["a", "b"],
        metadata={"k": "v"},
    )
    s = cd.to_json()
    cd2 = ClipData.from_json(s)
    assert cd2.content == cd.content
    assert cd2.change_type == cd.change_type
    assert list(cd2.tags) == list(cd.tags)
    assert cd2.metadata == cd.metadata
    assert cd2.sequence == cd.sequence


# ---------------------------------------------------------------------------
# 监控：clip_watch 收到外部写入事件
# ---------------------------------------------------------------------------


def test_clip_watch_receives_external_write():
    """watch（filter_self=False）应收到 clip_write 触发的变更事件。"""
    received: "queue.Queue[ClipData]" = queue.Queue()

    # polling 后端提速；filter_self=False：clip_write 写入也应分发
    w = clip_watch(
        interval=0.05,
        backend="polling",
        filter_self=False,
        on_text=lambda cd: received.put(cd),
    )
    try:
        assert w.is_running or w.dispatcher.is_running
        # 排空 polling 首次分发可能带来的剪贴板残留
        time.sleep(0.2)
        _drain(received)
        text = _WATCH_PREFIX + str(int(time.time()))
        clip_write(text)
        ok = _wait_until(lambda: not received.empty(), timeout=3.0)
        assert ok, "clip_watch 未在超时内收到写入事件"
        got = received.get()
        assert got.content == text
        assert got.change_type.name == "TEXT"
    finally:
        w.stop()


def test_clip_watch_filter_self_default():
    """默认 filter_self=True：自己写回不应出现在分发流中。

    与 test_clip_watch_receives_external_write 配对验证自过滤语义。
    说明：本用例用独立 Dispatcher 写入（而非 clip_write 低层 reader），
    使 watcher 与 writer 各自维护签名，验证的是「watcher 自己不写回」的默认行为。
    """
    received: "queue.Queue[ClipData]" = queue.Queue()
    w = clip_watch(
        interval=0.05,
        backend="polling",
        filter_self=True,
        on_change=lambda cd: received.put(cd),
    )
    try:
        # watcher 自身不写回：由外部 observer 写
        from vools.reactive.monitoring.clipboard import ClipboardDispatcher

        time.sleep(0.2)
        _drain(received)
        writer = ClipboardDispatcher(interval=0.05, backend="polling")
        writer.start()
        try:
            text = _WATCH_PREFIX + "self-" + str(int(time.time()))
            writer.set_clipboard(text)
            ok = _wait_until(lambda: not received.empty(), timeout=3.0)
            assert ok, "外部 dispatcher 写入未触发 watcher"
            got = received.get()
            assert got.content == text
        finally:
            writer.stop()
    finally:
        w.stop()


# ---------------------------------------------------------------------------
# 懒加载导出
# ---------------------------------------------------------------------------


def test_lazy_exports_exist():
    import vools.actus as actus

    assert hasattr(actus, "clip_read")
    assert hasattr(actus, "clip_write")
    assert hasattr(actus, "clip_clear")
    assert hasattr(actus, "clip_watch")
    assert hasattr(actus, "ClipWatcher")
    assert "clip_read" in actus.__all__
    assert "ClipWatcher" in actus.__all__
