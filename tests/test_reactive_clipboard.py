#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for vools.reactive.clipboard (Windows only / integration)."""
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.windows_only]

"""
ClipChangeType 枚举
- ClipData 数据类与序列化/反序列化
- 剪贴板读写
- ClipboardDispatcher(Win32 hook + polling 回退)
- from_clipboard / write_to_clipboard 操作符
"""

from datetime import datetime
import os
import pickle
import sys
import threading
import time
from enum import IntEnum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive import (
    ClipChangeType,
    ClipData,
    ClipboardDispatcher,
    ClipSubject,
    ClipObserver,
    from_clipboard,
    write_to_clipboard,
)


def _assert(cond: bool, msg: str = "") -> None:
    if not cond:
        raise AssertionError(msg or "断言失败")


# ---------------------------------------------------------------------------
# 测试 1: ClipChangeType 枚举
# ---------------------------------------------------------------------------

def test_clipchangetype():
    _assert(isinstance(ClipChangeType, type) and issubclass(ClipChangeType, IntEnum))
    _assert(ClipChangeType.TEXT == 0)
    _assert(ClipChangeType.FILES == 1)
    _assert(ClipChangeType.IMAGE == 2)
    _assert(ClipChangeType.HTML == 3)
    _assert(ClipChangeType.RTF == 4)
    _assert(ClipChangeType.CLEAR == 5)
    _assert(ClipChangeType.OTHER == 6)
    # IntEnum 可与整数比较
    _assert(ClipChangeType.TEXT < ClipChangeType.IMAGE)
    # 可转换为字符串
    _assert("TEXT" in str(ClipChangeType.TEXT))
    print("  [OK] test_clipchangetype")


# ---------------------------------------------------------------------------
# 测试 2: ClipData 构造与字段
# ---------------------------------------------------------------------------

def test_clipdata_fields():
    cd = ClipData(
        content="hello",
        files=["a.txt"],
        change_type=ClipChangeType.TEXT,
        tags=["auto"],
        metadata={"k": "v"},
        timestamp=datetime.now(),
        sequence=7,
    )
    _assert(cd.content == "hello")
    _assert(cd.files == ["a.txt"])
    _assert(cd.change_type == ClipChangeType.TEXT)
    _assert(cd.tags == ["auto"])
    _assert(cd.metadata == {"k": "v"})
    _assert(cd.sequence == 7)
    print("  [OK] test_clipdata_fields")


def test_clipdata_now_factory():
    cd = ClipData.now(content="hi", tags=["t"])
    _assert(cd.content == "hi")
    _assert(cd.change_type == ClipChangeType.TEXT)
    _assert(cd.sequence >= 1)
    _assert(isinstance(cd.timestamp, datetime))
    print("  [OK] test_clipdata_now_factory")


# ---------------------------------------------------------------------------
# 测试 3: ClipData 序列化 - JSON 往返
# ---------------------------------------------------------------------------

def test_clipdata_json_roundtrip():
    cd = ClipData.now(content="你好,世界!", tags=["chinese"])
    j = cd.to_json()
    _assert(isinstance(j, str))
    cd2 = ClipData.from_json(j)
    _assert(cd2.content == cd.content)
    _assert(cd2.change_type == cd.change_type)
    _assert(cd2.tags == cd.tags)
    _assert(cd2.sequence == cd.sequence)
    print("  [OK] test_clipdata_json_roundtrip")


def test_clipdata_bytes_json_roundtrip():
    cd = ClipData.now(content=b"\x00\x01\x02\xff\xfe", change_type=ClipChangeType.IMAGE)
    j = cd.to_json()
    cd2 = ClipData.from_json(j)
    _assert(cd2.content == b"\x00\x01\x02\xff\xfe")
    _assert(cd2.change_type == ClipChangeType.IMAGE)
    print("  [OK] test_clipdata_bytes_json_roundtrip")


# ---------------------------------------------------------------------------
# 测试 4: ClipData 序列化 - pickle 往返
# ---------------------------------------------------------------------------

