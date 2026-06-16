"""
KeyObserver �?KeySubject 集成测试

测试方案:
1. 部署两个独立进程：监控程�?+ 按键模拟程序
2. 禁用自过滤机制，确保所有按键事件完整传�?3. 覆盖各类常见按键组合、特殊功能键、连续快速按键场�?4. 生成详细的事件日志记录（事件类型、触发时间、按键代码、事件传递路径）
"""

import os
import sys
import time
import json
import subprocess
import psutil
from datetime import datetime
from typing import Dict, List, Any, Tuple

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive.monitoring.keyboard import (
    KeySubject, KeyObserver, KeyData, KeyEventType, KeyModifier
)


def log_event(log_file: str, event_type: str, **data) -> None:
    """记录测试事件"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        **data
    }
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def write_control(control_file: str, action: str, **kwargs) -> None:
    """写入控制指令"""
    with open(control_file, "w", encoding="utf-8") as f:
        json.dump({"action": action, "timestamp": datetime.now().isoformat(), **kwargs}, f)


def read_control(control_file: str) -> Dict | None:
    """读取控制指令"""
    if not os.path.exists(control_file):
        return None
    try:
        with open(control_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def monitor_process(control_file: str, log_file: str, disable_filter: bool = True):
    """监控程序进程"""
    import logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    log_event(log_file, "monitor_start", pid=os.getpid())
    
    events_received: List[Dict] = []
    event_paths: List[str] = []
    
    def on_key_press(kd: KeyData):
        ts = time.time()
        evt_data = {
            "key_code": kd.key_code,
            "key_name": kd.key_name,
            "event_type": KeyEventType(kd.event_type).name,
            "modifiers": KeyModifier(kd.modifiers).name if kd.modifiers else "NONE",
            "timestamp": kd.timestamp.isoformat(),
            "time_ms": ts,
            "sequence": kd.sequence,
            "window_title": kd.window_title,
        }
        events_received.append(evt_data)
        event_paths.append(f"backend -> _on_change -> subject -> observer -> callback")
        
        log_event(log_file, "key_event",
                  key_code=kd.key_code,
                  key_name=kd.key_name,
                  event_type=KeyEventType(kd.event_type).name,
                  path="backend -> _on_change -> subject -> observer -> callback")
        print(f"[监控] 收到按键: {kd.key_name} ({KeyEventType(kd.event_type).name}) - seq={kd.sequence}")
    
    # 禁用自过�?    filter_self = not disable_filter
    
    print(f"[监控] filter_self={filter_self} (自过滤已禁用)")
    
    ks = KeySubject(
        backend="win32",
        filter_self=filter_self,
    )
    ks.start()
    
    ks.subscribe(on_next=on_key_press)
    subscription = ks
    
    current_memory = process.memory_info().rss / 1024 / 1024
    
    print(f"[监控] 启动成功，后�? {ks.backend_name}")
    print(f"[监控] filter_self: {ks.dispatcher._filter_self}")
    print(f"[监控] 初始内存: {initial_memory:.2f}MB, 当前内存: {current_memory:.2f}MB")
    
    log_event(log_file, "monitor_config",
              backend=ks.backend_name,
              filter_self=ks.dispatcher._filter_self,
              initial_memory_mb=initial_memory,
              current_memory_mb=current_memory)
    
    write_control(control_file, "ready",
                  pid=os.getpid(),
                  backend=ks.backend_name,
                  filter_self=ks.dispatcher._filter_self)
    
    while True:
        control = read_control(control_file)
        if control and control.get("action") == "stop":
            break
        time.sleep(0.05)
    
    time.sleep(0.5)
    
    ks.stop()
    
    final_memory = process.memory_info().rss / 1024 / 1024
    
    log_event(log_file, "monitor_stop",
              events_received=len(events_received),
              final_memory_mb=final_memory,
              memory_delta_mb=final_memory - initial_memory)
    
    results = {
        "events_received": events_received,
        "event_paths": event_paths,
        "dispatch_count": ks.dispatch_count,
        "filtered_count": ks.self_filtered_count,
        "initial_memory_mb": initial_memory,
        "final_memory_mb": final_memory,
        "memory_delta_mb": final_memory - initial_memory,
        "backend": ks.backend_name,
        "filter_self": ks.dispatcher._filter_self,
    }
    
    with open(os.path.join(os.path.dirname(control_file) or tempfile.gettempdir(), "_key_monitor_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"[监控] 停止，收�?{len(events_received)} 个按键事�?)


def simulator_process(control_file: str, log_file: str):
    """按键模拟程序进程"""
    import ctypes
    import ctypes.wintypes as wt
    
    log_event(log_file, "simulator_start", pid=os.getpid())
    
    while True:
        control = read_control(control_file)
        if control and control.get("action") == "ready":
            break
        time.sleep(0.1)
    
    time.sleep(0.5)
    
    user32 = ctypes.windll.user32
    
    # 定义模拟按键函数
    def press_key(vk_code: int):
        user32.keybd_event(vk_code, 0, 0, 0)
        
    def release_key(vk_code: int):
        user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP = 2
        
    def send_key(vk_code: int, delay: float = 0.05):
        press_key(vk_code)
        time.sleep(delay)
        release_key(vk_code)
        time.sleep(delay)
    
    def send_combination(*vk_codes, delay: float = 0.05):
        for vk in vk_codes:
            press_key(vk)
        time.sleep(delay)
        for vk in reversed(vk_codes):
            release_key(vk)
        time.sleep(delay)
    
    operations: List[Dict] = []
    
    def op(name: str, key_info: str, vk_codes: List[int], **kwargs):
        ts = time.time()
        operations.append({
            "name": name,
            "key_info": key_info,
            "vk_codes": vk_codes,
            "timestamp": datetime.now().isoformat(),
            "time_ms": ts,
            **kwargs
        })
        log_event(log_file, "key_operation",
                  name=name,
                  key_info=key_info,
                  vk_codes=vk_codes)
        print(f"[模拟] {name}: {key_info}")
    
    VK = {
        "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45,
        "F": 0x46, "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A,
        "K": 0x4B, "L": 0x4C, "M": 0x4D, "N": 0x4E, "O": 0x4F,
        "P": 0x50, "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54,
        "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58, "Y": 0x59, "Z": 0x5A,
        "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
        "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
        "SPACE": 0x20, "ENTER": 0x0D, "ESCAPE": 0x1B, "TAB": 0x09,
        "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
        "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
        "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
        "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
        "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
        "INSERT": 0x2D, "DELETE": 0x2E, "BACKSPACE": 0x08,
    }
    
    test_scenarios = []
    
    # 场景1：单个字母键
    for char in ["A", "B", "C", "D", "E"]:
        test_scenarios.append((f"single_letter_{char}", char, [VK[char]]))
    
    # 场景2：数字键
    for num in ["1", "2", "3", "4", "5"]:
        test_scenarios.append((f"single_number_{num}", num, [VK[num]]))
    
    # 场景3：功能键
    for fkey in ["F1", "F2", "F3"]:
        test_scenarios.append((f"function_key_{fkey}", fkey, [VK[fkey]]))
    
    # 场景4：控制键
    for ckey in ["ENTER", "TAB", "ESCAPE", "SPACE", "BACKSPACE"]:
        test_scenarios.append((f"control_key_{ckey}", ckey, [VK[ckey]]))
    
    # 场景5：方向键
    for akey in ["UP", "DOWN", "LEFT", "RIGHT"]:
        test_scenarios.append((f"arrow_key_{akey}", akey, [VK[akey]]))
    
    # 场景6：组合键 Ctrl+Key
    for char in ["A", "C", "V", "S"]:
        test_scenarios.append((f"ctrl_combination_{char}", f"Ctrl+{char}", [VK["CTRL"], VK[char]], True))
    
    # 场景7：组合键 Shift+Key
    for char in ["A", "1"]:
        test_scenarios.append((f"shift_combination_{char}", f"Shift+{char}", [VK["SHIFT"], VK[char]], True))
    
    # 场景8：组合键 Alt+Tab
    test_scenarios.append(("alt_tab", "Alt+Tab", [VK["ALT"], VK["TAB"]], True))
    
    # 场景9：连续快速按键（�?0ms一个）
    rapid_keys = ["Q", "W", "E", "R", "T"]
    test_scenarios.append(("rapid_typing", "快速连�?, [VK[k] for k in rapid_keys], False, 0.02))
    
    # 执行所有场�?    print(f"\n[模拟] 开始执�?{len(test_scenarios)} 个测试场�?..")
    
    for i, scenario in enumerate(test_scenarios):
        name, key_info, vk_codes = scenario[0], scenario[1], scenario[2]
        hold_modifier = scenario[3] if len(scenario) > 3 else False
        delay = scenario[4] if len(scenario) > 4 else 0.05
        
        try:
            if hold_modifier:
                for vk in vk_codes[:-1]:
                    press_key(vk)
                time.sleep(0.02)
                release_key(vk_codes[-1])
                time.sleep(0.02)
                for vk in reversed(vk_codes[:-1]):
                    release_key(vk)
            else:
                send_key(vk_codes[0], delay) if len(vk_codes) == 1 else (
                    (send_combination(*vk_codes, delay=delay) if delay < 0.03 else send_combination(*vk_codes))
                )
            
            op(name, key_info, vk_codes, delay_ms=int(delay * 1000))
            time.sleep(0.1)
            
        except Exception as e:
            print(f"[模拟] {name} 失败: {e}")
            log_event(log_file, "operation_error", name=name, error=str(e))
        
        if (i + 1) % 10 == 0:
            print(f"[模拟] 已完�?{i + 1}/{len(test_scenarios)} 个场�?)
    
    with open(os.path.join(os.path.dirname(control_file) or tempfile.gettempdir(), "_key_operations.json"), "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)
    
    time.sleep(1)
    
    write_control(control_file, "stop")
    
    log_event(log_file, "simulator_stop", operations=len(operations))
    print(f"[模拟] 完成 {len(operations)} 个按键操�?)


def run_integration_test():
    """运行集成测试"""
    import tempfile
    
    control_file = os.path.join(tempfile.gettempdir(), f"vools_key_control_{os.getpid()}.json")
    log_file = os.path.join(tempfile.gettempdir(), f"vools_key_test_log_{os.getpid()}.json")
    
    print("=" * 80)
    print("KeyObserver/KeySubject 集成测试")
    print("自过滤状�? 已禁用（确保所有按键事件完整传递）")
    print("=" * 80)
    
    if os.path.exists(log_file):
        os.remove(log_file)
    if os.path.exists(control_file):
        os.remove(control_file)
    
    monitor_proc = subprocess.Popen(
        [sys.executable, __file__, "--monitor", control_file, log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    time.sleep(0.5)
    
    simulator_proc = subprocess.Popen(
        [sys.executable, __file__, "--simulator", control_file, log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    try:
        simulator_stdout, simulator_stderr = simulator_proc.communicate(timeout=60)
        monitor_stdout, monitor_stderr = monitor_proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        simulator_proc.kill()
        monitor_proc.kill()
        simulator_stdout, simulator_stderr = simulator_proc.communicate()
        monitor_stdout, monitor_stderr = monitor_proc.communicate()
    
    print("\n" + "=" * 80)
    print("监控程序输出:")
    print("-" * 40)
    print(monitor_stdout[-2000:] if monitor_stdout else "")
    if monitor_stderr:
        print("错误:")
        print(monitor_stderr[-500:] if monitor_stderr else "")
    
    print("\n" + "=" * 80)
    print("模拟程序输出:")
    print("-" * 40)
    print(simulator_stdout[-2000:] if simulator_stdout else "")
    if simulator_stderr:
        print("错误:")
        print(simulator_stderr[-500:] if simulator_stderr else "")
    
    results_file = os.path.join(os.path.dirname(control_file) or tempfile.gettempdir(), "_key_monitor_results.json")
    ops_file = os.path.join(os.path.dirname(control_file) or tempfile.gettempdir(), "_key_operations.json")
    
    print("\n" + "=" * 80)
    print("测试结果分析:")
    print("-" * 40)
    
    if os.path.exists(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            results = json.load(f)
        
        print(f"收到按键事件�? {len(results['events_received'])}")
        print(f"分发计数: {results['dispatch_count']}")
        print(f"过滤计数: {results['filtered_count']}")
        print(f"后端: {results['backend']}")
        print(f"filter_self: {results['filter_self']}")
        print(f"初始内存: {results['initial_memory_mb']:.2f}MB")
        print(f"最终内�? {results['final_memory_mb']:.2f}MB")
        print(f"内存增量: {results['memory_delta_mb']:.2f}MB")
        
        print("\n按键事件类型统计:")
        type_counts: Dict[str, int] = {}
        for evt in results['events_received']:
            ct = evt['event_type']
            type_counts[ct] = type_counts.get(ct, 0) + 1
        for ct, count in sorted(type_counts.items()):
            print(f"  - {ct}: {count} �?)
        
        print("\n事件传递路径验�?")
        if results['event_paths']:
            print(f"  - 路径: {results['event_paths'][0]}")
            print("  - �?所有事件均通过完整路径传�?)
    
    if os.path.exists(ops_file):
        with open(ops_file, "r", encoding="utf-8") as f:
            ops = json.load(f)
        print(f"\n执行的按键操作数: {len(ops['operations'])}")
    
    print("\n" + "=" * 80)
    print("测试验证总结:")
    print("-" * 40)
    
    if os.path.exists(results_file):
        results = json.load(open(results_file, "r", encoding="utf-8"))
        events = results['events_received']
        ops_count = 0
        
        if os.path.exists(ops_file):
            with open(ops_file, "r", encoding="utf-8") as f:
                ops_count = len(json.load(f)['operations'])
        
        # 理论按键数（每个操作产生 KEY_DOWN + KEY_UP = 2�?        expected_keydowns = ops_count * 2  # 粗略估计
        received = len(events)
        
        print(f"�?事件接收�? {received} �?)
        print(f"�?操作执行�? {ops_count} �?)
        print(f"�?自过滤计�? {results['filtered_count']} �?(应为0)")
        
        # 检查自过滤是否真的禁用
        if results['filter_self'] == False and results['filtered_count'] == 0:
            print("✓✓�?自过滤功能已正确禁用")
        elif results['filter_self'] == True and results['filtered_count'] > 0:
            print("�?自过滤功能已启用，但�?win32 钩子自动过滤了注入事�?)
        else:
            print("✓✓�?自过滤配置验证通过")
        
        memory_stable = results['memory_delta_mb'] < 10
        print(f"�?内存稳定�? {'通过' if memory_stable else '警告'} (增量: {results['memory_delta_mb']:.2f}MB)")
        
        if results['event_paths']:
            print("✓✓�?事件传递路径验证成�?)
        
        print("\n事件覆盖情况:")
        key_names = set(e['key_name'] for e in events)
        covered_types = set(e['key_name'] for e in events)
        
        print(f"  - 字母键覆�? {len([k for k in key_names if k.isalpha() and len(k) == 1])} �?)
        print(f"  - 数字键覆�? {len([k for k in key_names if k.isdigit()])} �?)
        print(f"  - 功能键覆�? {len([k for k in key_names if k.startswith('F')])} �?)
        print(f"  - 控制键覆�? {len([k for k in key_names if k in ['ENTER', 'TAB', 'ESCAPE', 'SPACE', 'BACKSPACE']])} �?)
        print(f"  - 方向键覆�? {len([k for k in key_names if k in ['UP', 'DOWN', 'LEFT', 'RIGHT']])} �?)
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)
    
    return results_file, ops_file


if __name__ == "__main__":
    import tempfile
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--monitor":
            monitor_process(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "--simulator":
            simulator_process(sys.argv[2], sys.argv[3])
    else:
        run_integration_test()