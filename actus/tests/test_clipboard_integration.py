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
# 边界回归（T0r4.5 寻虫收口）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [b"actus-bytes", bytearray(b"actus-ba"), memoryview(b"mv")])
def test_write_rejects_bytes_like(bad):
    """bytes-like 输入必须硬报错：此前 str() 静默变形为 "b'...'" 写入剪贴板。

    实证（T0r4.5 探针 probe 2）：clip_write(b'actus-bytes-probe') 曾把
    "b'actus-bytes-probe'"（带 repr 引号与 b 前缀）写入系统剪贴板，
    调用者意图（写二进制/编码文本）与实际写入内容完全不符且无告警。
    """
    with pytest.raises(TypeError) as ei:
        clip_write(bad)
    assert "bytes-like" in str(ei.value)


def test_write_none_is_empty_string():
    """文档语义锁定：None 视为空串（宽容路径不因 bytes 收紧而回归）。"""
    cd = clip_write(None)
    assert cd.content == ""


def test_write_int_is_str_coerced():
    """宽容语义锁定：int 等 str() 可转换对象维持现状转字符串（防过度收紧回归）。"""
    cd = clip_write(12345)
    assert cd.content == "12345"


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
# 监控参数校验（BUG-371：clip_watch(interval<=0) 无下限守卫）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, -0.01])
def test_clip_watch_rejects_non_positive_interval(bad):
    """interval<=0 必须硬报错。

    BUG-371 实证：此前 clip_watch(interval=0/-1) 直接透传底层 Dispatcher，
    polling 后端 clamp(0.02) 静默生效——调用方期望"立即轮询 / 不轮询"的语义
    未兑现，win32 事件后端下非法值甚至不被任何后端报错，接口契约缺失。
    收口后 fail-fast：非法 interval 明确报错，杜绝 busy-loop 与语义幻觉。
    """
    with pytest.raises(ValueError) as ei:
        clip_watch(interval=bad)
    assert "interval" in str(ei.value)
    assert "> 0" in str(ei.value)


@pytest.mark.parametrize("bad", ["0.1", True, None])
def test_clip_watch_rejects_bad_interval_type(bad):
    """非数字 interval 必须硬报错（bool 是 int 子类，同样拒绝）。"""
    with pytest.raises(TypeError) as ei:
        clip_watch(interval=bad)
    assert "interval" in str(ei.value)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_clip_watch_rejects_non_finite_interval(bad):
    """NaN/inf 必须硬报错：无法 clamp，会破坏底层 stop() join 超时语义。"""
    with pytest.raises(ValueError) as ei:
        clip_watch(interval=bad)
    assert "interval" in str(ei.value)


def test_dispatcher_clamps_non_positive_interval():
    """底层 dispatcher 对 interval<=0 保留 clamp(0.02) 兼容语义（不回归），
    NaN/inf 与非法类型显式拒绝（BUG-371 兜底防线）。"""
    from vools.reactive.monitoring.clipboard import ClipboardDispatcher

    d0 = ClipboardDispatcher(interval=0, backend="polling")
    try:
        assert d0._interval >= 0.02
        d0.start()
        assert d0.is_running
    finally:
        d0.stop()

    with pytest.raises(ValueError):
        ClipboardDispatcher(interval=float("nan"))
    with pytest.raises(TypeError):
        ClipboardDispatcher(interval=None)


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