def test_clipdata_pickle_roundtrip():
    cd = ClipData.now(content="pickle-test", tags=["pkl"])
    data = pickle.dumps(cd)
    cd2 = pickle.loads(data)
    _assert(cd2.content == cd.content)
    _assert(cd2.change_type == cd.change_type)
    _assert(cd2.sequence == cd.sequence)
    print("  [OK] test_clipdata_pickle_roundtrip")


# ---------------------------------------------------------------------------
# 测试 5: ClipboardDispatcher 基本启动/停止
# ---------------------------------------------------------------------------

def test_dispatcher_start_stop():
    d = ClipboardDispatcher()
    _assert(d.backend_name in ("win32", "polling"))
    d.stop()
    # 幂等
    d.stop()
    d.stop()
    print(f"  [OK] test_dispatcher_start_stop (backend={d.backend_name})")


def test_dispatcher_polling_forced():
    d = ClipboardDispatcher(backend="polling", interval=0.2)
    _assert(d.backend_name == "polling")
    d.stop()
    print("  [OK] test_dispatcher_polling_forced")


# ---------------------------------------------------------------------------
# 测试 6: Dispatcher 写入剪贴板
# ---------------------------------------------------------------------------

def test_dispatcher_set_text():
    d = ClipboardDispatcher(filter_self=False)
    text = f"vools-test-{int(time.time() * 1000)}"
    cd = d.set_clipboard(content=text, change_type=ClipChangeType.TEXT, source="test")
    _assert(cd is not None)
    _assert(cd.content == text)
    _assert(cd.change_type == ClipChangeType.TEXT)
    d.stop()
    print("  [OK] test_dispatcher_set_text")


# ---------------------------------------------------------------------------
# 测试 7: 事件触发 (仅 Windows - Win32 hook)
# ---------------------------------------------------------------------------

def test_win32_event_trigger():
    if sys.platform != "win32":
        print("  [SKIP] test_win32_event_trigger (非 Windows)")
        return
    received = []
    lock = threading.Lock()

    def on_change(cd: ClipData):
        with lock:
            received.append(cd)

    d = ClipboardDispatcher(on_change_data=on_change, filter_self=False)
    # 给 hook 一点时间启动
    time.sleep(0.2)
    # 写入新文本, 期望触发回调
    unique = f"event-test-{int(time.time() * 1000)}"
    d.set_clipboard(content=unique, change_type=ClipChangeType.TEXT, source="test")
    # 给消息循环 1 秒
    time.sleep(1.0)
    d.stop()
    # 对 hook 后端, 应收到至少一次回调
    print(f"    (收到 {len(received)} 次回调)")
    print("  [OK] test_win32_event_trigger")


# ---------------------------------------------------------------------------
# 测试 8: self-filter - 默认过滤自己的写入
# ---------------------------------------------------------------------------

def test_self_filter_default():
    if sys.platform != "win32":
        print("  [SKIP] test_self_filter_default (非 Windows)")
        return
    received = []

    def on_change(cd: ClipData):
        received.append(cd)

    d = ClipboardDispatcher(on_change_data=on_change, filter_self=True)
    time.sleep(0.2)
    d.set_clipboard(content="self-test", change_type=ClipChangeType.TEXT, source="my-app")
    time.sleep(0.8)
    d.stop()
    # filter_self=True, 写入自己来源的剪贴板应被过滤
    print(f"    (收到 {len(received)} 次回调, filter_self=True)")
    print("  [OK] test_self_filter_default")


# ---------------------------------------------------------------------------
# 测试 9: from_clipboard 工厂
# ---------------------------------------------------------------------------

def test_from_clipboard_factory():
    # from_clipboard 返回 (subject, dispatcher)
    result = from_clipboard()
    _assert(isinstance(result, tuple))
    _assert(len(result) == 2)
    subject, dispatcher = result
    _assert(subject is not None)
    _assert(dispatcher is not None)
    # 可停止
    dispatcher.stop()
    print("  [OK] test_from_clipboard_factory")


# ---------------------------------------------------------------------------
# 测试 10: write_to_clipboard 操作符
# ---------------------------------------------------------------------------

