"""keyboard_mouse 模块单元测试。"""
import pickle
import sys

import pytest

from vools.reactive.monitoring.keyboard import (
    KeyEventType,
    KeyModifier,
    KeyData,
    KeyboardDispatcher,
    KeySubject,
    KeyObserver,
    from_keyboard,
    write_to_keyboard,
)

from vools.reactive.monitoring.mouse import (
    MouseEventType,
    MouseData,
    MouseDispatcher,
    MouseSubject,
    MouseObserver,
    from_mouse,
    write_to_mouse,
)


# ============================================================================
# TR-1.1: 枚举值测试
# ============================================================================

def test_key_event_type_values():
    assert int(KeyEventType.KEY_DOWN) == 0
    assert int(KeyEventType.KEY_UP) == 1
    assert int(KeyEventType.KEY_HOLD) == 2
    assert KeyEventType.KEY_DOWN.name == "KEY_DOWN"
    assert len(list(KeyEventType)) == 3


def test_mouse_event_type_values():
    assert int(MouseEventType.MOVE) == 0
    assert int(MouseEventType.LEFT_DOWN) == 1
    assert int(MouseEventType.LEFT_UP) == 2
    assert int(MouseEventType.RIGHT_DOWN) == 3
    assert int(MouseEventType.RIGHT_UP) == 4
    assert int(MouseEventType.MIDDLE_DOWN) == 5
    assert int(MouseEventType.MIDDLE_UP) == 6
    assert int(MouseEventType.SCROLL) == 7
    assert int(MouseEventType.DRAG) == 8


def test_key_modifier_values():
    assert KeyModifier.NONE == 0
    assert KeyModifier.SHIFT == 1
    assert KeyModifier.CTRL == 2
    assert KeyModifier.ALT == 4
    assert KeyModifier.WIN == 8
    assert KeyModifier.CAPSLOCK == 16
    assert KeyModifier.CTRL | KeyModifier.SHIFT == 3
    assert str(KeyModifier.SHIFT | KeyModifier.CTRL) == "SHIFT+CTRL"


# ============================================================================
# TR-1.2 & TR-1.3: KeyData 测试
# ============================================================================

def test_key_data_auto_event_type():
    kd = KeyData(key_code=65, is_press=True)
    assert kd.event_type == KeyEventType.KEY_DOWN
    kd2 = KeyData(key_code=65, is_press=False)
    assert kd2.event_type == KeyEventType.KEY_UP


def test_key_data_auto_key_name():
    kd = KeyData(key_code=65, is_press=True)
    assert kd.key_name == "A"


def test_key_data_now_factory():
    kd = KeyData.now(key_code=65, is_press=True)
    assert kd.timestamp is not None
    assert kd.sequence > 0
    assert kd.event_type == KeyEventType.KEY_DOWN


def test_key_data_json_roundtrip():
    kd = KeyData.now(key_code=65, is_press=True)
    j = kd.to_json()
    kd2 = KeyData.from_json(j)
    assert kd2.key_code == kd.key_code
    assert kd2.is_press == kd.is_press
    assert kd2.event_type == kd.event_type
    assert kd2.sequence == kd.sequence


def test_key_data_pickle_roundtrip():
    kd = KeyData.now(key_code=65, is_press=True)
    pk = kd.to_pickle()
    kd2 = KeyData.from_pickle(pk)
    assert kd2.key_code == kd.key_code


# ============================================================================
# TR-1.4: MouseData 测试
# ============================================================================

def test_mouse_data_fields():
    md = MouseData.now(x=100, y=200, event_type=MouseEventType.MOVE)
    assert md.x == 100
    assert md.y == 200
    assert md.event_type == MouseEventType.MOVE
    assert md.sequence > 0


def test_mouse_data_button_auto():
    md_left = MouseData.now(x=0, y=0, event_type=MouseEventType.LEFT_DOWN)
    assert md_left.button == "left"
    md_right = MouseData.now(x=0, y=0, event_type=MouseEventType.RIGHT_DOWN)
    assert md_right.button == "right"
    md_middle = MouseData.now(x=0, y=0, event_type=MouseEventType.MIDDLE_DOWN)
    assert md_middle.button == "middle"


def test_mouse_data_json_roundtrip():
    md = MouseData.now(x=100, y=200, event_type=MouseEventType.MOVE)
    j = md.to_json()
    md2 = MouseData.from_json(j)
    assert md2.x == md.x
    assert md2.y == md.y
    assert md2.event_type == md.event_type


# ============================================================================
# TR-1.5: 键码映射测试
# ============================================================================

