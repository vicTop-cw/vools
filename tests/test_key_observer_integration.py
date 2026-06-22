"""KeyObserver integration tests (Windows only).

KeyObserver å ?KeySubject é  æ  æµ è¯

æµ è¯ æ ¹æ¡ :
1. é ¨ç½²ä¸¤ä¸ªç ¬ç« è¿ ç¨ ï¼ ç  æ §ç¨ åº?+ æ  é ®æ¨¡æ  ç¨ åº
2. ç¦ ç ¨è ªè¿ æ»¤æ ºå ¶ï¼ ç¡®ä¿ æ  æ  æ  é ®äº ä»¶å® æ ´ä¼ é ?3. è¦ ç  å  ç±»å¸¸è§ æ  é ®ç» å  ã  ç ¹æ® å  è ½é ®ã  è¿ ç»­å¿«é  æ  é ®å ºæ ?4. ç  æ  è¯¦ç» ç  äº ä»¶æ ¥å¿ è®°å½ ï¼ äº ä»¶ç±»å  ã  è§¦å  æ ¶é ´ã  æ  é ®ä»£ç  ã  äº ä»¶ä¼ é  è·¯å¾ ï¼
"""

import os
import sys
import time
import json
import subprocess
import psutil
from datetime import datetime
from typing import Dict, List, Any, Tuple

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.windows_only]

# æ·»å  é¡¹ç ®æ ¹ç ®å½ å °è·¯å¾
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive.monitoring.keyboard import (
    KeySubject, KeyObserver, KeyData, KeyEventType, KeyModifier
)


def log_event(log_file: str, event_type: str, **data) -> None:
    """è®°å½ æµ è¯ äº ä»¶"""
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
    """å  å ¥æ §å ¶æ  ä»¤"""
    with open(control_file, "w", encoding="utf-8") as f:
        json.dump({"action": action, "timestamp": datetime.now().isoformat(), **kwargs}, f)


