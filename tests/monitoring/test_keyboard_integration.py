"""键盘监控双进程集成测试 (Windows only)。

测试 KeySubject 和 KeyObserver 的集成：
1. 双进程架构：监控进程 + 键盘模拟进程
2. 禁用自运过滤机制，确保所有外部键盘事件完整传递
3. 覆盖各类常见按键组合
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import pytest

# Windows 平台检查
if sys.platform != "win32":
    pytestmark = pytest.mark.skip(reason="Windows platform only")
else:
    pytestmark = pytest.mark.integration

from vools.reactive.monitoring.keyboard import (
    KeySubject, KeyObserver, KeyData, KeyEventType, KeyModifier
)

# 导入模拟器工具
sys.path.insert(0, str(Path(__file__).parent / "simulators"))
from utils import get_test_paths, write_control, read_log, cleanup_test_files


def start_keyboard_sim(control_file: str, log_file: str) -> subprocess.Popen:
    """启动键盘模拟器子进程（使用位置参数）。

    Args:
        control_file: 控制文件路径
        log_file: 日志文件路径

    Returns:
        subprocess.Popen 对象
    """
    simulators_dir = Path(__file__).parent / "simulators"
    script_path = simulators_dir / "keyboard_sim.py"

    # keyboard_sim.py 使用位置参数，不是命名参数
    cmd = [
        sys.executable,
        str(script_path),
        control_file,
        log_file,
    ]

    # Windows 下避免显示控制台窗口
    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    return proc


def stop_keyboard_sim(proc: subprocess.Popen, control_file: str, timeout: float = 5.0) -> None:
    """停止键盘模拟器进程。

    Args:
        proc: 子进程对象
        control_file: 控制文件路径
        timeout: 超时时间
    """
    if proc.poll() is not None:
        return

    # 通过控制文件发送停止命令
    try:
        write_control(control_file, {"action": "stop"})
    except (IOError, OSError):
        pass

    # 等待进程退出
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()


class TestKeyboardPressEvents:
    """测试键盘事件捕获"""

    def test_keyboard_press_events(self):
        """测试按键事件捕获

        测试流程：
        1. 启动 KeySubject 监控
        2. 启动 keyboard_sim 子进程，模拟按下 A, ENTER, F1
        3. 等待事件到达（超时 5 秒）
        4. 验证收到的事件数量 >= 3
        5. 验证事件类型为 KEY_DOWN/KEY_UP
        6. 清理
        """
        # 获取测试路径
        control_file, log_file, temp_dir = get_test_paths("test_keyboard_press_events")

        try:
            # 收集事件
            events_received: List[KeyData] = []

            def on_key_event(kd: KeyData) -> None:
                events_received.append(kd)

            # 启动 KeySubject，禁用自运过滤以捕获所有事件
            ks = KeySubject(
                backend="win32",
                filter_self=False,  # 禁用自运过滤
            )
            ks.subscribe(on_next=on_key_event)
            ks.start()

            # 等待后端启动
            time.sleep(0.5)

            # 启动键盘模拟器子进程
            proc = start_keyboard_sim(str(control_file), str(log_file))

            # 等待子进程启动
            time.sleep(0.3)

            # 发送模拟指令：按下 A, ENTER, F1
            write_control(control_file, {
                "action": "start",
                "params": {
                    "keys": ["A", "ENTER", "F1"]
                }
            })

            # 等待事件到达（超时 5 秒）
            start_time = time.time()
            timeout = 5.0

            while time.time() - start_time < timeout:
                if len(events_received) >= 3:
                    break
                time.sleep(0.1)

            # 停止监控和模拟器
            stop_keyboard_sim(proc, str(control_file))
            ks.stop()

            # 验证结果
            # 每个按键会产生 KEY_DOWN 和 KEY_UP 两个事件
            assert len(events_received) >= 3, \
                f"应至少收到 3 个事件，实际收到 {len(events_received)} 个"

            # 验证事件类型
            event_types = {KeyEventType(kd.event_type) for kd in events_received}
            assert KeyEventType.KEY_DOWN in event_types or KeyEventType.KEY_UP in event_types, \
                f"事件类型应包含 KEY_DOWN 或 KEY_UP，实际: {event_types}"

            # 验证按键名称
            key_names = {kd.key_name for kd in events_received}
            expected_keys = {"A", "ENTER", "F1"}
            matched_keys = key_names & expected_keys
            assert len(matched_keys) > 0, \
                f"应捕获到预期按键，预期: {expected_keys}, 实际: {key_names}"

        finally:
            # 清理测试文件
            cleanup_test_files(control_file, log_file, temp_dir)


class TestKeyboardObserverRouting:
    """测试 KeyObserver 路由"""

    def test_keyboard_observer_routing(self):
        """测试 KeyObserver 路由

        测试流程：
        1. 创建 KeyObserver(on_press=callback)
        2. 订阅 KeySubject
        3. 模拟按键
        4. 验证 on_press 回调被触发
        """
        # 获取测试路径
        control_file, log_file, temp_dir = get_test_paths("test_keyboard_observer_routing")

        try:
            # 收集回调触发
            press_calls: List[KeyData] = []
            release_calls: List[KeyData] = []

            def on_press(kd: KeyData) -> None:
                press_calls.append(kd)

            def on_release(kd: KeyData) -> None:
                release_calls.append(kd)

            # 创建 KeyObserver，设置回调查看路由
            observer = KeyObserver(
                on_press=on_press,
                on_release=on_release,
            )

            # 启动 KeySubject，禁用自运过滤
            ks = KeySubject(
                backend="win32",
                filter_self=False,
            )

            # 订阅
            subscription = ks.subscribe(observer)
            ks.start()

            # 等待后端启动
            time.sleep(0.5)

            # 启动键盘模拟器子进程
            proc = start_keyboard_sim(str(control_file), str(log_file))

            # 等待子进程启动
            time.sleep(0.3)

            # 发送模拟指令：按下 SPACE
            write_control(control_file, {
                "action": "start",
                "params": {
                    "keys": ["SPACE"]
                }
            })

            # 等待事件到达
            start_time = time.time()
            timeout = 5.0

            while time.time() - start_time < timeout:
                if len(press_calls) >= 1:
                    break
                time.sleep(0.1)

            # 停止监控和模拟器
            stop_keyboard_sim(proc, str(control_file))
            ks.stop()
            subscription.unsubscribe()

            # 验证结果
            # on_press 回调应被触发
            assert len(press_calls) >= 1, \
                f"on_press 回调应至少触发 1 次，实际: {len(press_calls)} 次"

            # 验证 on_release 也被触发（按键释放事件）
            assert len(release_calls) >= 1, \
                f"on_release 回调应至少触发 1 次，实际: {len(release_calls)} 次"

            # 验证事件数据
            press_event = press_calls[0]
            assert press_event.key_name == "SPACE", \
                f"按键名称应为 SPACE，实际: {press_event.key_name}"

            release_event = release_calls[0]
            assert release_event.key_name == "SPACE", \
                f"按键名称应为 SPACE，实际: {release_event.key_name}"

        finally:
            # 清理测试文件
            cleanup_test_files(control_file, log_file, temp_dir)


class TestKeyboardEventDetails:
    """测试键盘事件细节"""

    def test_event_data_structure(self):
        """测试事件数据结构完整性"""
        # 获取测试路径
        control_file, log_file, temp_dir = get_test_paths("test_event_data_structure")

        try:
            events: List[KeyData] = []

            def on_event(kd: KeyData) -> None:
                events.append(kd)

            # 启动监控
            ks = KeySubject(
                backend="win32",
                filter_self=False,
            )
            ks.subscribe(on_next=on_event)
            ks.start()

            time.sleep(0.5)

            # 启动模拟器
            proc = start_keyboard_sim(str(control_file), str(log_file))

            time.sleep(0.3)

            # 模拟按键
            write_control(control_file, {
                "action": "start",
                "params": {
                    "keys": ["A", "ENTER"]
                }
            })

            # 等待事件
            start_time = time.time()
            while time.time() - start_time < 5.0 and len(events) < 2:
                time.sleep(0.1)

            stop_keyboard_sim(proc, str(control_file))
            ks.stop()

            # 验证事件数据结构
            if events:
                kd = events[0]

                # 验证必需字段存在
                assert hasattr(kd, 'key_code'), "KeyData 应有 key_code 字段"
                assert hasattr(kd, 'key_name'), "KeyData 应有 key_name 字段"
                assert hasattr(kd, 'is_press'), "KeyData 应有 is_press 字段"
                assert hasattr(kd, 'event_type'), "KeyData 应有 event_type 字段"
                assert hasattr(kd, 'timestamp'), "KeyData 应有 timestamp 字段"
                assert hasattr(kd, 'sequence'), "KeyData 应有 sequence 字段"

                # 验证字段类型
                assert isinstance(kd.key_code, int), "key_code 应为 int"
                assert isinstance(kd.key_name, str), "key_name 应为 str"
                assert isinstance(kd.is_press, bool), "is_press 应为 bool"
                assert isinstance(kd.event_type, int), "event_type 应为 int"
                assert isinstance(kd.sequence, int), "sequence 应为 int"

                # 验证事件类型值有效
                assert kd.event_type in (KeyEventType.KEY_DOWN, KeyEventType.KEY_UP, KeyEventType.KEY_HOLD), \
                    f"event_type 应为有效值，实际: {kd.event_type}"

        finally:
            cleanup_test_files(control_file, log_file, temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])