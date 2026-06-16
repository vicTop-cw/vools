import os
import sys
import json
import time
import multiprocessing
import psutil
from datetime import datetime
from typing import Dict, List, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive.monitoring.keyboard import (
    KeySubject, KeyObserver, KeyData, KeyEventType
)


def log_event(log_file: str, event_type: str, **data) -> None:
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
    with open(control_file, "w", encoding="utf-8") as f:
        json.dump({"action": action, "timestamp": datetime.now().isoformat(), **kwargs}, f)


def read_control(control_file: str) -> Dict | None:
    if not os.path.exists(control_file):
        return None
    try:
        with open(control_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def monitor_process(control_file: str, log_file: str, disable_filter: bool):
    import logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    log_event(log_file, "monitor_start", pid=os.getpid())
    
    events_received: List[Dict] = []
    
    def on_key_event(kd: KeyData):
        ts = time.time()
        evt_data = {
            "key_code": kd.key_code,
            "key_name": kd.key_name,
            "is_press": kd.is_press,
            "event_type": KeyEventType(kd.event_type).name,
            "modifiers": kd.modifiers,
            "timestamp": kd.timestamp.isoformat(),
            "time_ms": ts,
            "sequence": kd.sequence,
        }
        events_received.append(evt_data)
        
        log_event(log_file, "key_event",
                  key_code=kd.key_code,
                  key_name=kd.key_name,
                  key_event_type=KeyEventType(kd.event_type).name,
                  path="backend -> _on_change -> subject -> observer -> callback")
        print(f"[监控] 收到键盘事件: {KeyEventType(kd.event_type).name} - {kd.key_name} (0x{kd.key_code:02X}) - seq={kd.sequence}")
    
    filter_self = not disable_filter
    
    print(f"[监控] filter_self={filter_self} (自过滤已禁用)")
    
    try:
        ks = KeySubject(
            backend="win32",
            filter_self=filter_self,
        )
        ks.subscribe(on_next=on_key_event)
        ks.start()
    except Exception as e:
        print(f"[监控] win32 后端启动失败，回退�?polling 后端: {e}")
        ks = KeySubject(
            backend="polling",
            filter_self=filter_self,
        )
        ks.subscribe(on_next=on_key_event)
        ks.start()
    
    current_memory = process.memory_info().rss / 1024 / 1024
    
    print(f"[监控] 启动成功，后�? {ks.backend_name}")
    print(f"[监控] filter_self: {ks.dispatcher._filter_self}")
    print(f"[监控] 初始内存: {initial_memory:.2f}MB, 当前内存: {current_memory:.2f}MB")
    
    log_event(log_file, "monitor_config",
              backend=ks.backend_name,
              filter_self=ks.dispatcher._filter_self,
              initial_memory_mb=initial_memory)
    
    write_control(control_file, "ready")
    
    start_time = time.time()
    while time.time() - start_time < 60:
        control = read_control(control_file)
        if control and control.get("action") == "done":
            break
        time.sleep(0.1)
    
    ks.stop()
    
    final_memory = process.memory_info().rss / 1024 / 1024
    
    log_event(log_file, "monitor_stop",
              events_count=len(events_received),
              dispatch_count=ks.dispatch_count,
              self_filtered_count=ks.self_filtered_count,
              final_memory_mb=final_memory)
    
    print(f"[监控] 停止，收�?{len(events_received)} 个键盘事�?)
    
    events_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_keyboard_events.json")
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump({
            "events": events_received,
            "dispatch_count": ks.dispatch_count,
            "self_filtered_count": ks.self_filtered_count,
            "backend": ks.backend_name,
            "filter_self": ks.dispatcher._filter_self,
            "initial_memory_mb": initial_memory,
            "final_memory_mb": final_memory,
        }, f, ensure_ascii=False, indent=2)


def simulator_process(control_file: str, log_file: str):
    time.sleep(0.5)
    
    while True:
        control = read_control(control_file)
        if control and control.get("action") == "ready":
            break
        time.sleep(0.1)
    
    time.sleep(0.5)
    
    operations: List[Dict] = []
    
    def op(name: str, action: str, **kwargs):
        ts = time.time()
        operations.append({
            "name": name,
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "time_ms": ts,
            **kwargs
        })
        log_event(log_file, "keyboard_operation",
                  name=name,
                  action=action,
                  **kwargs)
        print(f"[模拟] {name}: {action}")
    
    scenarios = [
        ("tap_a", "按字�?A", {"key": "a"}),
        ("tap_b", "按字�?B", {"key": "b"}),
        ("tap_c", "按字�?C", {"key": "c"}),
        ("tap_1", "按数�?1", {"key": "1"}),
        ("tap_enter", "按回车键", {"key": "enter"}),
        
        ("tap_shift", "�?Shift �?, {"key": "shift"}),
        ("tap_ctrl", "�?Ctrl �?, {"key": "ctrl"}),
        ("tap_alt", "�?Alt �?, {"key": "alt"}),
        ("tap_win", "�?Win �?, {"key": "win"}),
        
        ("ctrl_a", "Ctrl+A", {"keys": ["ctrl", "a"]}),
        ("ctrl_c", "Ctrl+C", {"keys": ["ctrl", "c"]}),
        ("ctrl_v", "Ctrl+V", {"keys": ["ctrl", "v"]}),
        
        ("shift_a", "Shift+A", {"keys": ["shift", "a"]}),
        ("rapid_taps", "快速连续按�?, {"keys": ["a", "b", "c", "d", "e"], "delay": 0.05}),
        ("function_keys", "功能�?F1-F4", {"keys": ["f1", "f2", "f3", "f4"]}),
        
        ("type_hello", "输入文本 'hello'", {"text": "hello"}),
    ]
    
    from vools.reactive.monitoring.keyboard import _press, _release, _type_text, _hotkey
    
    print(f"\n[模拟] 开始执�?{len(scenarios)} 个测试场�?..")
    
    for i, scenario in enumerate(scenarios):
        name, action, params = scenario[0], scenario[1], scenario[2]
        
        try:
            if "key" in params:
                _press(params["key"])
                time.sleep(0.02)
                _release(params["key"])
                op(name, action, key=params["key"])
            
            elif "keys" in params:
                keys = params["keys"]
                delay = params.get("delay", 0.05)
                for key in keys:
                    _press(key)
                    time.sleep(delay)
                    _release(key)
                    time.sleep(delay)
                op(name, action, keys=keys)
            
            elif "text" in params:
                _type_text(params["text"])
                op(name, action, text=params["text"])
            
        except Exception as e:
            log_event(log_file, "simulator_error", name=name, error=str(e))
            print(f"[模拟] 错误: {e}")
        
        time.sleep(0.15)
        
        if (i + 1) % 5 == 0:
            print(f"[模拟] 已完�?{i+1}/{len(scenarios)} 个场�?)
    
    ops_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_keyboard_operations.json")
    with open(ops_path, "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)
    
    write_control(control_file, "done")
    
    print(f"\n[模拟] 完成 {len(scenarios)} 个键盘操�?)


def main():
    disable_filter = True
    
    control_file = os.path.join(os.path.expanduser("~"), "_keyboard_control.json")
    log_file = os.path.join(os.path.expanduser("~"), "_keyboard_test.log")
    
    if os.path.exists(control_file):
        os.remove(control_file)
    if os.path.exists(log_file):
        os.remove(log_file)
    
    print("=" * 80)
    print("KeyObserver/KeySubject 集成测试")
    print(f"自过滤状�? {'已禁用（确保所有键盘事件完整传递）' if disable_filter else '已启�?}")
    print("=" * 80)
    
    monitor = multiprocessing.Process(target=monitor_process, args=(control_file, log_file, disable_filter))
    simulator = multiprocessing.Process(target=simulator_process, args=(control_file, log_file))
    
    monitor.start()
    
    time.sleep(1)
    
    simulator.start()
    
    simulator.join()
    monitor.join(timeout=65)
    
    if monitor.is_alive():
        monitor.terminate()
        monitor.join()
    
    print("\n" + "=" * 80)
    print("测试结果分析:")
    print("-" * 40)
    
    events_path = os.path.join(os.path.expanduser("~"), "_keyboard_events.json")
    if os.path.exists(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        events = data.get("events", [])
        event_type_counts = {}
        for evt in events:
            et = evt.get("event_type", "UNKNOWN")
            event_type_counts[et] = event_type_counts.get(et, 0) + 1
        
        print(f"收到键盘事件�? {len(events)}")
        print(f"分发计数: {data.get('dispatch_count', 0)}")
        print(f"过滤计数: {data.get('self_filtered_count', 0)}")
        print(f"后端: {data.get('backend', 'unknown')}")
        print(f"filter_self: {data.get('filter_self', 'unknown')}")
        print(f"初始内存: {data.get('initial_memory_mb', 0):.2f}MB")
        print(f"最终内�? {data.get('final_memory_mb', 0):.2f}MB")
        mem_delta = data.get('final_memory_mb', 0) - data.get('initial_memory_mb', 0)
        print(f"内存增量: {'+' if mem_delta >= 0 else ''}{mem_delta:.2f}MB")
        
        print("\n键盘事件类型统计:")
        for et, count in sorted(event_type_counts.items()):
            print(f"  - {et}: {count} �?)
        
        ops_path = os.path.join(os.path.expanduser("~"), "_keyboard_operations.json")
        ops_count = 0
        if os.path.exists(ops_path):
            with open(ops_path, "r", encoding="utf-8") as f:
                ops_data = json.load(f)
            ops_count = len(ops_data.get("operations", []))
        
        print(f"\n执行的键盘操作数: {ops_count}")
    
    print("\n" + "=" * 80)
    print("测试验证总结:")
    print("-" * 40)
    
    if os.path.exists(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        events = data.get("events", [])
        filtered = data.get("self_filtered_count", 0)
        
        print(f"�?事件接收�? {len(events)} �?)
        print(f"�?过滤计数: {filtered} �?(应为0)")
        
        if filtered == 0 and disable_filter:
            print("✓✓�?自过滤功能已正确禁用")
        else:
            print("�?自过滤功能可能存在问�?)
        
        mem_delta = data.get('final_memory_mb', 0) - data.get('initial_memory_mb', 0)
        if abs(mem_delta) < 10:
            print(f"�?内存稳定�? 通过 (增量: {'+' if mem_delta >= 0 else ''}{mem_delta:.2f}MB)")
        else:
            print(f"�?内存稳定�? 警告 (增量: {'+' if mem_delta >= 0 else ''}{mem_delta:.2f}MB)")
        
        print("\n事件覆盖情况:")
        event_types = ["KEY_DOWN", "KEY_UP"]
        for et in event_types:
            count = sum(1 for e in events if e.get("event_type") == et)
            print(f"  - {et}: {count} �?)
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