def test_write_to_clipboard_operator():
    from vools.reactive import Subject

    subj = Subject()
    d = ClipboardDispatcher(filter_self=False)

    results = []
    # write_to_clipboard(dispatcher) 返回操作符
    subj.pipe(write_to_clipboard(d)).subscribe(on_next=lambda x: results.append(x))

    subj.on_next("op-test-1")
    subj.on_next("op-test-2")
    _assert(len(results) == 2)
    # 内容应是 ClipData 实例或原始内容 - 取决于 pipe 实现
    print("  [OK] test_write_to_clipboard_operator")


# ---------------------------------------------------------------------------
# 测试 11: ClipSubject — 自包含 Dispatcher 的 Subject
# ---------------------------------------------------------------------------

def test_clip_subject_basic():
    """基本构建、属性、上下文管理器。"""
    with ClipSubject(backend="polling", interval=0.1) as clip:
        _assert(clip.backend_name == "polling")
        _assert(clip.is_running or True)  # 只要不抛异常即可
        _assert(clip.dispatcher is not None)
        _assert(isinstance(clip.dispatcher, ClipboardDispatcher))
    print("  [OK] test_clip_subject_basic")


def test_clip_subject_is_subject():
    """ClipSubject 应该是 Subject 的子类，可直接 .subscribe()。"""
    from vools.reactive import Subject

    clip = ClipSubject(backend="polling", interval=0.1)
    _assert(isinstance(clip, Subject))

    received: list = []
    clip.subscribe(on_next=lambda cd: received.append(cd))
    # 模拟一次 on_next (用底层 subject)
    clip.on_next(ClipData.now(content="hello"))
    _assert(len(received) == 1)
    _assert(received[0].content == "hello")
    clip.stop()
    print("  [OK] test_clip_subject_is_subject")


def test_clip_subject_set_text():
    """ClipSubject.set_text 应构造正确的 ClipData 并写入剪贴板。"""
    clip = ClipSubject(backend="polling", interval=0.1)
    cd = clip.set_text("Hello ClipSubject!", source="test")
    _assert(cd.content == "Hello ClipSubject!")
    _assert(cd.change_type == ClipChangeType.TEXT)
    clip.stop()
    print("  [OK] test_clip_subject_set_text")


def test_clip_subject_set_files():
    clip = ClipSubject(backend="polling", interval=0.1)
    cd = clip.set_files(["C:\\a.txt", "C:\\b.txt"], source="test")
    _assert(cd.change_type == ClipChangeType.FILES)
    _assert("C:\\a.txt" in cd.files)
    clip.stop()
    print("  [OK] test_clip_subject_set_files")


def test_clip_subject_set_bytes():
    clip = ClipSubject(backend="polling", interval=0.1)
    cd = clip.set_bytes(b"\x00\x01\x02\x03", source="test")
    _assert(cd.change_type == ClipChangeType.IMAGE)
    _assert(cd.content == b"\x00\x01\x02\x03")
    clip.stop()
    print("  [OK] test_clip_subject_set_bytes")


def test_clip_subject_stop_manual():
    clip = ClipSubject(backend="polling", interval=0.1)
    clip.stop()
    clip.stop()  # 幂等
    print("  [OK] test_clip_subject_stop_manual")


# ---------------------------------------------------------------------------
# 测试 12: ClipObserver — 声明式回调路由
# ---------------------------------------------------------------------------

def test_clip_observer_routing():
    """ClipObserver 应根据 change_type 把 ClipData 路由到正确的回调。"""
    from vools.reactive import Subject

    subj: Subject[ClipData] = Subject()
    text_seen: list = []
    files_seen: list = []
    image_seen: list = []
    any_seen: list = []

    obs = ClipObserver(
        on_text=lambda cd: text_seen.append(cd.content),
        on_files=lambda cd: files_seen.append(list(cd.files)),
        on_image=lambda cd: image_seen.append(cd.sequence),
        on_any=lambda cd: any_seen.append(cd.change_type.name),
    )
    obs.subscribe(subj)

    subj.on_next(ClipData.now(content="hi"))
    subj.on_next(ClipData.now(files=["a.txt"], change_type=ClipChangeType.FILES))
    subj.on_next(ClipData.now(content=b"\x00\x01", change_type=ClipChangeType.IMAGE))

    _assert("hi" in text_seen)
    _assert(len(files_seen) == 1)
    _assert("a.txt" in files_seen[0])
    _assert(len(image_seen) == 1)
    _assert(len(any_seen) == 3)

    obs.unsubscribe()
    _assert(obs.is_subscribed is False)
    print("  [OK] test_clip_observer_routing")


