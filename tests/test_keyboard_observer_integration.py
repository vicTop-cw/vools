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
        print(f"[çæ§] æ¶å°é®çäºä»¶: {KeyEventType(kd.event_type).name} - {kd.key_name} (0x{kd.key_code:02X}) - seq={kd.sequence}")
    
    filter_self = not disable_filter
    
    print(f"[çæ§] filter_self={filter_self} (èªè¿æ»¤å·²ç¦ç¨)")
    
    try:
        ks = KeySubject(
            backend="win32",
            filter_self=filter_self,
        )
        ks.subscribe(on_next=on_key_event)
        ks.start()
    except Exception as e:
        print(f"[çæ§] win32 åç«¯å¯å¨å¤±è´¥ï¼åéå?polling åç«¯: {e}")
        ks = KeySubject(
            backend="polling",
            filter_self=filter_self,
        )
        ks.subscribe(on_next=on_key_event)
        ks.start()
    
    current_memory = process.memory_info().rss / 1024 / 1024
    
    print(f"[çæ§] å¯å¨æåï¼åç«? {ks.backend_name}")
    print(f"[çæ§] filter_self: {ks.dispatcher._filter_self}")
    print(f"[çæ§] åå§åå­: {initial_memory:.2f}MB, å½ååå­: {current_memory:.2f}MB")
    
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
    
    print(f"[çæ§] åæ­¢ï¼æ¶å?{len(events_received)} ä¸ªé®çäºä»?)
    
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
        print(f"[æ¨¡æ] {name}: {action}")
    
    scenarios = [
        ("tap_a", "æå­æ¯?A", {"key": "a"}),
        ("tap_b", "æå­æ¯?B", {"key": "b"}),
        ("tap_c", "æå­æ¯?C", {"key": "c"}),
        ("tap_1", "ææ°å­?1", {"key": "1"}),
        ("tap_enter", "æåè½¦é®", {"key": "enter"}),
        
        ("tap_shift", "æ?Shift é?, {"key": "shift"}),
        ("tap_ctrl", "æ?Ctrl é?, {"key": "ctrl"}),
        ("tap_alt", "æ?Alt é?, {"key": "alt"}),
        ("tap_win", "æ?Win é?, {"key": "win"}),
        
        ("ctrl_a", "Ctrl+A", {"keys": ["ctrl", "a"]}),
        ("ctrl_c", "Ctrl+C", {"keys": ["ctrl", "c"]}),
        ("ctrl_v", "Ctrl+V", {"keys": ["ctrl", "v"]}),
        
        ("shift_a", "Shift+A", {"keys": ["shift", "a"]}),
        ("rapid_taps", "å¿«éè¿ç»­æé?, {"keys": ["a", "b", "c", "d", "e"], "delay": 0.05}),
        ("function_keys", "åè½é?F1-F4", {"keys": ["f1", "f2", "f3", "f4"]}),
        
        ("type_hello", "è¾å¥ææ¬ 'hello'", {"text": "hello"}),
    ]
    
    from vools.reactive.monitoring.keyboard import _press, _release, _type_text, _hotkey
    
    print(f"\n[æ¨¡æ] å¼å§æ§è¡?{len(scenarios)} ä¸ªæµè¯åºæ?..")
    
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
            print(f"[æ¨¡æ] éè¯¯: {e}")
        
        time.sleep(0.15)
        
        if (i + 1) % 5 == 0:
            print(f"[æ¨¡æ] å·²å®æ?{i+1}/{len(scenarios)} ä¸ªåºæ?)
    
    ops_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_keyboard_operations.json")
    with open(ops_path, "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)
    
    write_control(control_file, "done")
    
    print(f"\n[æ¨¡æ] å®æ {len(scenarios)} ä¸ªé®çæä½?)


def main():
    disable_filter = True
    
    control_file = os.path.join(os.path.expanduser("~"), "_keyboard_control.json")
    log_file = os.path.join(os.path.expanduser("~"), "_keyboard_test.log")
    
    if os.path.exists(control_file):
        os.remove(control_file)
    if os.path.exists(log_file):
        os.remove(log_file)
    
    print("=" * 80)
    print("KeyObserver/KeySubject éææµè¯")
    print(f"èªè¿æ»¤ç¶æ? {'å·²ç¦ç¨ï¼ç¡®ä¿ææé®çäºä»¶å®æ´ä¼ éï¼' if disable_filter else 'å·²å¯ç?}")
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
    print("æµè¯ç»æåæ:")
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
        
        print(f"æ¶å°é®çäºä»¶æ? {len(events)}")
        print(f"ååè®¡æ°: {data.get('dispatch_count', 0)}")
        print(f"è¿æ»¤è®¡æ°: {data.get('self_filtered_count', 0)}")
        print(f"åç«¯: {data.get('backend', 'unknown')}")
        print(f"filter_self: {data.get('filter_self', 'unknown')}")
        print(f"åå§åå­: {data.get('initial_memory_mb', 0):.2f}MB")
        print(f"æç»åå­? {data.get('final_memory_mb', 0):.2f}MB")
        mem_delta = data.get('final_memory_mb', 0) - data.get('initial_memory_mb', 0)
        print(f"åå­å¢é: {'+' if mem_delta >= 0 else ''}{mem_delta:.2f}MB")
        
        print("\né®çäºä»¶ç±»åç»è®¡:")
        for et, count in sorted(event_type_counts.items()):
            print(f"  - {et}: {count} ä¸?)
        
        ops_path = os.path.join(os.path.expanduser("~"), "_keyboard_operations.json")
        ops_count = 0
        if os.path.exists(ops_path):
            with open(ops_path, "r", encoding="utf-8") as f:
                ops_data = json.load(f)
            ops_count = len(ops_data.get("operations", []))
        
        print(f"\næ§è¡çé®çæä½æ°: {ops_count}")
    
    print("\n" + "=" * 80)
    print("æµè¯éªè¯æ»ç»:")
    print("-" * 40)
    
    if os.path.exists(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        events = data.get("events", [])
        filtered = data.get("self_filtered_count", 0)
        
        print(f"â?äºä»¶æ¥æ¶æ? {len(events)} ä¸?)
        print(f"â?è¿æ»¤è®¡æ°: {filtered} ä¸?(åºä¸º0)")
        
        if filtered == 0 and disable_filter:
            print("âââ?èªè¿æ»¤åè½å·²æ­£ç¡®ç¦ç¨")
        else:
            print("â?èªè¿æ»¤åè½å¯è½å­å¨é®é¢?)
        
        mem_delta = data.get('final_memory_mb', 0) - data.get('initial_memory_mb', 0)
        if abs(mem_delta) < 10:
            print(f"â?åå­ç¨³å®æ? éè¿ (å¢é: {'+' if mem_delta >= 0 else ''}{mem_delta:.2f}MB)")
        else:
            print(f"â?åå­ç¨³å®æ? è­¦å (å¢é: {'+' if mem_delta >= 0 else ''}{mem_delta:.2f}MB)")
        
        print("\näºä»¶è¦çæåµ:")
        event_types = ["KEY_DOWN", "KEY_UP"]
        for et in event_types:
            count = sum(1 for e in events if e.get("event_type") == et)
            print(f"  - {et}: {count} ä¸?)
    
    print("\n" + "=" * 80)
    print("æµè¯å®æ")
    print("=" * 80)


if __name__ == "__main__":
    main()