def test_vk_code_to_name():
    from vools.reactive.monitoring.keyboard import _vk_code_to_name

    assert _vk_code_to_name(0x41) == "A"
    assert _vk_code_to_name(0x0D) == "ENTER"
    assert _vk_code_to_name(0x70) == "F1"
    assert _vk_code_to_name(0x20) == "SPACE"
    assert _vk_code_to_name(0xA2) == "LCTRL"  # VK_LCTRL


def test_name_to_vk_code():
    from vools.reactive.monitoring.keyboard import _name_to_vk_code

    assert _name_to_vk_code("A") == 0x41
    assert _name_to_vk_code("ENTER") == 0x0D
    assert _name_to_vk_code("F1") == 0x70
    assert _name_to_vk_code("SPACE") == 0x20
    assert _name_to_vk_code("ESCAPE") == 0x1B
    assert _name_to_vk_code("unknown") == 0


# ============================================================================
# TR-5: KeyboardDispatcher 测试
# ============================================================================

def test_keyboard_dispatcher_backend_polling():
    kd = KeyboardDispatcher(backend="polling")
    assert kd.backend_name == "polling"
    assert not kd.is_running
    assert kd.dispatch_count == 0
    assert kd.error_count == 0


def test_keyboard_dispatcher_start_stop():
    kd = KeyboardDispatcher(backend="polling")
    kd.start()
    assert kd.is_running
    kd.stop()
    assert not kd.is_running


def test_keyboard_dispatcher_context_manager():
    with KeyboardDispatcher(backend="polling") as kd:
        assert kd.is_running
    assert not kd.is_running


def test_keyboard_dispatcher_self_filter():
    kd = KeyboardDispatcher(backend="polling", filter_self=True)
    kd.start()
    kd._register_self_signature(KeyData.now(key_code=65, is_press=True))
    kd._dispatch_once(KeyData.now(key_code=65, is_press=True))
    assert kd.self_filtered_count == 1
    assert kd.dispatch_count == 0
    kd.stop()


def test_keyboard_dispatcher_subject():
    kd = KeyboardDispatcher(backend="polling")
    assert hasattr(kd, "subject")
    assert hasattr(kd.subject, "subscribe")


# ============================================================================
# TR-5: MouseDispatcher 测试
# ============================================================================

def test_mouse_dispatcher_backend_polling():
    ms = MouseDispatcher(backend="polling")
    assert ms.backend_name == "polling"
    assert not ms.is_running


def test_mouse_dispatcher_start_stop():
    ms = MouseDispatcher(backend="polling")
    ms.start()
    assert ms.is_running
    ms.stop()
    assert not ms.is_running


def test_mouse_dispatcher_context_manager():
    with MouseDispatcher(backend="polling") as ms:
        assert ms.is_running
    assert not ms.is_running


def test_mouse_dispatcher_self_filter():
    ms = MouseDispatcher(backend="polling", filter_self=True)
    ms.start()
    ms._register_self_signature(
        MouseData.now(x=100, y=200, event_type=MouseEventType.MOVE)
    )
    ms._dispatch_once(
        MouseData.now(x=100, y=200, event_type=MouseEventType.MOVE)
    )
    assert ms.self_filtered_count == 1
    assert ms.dispatch_count == 0
    ms.stop()


# ============================================================================
# TR-6: KeySubject 测试
# ============================================================================

def test_key_subject_is_subject():
    from vools.reactive.core.subject import Subject

    ks = KeySubject(backend="polling")
    # KeySubject has a Subject (composition), but is not a Subject subclass
    assert hasattr(ks, "subject")
    assert isinstance(ks.subject, Subject)
    # subscribe method delegates to internal subject
    received = []
    ks.subscribe(on_next=lambda kd: received.append(kd))
    ks.subject.on_next(KeyData.now(key_code=65, is_press=True))
    assert len(received) == 1


def test_key_subject_context_manager():
    with KeySubject(backend="polling") as ks:
        assert ks.is_running
    assert not ks.is_running


def test_key_subject_dispatcher():
    ks = KeySubject(backend="polling")
    assert hasattr(ks, "dispatcher")
    assert isinstance(ks.dispatcher, KeyboardDispatcher)
    assert ks.backend_name == "polling"


def test_key_subject_pipe():
    ks = KeySubject(backend="polling")
    ks.start()
    results = []
    ks.pipe(lambda x: x).subscribe(on_next=lambda x: results.append(x))
    ks.stop()
    # pipe 可调用不抛异常


# ============================================================================
# TR-6: MouseSubject 测试
# ============================================================================

def test_mouse_subject_is_subject():
    from vools.reactive.core.subject import Subject

    ms = MouseSubject(backend="polling")
    # MouseSubject has a Subject (composition), but is not a Subject subclass
    assert hasattr(ms, "subject")
    assert isinstance(ms.subject, Subject)
    received = []
    ms.subscribe(on_next=lambda md: received.append(md))
    ms.subject.on_next(MouseData.now(x=0, y=0, event_type=MouseEventType.MOVE))
    assert len(received) == 1