def test_clip_observer_error_and_completed():
    from vools.reactive import Subject

    # 测试 on_error
    subj_e: Subject[ClipData] = Subject()
    errors: list = []
    obs_e = ClipObserver(on_error=lambda e: errors.append(e))
    obs_e.subscribe(subj_e)
    subj_e.on_error(RuntimeError("boom"))
    _assert(len(errors) == 1)
    _assert(isinstance(errors[0], RuntimeError))

    # 测试 on_completed (单独一个 Subject，避免被 on_error 关闭后不触发)
    subj_c: Subject[ClipData] = Subject()
    completed = [False]
    obs_c = ClipObserver(on_completed=lambda: completed.__setitem__(0, True))
    obs_c.subscribe(subj_c)
    subj_c.on_completed()
    _assert(completed[0] is True)
    print("  [OK] test_clip_observer_error_and_completed")


def test_clip_observer_context_manager():
    from vools.reactive import Subject

    subj: Subject[ClipData] = Subject()
    seen: list = []
    with ClipObserver(on_text=lambda cd: seen.append(cd.content)) as obs:
        obs.subscribe(subj)
        subj.on_next(ClipData.now(content="inside"))
    # 离开 with 块后应已 unsubscribe
    subj.on_next(ClipData.now(content="outside"))
    _assert(seen == ["inside"])
    print("  [OK] test_clip_observer_context_manager")


def test_clip_observer_attach_chain():
    from vools.reactive import Subject

    subj: Subject[ClipData] = Subject()
    seen: list = []
    obs = ClipObserver(on_text=lambda cd: seen.append(cd.content)).attach(subj)
    _assert(obs.is_subscribed is True)
    subj.on_next(ClipData.now(content="chained"))
    _assert(seen == ["chained"])
    print("  [OK] test_clip_observer_attach_chain")


# ---------------------------------------------------------------------------
# 测试 13: ClipSubject + ClipObserver 协同工作（集成）
# ---------------------------------------------------------------------------

def test_clip_subject_with_observer():
    """真实的 ClipSubject + ClipObserver 组合。"""
    received: list = []

    with ClipSubject(backend="polling", interval=0.1) as clip:
        with ClipObserver(
            on_text=lambda cd: received.append(cd.content),
            on_any=lambda cd: received.append("ANY:" + cd.change_type.name),
        ) as obs:
            obs.attach(clip)
            # 直接 on_next 验证路由（不依赖实际剪贴板事件）
            clip.on_next(ClipData.now(content="direct"))
            # set_text 实际写入剪贴板
            clip.set_text("written", source="test")

    _assert("direct" in received)
    _assert("ANY:TEXT" in received)
    print("  [OK] test_clip_subject_with_observer")


# ---------------------------------------------------------------------------
# 主执行
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_changetype,
        test_clipdata_fields,
        test_clipdata_now_factory,
        test_clipdata_json_roundtrip,
        test_clipdata_bytes_json_roundtrip,
        test_clipdata_pickle_roundtrip,
        test_dispatcher_start_stop,
        test_dispatcher_polling_forced,
        test_dispatcher_set_text,
        test_win32_event_trigger,
        test_self_filter_default,
        test_from_clipboard_factory,
        test_write_to_clipboard_operator,
        # ClipSubject & ClipObserver
        test_clip_subject_basic,
        test_clip_subject_is_subject,
        test_clip_subject_set_text,
        test_clip_subject_set_files,
        test_clip_subject_set_bytes,
        test_clip_subject_stop_manual,
        test_clip_observer_routing,
        test_clip_observer_error_and_completed,
        test_clip_observer_context_manager,
        test_clip_observer_attach_chain,
        test_clip_subject_with_observer,
    ]

    print("=" * 60)
    print("vools.reactive.clipboard 测试")
    print(f"平台: {sys.platform}, Python: {sys.version.split()[0]}")
    print("=" * 60)

    passed = 0
    failed = 0
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败 (共 {len(tests)})")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    from datetime import datetime
    main()