def read_control(control_file: str) -> Dict | None:
    """è¯»å  æ §å ¶æ  ä»¤"""
    if not os.path.exists(control_file):
        return None
    try:
        with open(control_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def monitor_process(control_file: str, log_file: str, disable_filter: bool = True):
    """ç  æ §ç¨ åº è¿ ç¨ """
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
        print(f"[ç  æ §] æ ¶å °æ  é ®: {kd.key_name} ({KeyEventType(kd.event_type).name}) - seq={kd.sequence}")

    # ç¦ ç ¨è ªè¿ æ»?    filter_self = not disable_filter

    print(f"[ç  æ §] filter_self={filter_self} (è ªè¿ æ»¤å·²ç¦ ç ¨)")

    ks = KeySubject(
        backend="win32",
        filter_self=filter_self,
    )
    ks.start()

    ks.subscribe(on_next=on_key_press)
    subscription = ks

    current_memory = process.memory_info().rss / 1024 / 1024

    print(f"[ç  æ §] å ¯å ¨æ  å  ï¼ å  ç«? {ks.backend_name}")
    print(f"[ç  æ §] filter_self: {ks.dispatcher._filter_self}")
    print(f"[ç  æ §] å  å§ å  å­ : {initial_memory:.2f}MB, å½ å  å  å­ : {current_memory:.2f}MB")

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

    print(f"[ç  æ §] å  æ­¢ï¼ æ ¶å ?{len(events_received)} ä¸ªæ  é ®äº ä»?")


def simulator_process(control_file: str, log_file: str):
    """æ  é ®æ¨¡æ  ç¨ åº è¿ ç¨ """
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

    # å® ä¹ æ¨¡æ  æ  é ®å ½æ °
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
        print(f"[æ¨¡æ  ] {name}: {key_info}")

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

    # å ºæ ¯1ï¼ å  ä¸ªå­ æ¯ é ®
    for char in ["A", "B", "C", "D", "E"]:
        test_scenarios.append((f"single_letter_{char}", char, [VK[char]]))

    # å ºæ ¯2ï¼ æ °å­ é ®
    for num in ["1", "2", "3", "4", "5"]:
        test_scenarios.append((f"single_number_{num}", num, [VK[num]]))

    # å ºæ ¯3ï¼ å  è ½é ®
    for fkey in ["F1", "F2", "F3"]:
        test_scenarios.append((f"function_key_{fkey}", fkey, [VK[fkey]]))

    # å ºæ ¯4ï¼ æ §å ¶é ®
    for ckey in ["ENTER", "TAB", "ESCAPE", "SPACE", "BACKSPACE"]:
        test_scenarios.append((f"control_key_{ckey}", ckey, [VK[ckey]]))

    # å ºæ ¯5ï¼ æ ¹å  é ®
    for akey in ["UP", "DOWN", "LEFT", "RIGHT"]:
        test_scenarios.append((f"arrow_key_{akey}", akey, [VK[akey]]))

    # å ºæ ¯6ï¼ ç» å  é ® Ctrl+Key
    for char in ["A", "C", "V", "S"]:
        test_scenarios.append((f"ctrl_combination_{char}", f"Ctrl+{char}", [VK["CTRL"], VK[char]], True))

    # å ºæ ¯7ï¼ ç» å  é ® Shift+Key
    for char in ["A", "1"]:
        test_scenarios.append((f"shift_combination_{char}", f"Shift+{char}", [VK["SHIFT"], VK[char]], True))

    # å ºæ ¯8ï¼ ç» å  é ® Alt+Tab
    test_scenarios.append(("alt_tab", "Alt+Tab", [VK["ALT"], VK["TAB"]], True))

    # å ºæ ¯9ï¼ è¿ ç»­å¿«é  æ  é ®ï¼ æ¯?0msä¸ ä¸ªï¼
    rapid_keys = ["Q", "W", "E", "R", "T"]
    test_scenarios.append(("rapid_typing", "rapid_typing_test", [VK[k] for k in rapid_keys], False, 0.02))

    # æ §è¡ æ  æ  å ºæ ?    print(f"\n[æ¨¡æ  ] å¼ å§ æ §è¡?{len(test_scenarios)} ä¸ªæµ è¯ å ºæ ?..")

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
            print(f"[æ¨¡æ  ] {name} å¤±è´¥: {e}")
            log_event(log_file, "operation_error", name=name, error=str(e))

        if (i + 1) % 10 == 0:
            print(f"[æ¨¡æ  ] å·²å® æ ?{i + 1}/{len(test_scenarios)} ä¸ªå ºæ ?")

    with open(os.path.join(os.path.dirname(control_file) or tempfile.gettempdir(), "_key_operations.json"), "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)

    time.sleep(1)

    write_control(control_file, "stop")

    log_event(log_file, "simulator_stop", operations=len(operations))
    print(f"[æ¨¡æ  ] å® æ   {len(operations)} ä¸ªæ  é ®æ  ä½?")


def run_integration_test():
    """è¿ è¡ é  æ  æµ è¯ """
    import tempfile

    control_file = os.path.join(tempfile.gettempdir(), f"vools_key_control_{os.getpid()}.json")
    log_file = os.path.join(tempfile.gettempdir(), f"vools_key_test_log_{os.getpid()}.json")

    print("=" * 80)
    print("KeyObserver/KeySubject é  æ  æµ è¯ ")
    print("è ªè¿ æ»¤ç ¶æ ? å·²ç¦ ç ¨ï¼ ç¡®ä¿ æ  æ  æ  é ®äº ä»¶å® æ ´ä¼ é  ï¼ ")
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
    print("ç  æ §ç¨ åº è¾ å º:")
    print("-" * 40)
    print(monitor_stdout[-2000:] if monitor_stdout else "")
    if monitor_stderr:
        print("é  è¯¯:")
        print(monitor_stderr[-500:] if monitor_stderr else "")

    print("\n" + "=" * 80)
    print("æ¨¡æ  ç¨ åº è¾ å º:")
    print("-" * 40)
    print(simulator_stdout[-2000:] if simulator_stdout else "")
    if simulator_stderr:
        print("é  è¯¯:")
        print(simulator_stderr[-500:] if simulator_stderr else "")

    results_file = os.path.join(os.path.dirname(control_file) or tempfile.gettempdir(), "_key_monitor_results.json")
    ops_file = os.path.join(os.path.dirname(control_file) or tempfile.gettempdir(), "_key_operations.json")

    print("\n" + "=" * 80)
    print("æµ è¯ ç» æ  å  æ  :")
    print("-" * 40)

    if os.path.exists(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            results = json.load(f)

        print(f"æ ¶å °æ  é ®äº ä»¶æ ? {len(results['events_received'])}")
        print(f"å  å  è®¡æ °: {results['dispatch_count']}")
        print(f"è¿ æ»¤è®¡æ °: {results['filtered_count']}")
        print(f"å  ç«¯: {results['backend']}")
        print(f"filter_self: {results['filter_self']}")
        print(f"å  å§ å  å­ : {results['initial_memory_mb']:.2f}MB")
        print(f"æ  ç» å  å­? {results['final_memory_mb']:.2f}MB")
        print(f"å  å­ å¢ é  : {results['memory_delta_mb']:.2f}MB")

        print("\næ  é ®äº ä»¶ç±»å  ç» è®¡:")
        type_counts: Dict[str, int] = {}
        for evt in results['events_received']:
            ct = evt['event_type']
            type_counts[ct] = type_counts.get(ct, 0) + 1
        for ct, count in sorted(type_counts.items()):
            print(f"  - {ct}: {count} ä¸?")

        print("\näº ä»¶ä¼ é  è·¯å¾ éª è¯?")
        if results['event_paths']:
            print(f"  - è·¯å¾ : {results['event_paths'][0]}")
            print("  - â ?æ  æ  äº ä»¶å  é  è¿ å® æ ´è·¯å¾ ä¼ é ?")

    if os.path.exists(ops_file):
        with open(ops_file, "r", encoding="utf-8") as f:
            ops = json.load(f)
        print(f"\næ §è¡ ç  æ  é ®æ  ä½ æ °: {len(ops['operations'])}")

    print("\n" + "=" * 80)
    print("æµ è¯ éª è¯ æ »ç» :")
    print("-" * 40)

    if os.path.exists(results_file):
        results = json.load(open(results_file, "r", encoding="utf-8"))
        events = results['events_received']
        ops_count = 0

        if os.path.exists(ops_file):
            with open(ops_file, "r", encoding="utf-8") as f:
                ops_count = len(json.load(f)['operations'])

        # ç  è®ºæ  é ®æ °ï¼ æ¯ ä¸ªæ  ä½ äº§ç   KEY_DOWN + KEY_UP = 2ï¼?        expected_keydowns = ops_count * 2  # ç² ç ¥ä¼°è®¡
        received = len(events)

        print(f"â ?äº ä»¶æ ¥æ ¶æ ? {received} ä¸?")
        print(f"â ?æ  ä½ æ §è¡ æ ? {ops_count} ä¸?")
        print(f"â ?è ªè¿ æ»¤è®¡æ ? {results['filtered_count']} ä¸?(åº ä¸º0)")

        # æ£ æ ¥è ªè¿ æ»¤æ ¯å ¦ç  ç  ç¦ ç ¨
        if results['filter_self'] == False and results['filtered_count'] == 0:
            print("â  â  â ?è ªè¿ æ»¤å  è ½å·²æ­£ç¡®ç¦ ç ¨")
        elif results['filter_self'] == True and results['filtered_count'] > 0:
            print("â ?è ªè¿ æ»¤å  è ½å·²å ¯ç ¨ï¼ ä½ å ?win32 é ©å­ è ªå ¨è¿ æ»¤äº æ³¨å ¥äº ä»?")
        else:
            print("â  â  â ?è ªè¿ æ»¤é  ç½®éª è¯ é  è¿ ")

        memory_stable = results['memory_delta_mb'] < 10
        print(f"â ?å  å­ ç¨³å® æ ? {'é  è¿ ' if memory_stable else 'è­¦å  '} (å¢ é  : {results['memory_delta_mb']:.2f}MB)")

        if results['event_paths']:
            print("â  â  â ?äº ä»¶ä¼ é  è·¯å¾ éª è¯ æ  å ?")

        print("\näº ä»¶è¦ ç  æ  å µ:")
        key_names = set(e['key_name'] for e in events)
        covered_types = set(e['key_name'] for e in events)

        print(f"  - å­ æ¯ é ®è¦ ç ? {len([k for k in key_names if k.isalpha() and len(k) == 1])} ä¸?")
        print(f"  - æ °å­ é ®è¦ ç ? {len([k for k in key_names if k.isdigit()])} ä¸?")
        print(f"  - å  è ½é ®è¦ ç ? {len([k for k in key_names if k.startswith('F')])} ä¸?")
        print(f"  - æ §å ¶é ®è¦ ç ? {len([k for k in key_names if k in ['ENTER', 'TAB', 'ESCAPE', 'SPACE', 'BACKSPACE']])} ä¸?")
        print(f"  - æ ¹å  é ®è¦ ç ? {len([k for k in key_names if k in ['UP', 'DOWN', 'LEFT', 'RIGHT']])} ä¸?")

    print("\n" + "=" * 80)
    print("æµ è¯ å® æ  ")
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