def test_mouse_subject_context_manager():
    with MouseSubject(backend="polling") as ms:
        assert ms.is_running
    assert not ms.is_running


# ============================================================================
# TR-7: KeyObserver 测试
# ============================================================================

def test_key_observer_on_press_routing():
    events = []
    ko = KeyObserver(
        on_press=lambda kd: events.append("press"),
        on_release=lambda kd: events.append("release"),
    )
    ko._on_next(KeyData(key_code=65, is_press=True))
    assert events == ["press"]
    ko._on_next(KeyData(key_code=65, is_press=False))
    assert events == ["press", "release"]


def test_key_observer_on_any():
    events = []
    ko = KeyObserver(on_any=lambda kd: events.append("any"))
    ko._on_next(KeyData(key_code=65, is_press=True))
    assert "any" in events


def test_key_observer_attach_chain():
    ks = KeySubject(backend="polling")
    ks.start()
    events = []
    with KeyObserver(on_press=lambda kd: events.append("press")).attach(ks):
        ks.subject.on_next(KeyData(key_code=65, is_press=True))
    assert events == ["press"]
    ks.stop()


# ============================================================================
# TR-7: MouseObserver 测试
# ============================================================================

def test_mouse_observer_on_move_routing():
    events = []
    mo = MouseObserver(
        on_move=lambda md: events.append("move"),
        on_click=lambda md: events.append("click"),
        on_scroll=lambda md: events.append("scroll"),
    )
    mo._on_next(
        MouseData.now(x=0, y=0, event_type=MouseEventType.MOVE)
    )
    assert "move" in events
    mo._on_next(
        MouseData.now(x=0, y=0, event_type=MouseEventType.LEFT_DOWN)
    )
    assert "click" in events
    mo._on_next(
        MouseData.now(x=0, y=0, event_type=MouseEventType.SCROLL, delta=120)
    )
    assert "scroll" in events


def test_mouse_observer_on_any():
    events = []
    mo = MouseObserver(on_any=lambda md: events.append("any"))
    mo._on_next(
        MouseData.now(x=0, y=0, event_type=MouseEventType.MOVE)
    )
    assert "any" in events


# ============================================================================
# TR-8: 工厂函数测试
# ============================================================================

def test_from_keyboard_factory():
    obs, disp = from_keyboard(backend="polling", auto_start=False)
    assert hasattr(obs, "subscribe")
    assert isinstance(disp, KeyboardDispatcher)
    assert disp.backend_name == "polling"
    assert not disp.is_running


def test_from_mouse_factory():
    obs, disp = from_mouse(backend="polling", auto_start=False)
    assert hasattr(obs, "subscribe")
    assert isinstance(disp, MouseDispatcher)
    assert disp.backend_name == "polling"


def test_from_keyboard_auto_start():
    obs, disp = from_keyboard(backend="polling", auto_start=True)
    assert disp.is_running
    disp.stop()
    assert not disp.is_running


# ============================================================================
# TR-9: write 操作符测试
# ============================================================================

def test_write_to_keyboard_operator():
    obs, disp = from_keyboard(backend="polling", auto_start=False)
    op = write_to_keyboard(disp)
    assert callable(op)
    # 不抛异常
    result = op(obs)
    assert hasattr(result, "subscribe")


def test_write_to_mouse_operator():
    obs, disp = from_mouse(backend="polling", auto_start=False)
    op = write_to_mouse(disp)
    assert callable(op)
    result = op(obs)
    assert hasattr(result, "subscribe")


# ============================================================================
# TR-9: __init__ 导出测试
# ============================================================================

def test_reactive_exports_keyboard_symbols():
    from vools.reactive import (
        KeyEventType,
        MouseEventType,
        KeyModifier,
        KeyData,
        MouseData,
        KeyboardDispatcher,
        MouseDispatcher,
        KeySubject,
        MouseSubject,
        KeyObserver,
        MouseObserver,
        from_keyboard,
        from_mouse,
        write_to_keyboard,
        write_to_mouse,
    )
    # 均不为 None
    assert KeyEventType is not None
    assert MouseEventType is not None
    assert KeyModifier is not None
    assert KeyData is not None
    assert MouseData is not None
    assert KeyboardDispatcher is not None
    assert MouseDispatcher is not None
    assert KeySubject is not None
    assert MouseSubject is not None
    assert KeyObserver is not None
    assert MouseObserver is not None
    assert from_keyboard is not None
    assert from_mouse is not None
    assert write_to_keyboard is not None
    assert write_to_mouse is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
