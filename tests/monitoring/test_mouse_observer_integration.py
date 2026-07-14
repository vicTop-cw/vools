"""MouseObserver integration tests (Windows only).

MouseObserver å ?MouseSubject é  æ  æµ è¯

æµ è¯ æ ¹æ¡ :
1. é ¨ç½²ä¸¤ä¸ªç ¬ç« è¿ ç¨ ï¼ ç  æ §ç¨ åº?+ é¼ æ  æ¨¡æ  ç¨ åº
2. ç¦ ç ¨è ªè¿ æ»¤æ ºå ¶ï¼ ç¡®ä¿ æ  æ  é¼ æ  äº ä»¶å® æ ´ä¼ é ?3. è¦ ç  å  ç±»é¼ æ  æ  ä½ å ºæ ¯ï¼ ç§»å ¨ã  ç ¹å »ã  æ  æ ½ã  æ» è½®ç­ ï¼?4. ç  æ  è¯¦ç» ç  äº ä»¶æ ¥å¿ è®°å½ ï¼ äº ä»¶ç±»å  ã  è§¦å  æ ¶é ´ã  å  æ  ã  äº ä»¶ä¼ é  è·¯å¾ ï¼
"""

import os
import sys
import time
import json
import subprocess
import psutil
from datetime import datetime
from typing import Dict, List, Any

import pytest

pytestmark = pytest.mark.skip(reason="legacy test, replaced by dual-process integration tests")
from vools.reactive.monitoring.mouse import (
    MouseSubject, MouseObserver, MouseData, MouseEventType
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

    def on_mouse_event(md: MouseData):
        ts = time.time()
        evt_data = {
            "x": md.x,
            "y": md.y,
            "event_type": MouseEventType(md.event_type).name,
            "button": md.button,
            "delta": md.delta,
            "timestamp": md.timestamp.isoformat(),
            "time_ms": ts,
            "sequence": md.sequence,
        }
        events_received.append(evt_data)

        log_event(log_file, "mouse_event",
                  x=md.x,
                  y=md.y,
                  mouse_event_type=MouseEventType(md.event_type).name,
                  path="backend -> _on_change -> subject -> observer -> callback")
        print(f"[ç  æ §] æ ¶å °é¼ æ  äº ä»¶: {MouseEventType(md.event_type).name} ({md.x},{md.y}) - seq={md.sequence}")

    filter_self = not disable_filter

    print(f"[ç  æ §] filter_self={filter_self} (è ªè¿ æ»¤å·²ç¦ ç ¨)")

    ms = MouseSubject(
        backend="polling",
        filter_self=filter_self,
    )

    ms.subscribe(on_next=on_mouse_event)
    ms.start()

    current_memory = process.memory_info().rss / 1024 / 1024

    print(f"[ç  æ §] å ¯å ¨æ  å  ï¼ å  ç«? {ms.backend_name}")
    print(f"[ç  æ §] filter_self: {ms.dispatcher._filter_self}")
    print(f"[ç  æ §] å  å§ å  å­ : {initial_memory:.2f}MB, å½ å  å  å­ : {current_memory:.2f}MB")

    log_event(log_file, "monitor_config",
              backend=ms.backend_name,
              filter_self=ms.dispatcher._filter_self,
              initial_memory_mb=initial_memory,
              current_memory_mb=current_memory)

    write_control(control_file, "ready",
                  pid=os.getpid(),
                  backend=ms.backend_name,
                  filter_self=ms.dispatcher._filter_self)

    while True:
        control = read_control(control_file)
        if control and control.get("action") == "stop":
            break
        time.sleep(0.05)

    time.sleep(0.5)

    ms.stop()

    final_memory = process.memory_info().rss / 1024 / 1024

    log_event(log_file, "monitor_stop",
              events_received=len(events_received),
              final_memory_mb=final_memory,
              memory_delta_mb=final_memory - initial_memory)

    results = {
        "events_received": events_received,
        "dispatch_count": ms.dispatch_count,
        "filtered_count": ms.self_filtered_count,
        "initial_memory_mb": initial_memory,
        "final_memory_mb": final_memory,
        "memory_delta_mb": final_memory - initial_memory,
        "backend": ms.backend_name,
        "filter_self": ms.dispatcher._filter_self,
    }

    results_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_monitor_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[ç  æ §] å  æ­¢ï¼ æ ¶å ?{len(events_received)} ä¸ªé¼ æ  äº ä»?")


def simulator_process(control_file: str, log_file: str):
    """é¼ æ  æ¨¡æ  ç¨ åº è¿ ç¨ """
    from vools.reactive.monitoring.mouse import _move_to, _click, _scroll, _move_relative

    log_event(log_file, "simulator_start", pid=os.getpid())

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
        log_event(log_file, "mouse_operation",
                  name=name,
                  action=action,
                  **kwargs)
        print(f"[æ¨¡æ  ] {name}: {action}")

    scenarios = [
        ("move_center", "placeholder", {"x": 960, "y": 540}),
        ("move_top_left", "ç§»å ¨å °å·¦ä¸ è§ ", {"x": 100, "y": 100}),
        ("move_top_right", "ç§»å ¨å °å ³ä¸ è§ ", {"x": 1820, "y": 100}),
        ("move_bottom_left", "ç§»å ¨å °å·¦ä¸ è§ ", {"x": 100, "y": 1060}),
        ("move_bottom_right", "ç§»å ¨å °å ³ä¸ è§ ", {"x": 1820, "y": 1060}),

        ("left_click_center", "å·¦é ®ç ¹å »ä¸­å¿ ", {"x": 960, "y": 540, "button": "left"}),
        ("left_double_click", "å·¦é ®å  å »", {"x": 960, "y": 540, "button": "left", "double": True}),
        ("right_click", "å ³é ®ç ¹å »", {"x": 960, "y": 540, "button": "right"}),
        ("middle_click", "ä¸­é ®ç ¹å »", {"x": 960, "y": 540, "button": "middle"}),

        ("scroll_up_small", "scroll_up_small", {"delta": 1}),
        ("scroll_down_small", "scroll_down_small", {"delta": -1}),
        ("scroll_up_large", "scroll_up_large", {"delta": 3}),
        ("scroll_down_large", "scroll_down_large", {"delta": -3}),

        ("rapid_moves", "placeholder", {"points": [(200, 200), (400, 200), (600, 200), (800, 200)]}),
        ("zigzag_moves", "placeholder", {"points": [(500, 300), (600, 400), (500, 500), (600, 600)]}),

        ("rapid_clicks", "rapid_clicks_test", {"count": 5, "x": 960, "y": 540}),
    ]

    print(f"\n[æ¨¡æ  ] å¼ å§ æ §è¡?{len(scenarios)} ä¸ªæµ è¯ å ºæ ?..")

    for i, scenario in enumerate(scenarios):
        name, action, params = scenario[0], scenario[1], scenario[2]

        try:
            if "x" in params and "y" in params and "button" not in params:
                _move_to(params["x"], params["y"])
                op(name, action, x=params["x"], y=params["y"])

            elif "button" in params:
                _move_to(params["x"], params["y"])
                time.sleep(0.05)
                if params.get("double"):
                    _click(params["button"])
                    time.sleep(0.05)
                    _click(params["button"])
                else:
                    _click(params["button"])
                op(name, action, x=params["x"], y=params["y"], button=params["button"])

            elif "delta" in params:
                _scroll(params["delta"])
                op(name, action, delta=params["delta"])

            elif "points" in params:
                for px, py in params["points"]:
                    _move_to(px, py)
                    time.sleep(0.02)
                op(name, action, points=params["points"])

            elif "count" in params:
                _move_to(params["x"], params["y"])
                time.sleep(0.05)
                for _ in range(params["count"]):
                    _click("left")
                    time.sleep(0.02)
                op(name, action, count=params["count"], x=params["x"], y=params["y"])

        except Exception as e:
            log_event(log_file, "simulator_error", name=name, error=str(e))
            print(f"[æ¨¡æ  ] é  è¯¯: {e}")

        time.sleep(0.15)

        if (i + 1) % 5 == 0:
            print(f"[æ¨¡æ  ] å·²å® æ ?{i+1}/{len(scenarios)} ä¸ªå ºæ ?")

    ops_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_operations.json")
    with open(ops_path, "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)

    time.sleep(1)

    write_control(control_file, "stop")

    log_event(log_file, "simulator_stop", operations=len(operations))
    print(f"[æ¨¡æ  ] å® æ   {len(operations)} ä¸ªé¼ æ  æ  ä½?")


def run_integration_test():
    """è¿ è¡ é  æ  æµ è¯ """
    import tempfile

    control_file = os.path.join(tempfile.gettempdir(), f"vools_mouse_control_{os.getpid()}.json")
    log_file = os.path.join(tempfile.gettempdir(), f"vools_mouse_test_log_{os.getpid()}.json")

    print("=" * 80)
    print("MouseObserver/MouseSubject é  æ  æµ è¯ ")
    print("è ªè¿ æ»¤ç ¶æ ? å·²ç¦ ç ¨ï¼ ç¡®ä¿ æ  æ  é¼ æ  äº ä»¶å® æ ´ä¼ é  ï¼ ")
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

    results_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_monitor_results.json")
    ops_path = os.path.join(os.path.dirname(control_file) or os.path.expanduser("~"), "_mouse_operations.json")

    print("\n" + "=" * 80)
    print("æµ è¯ ç» æ  å  æ  :")
    print("-" * 40)

    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)

        print(f"æ ¶å °é¼ æ  äº ä»¶æ ? {len(results['events_received'])}")
        print(f"å  å  è®¡æ °: {results['dispatch_count']}")
        print(f"è¿ æ»¤è®¡æ °: {results['filtered_count']}")
        print(f"å  ç«¯: {results['backend']}")
        print(f"filter_self: {results['filter_self']}")
        print(f"å  å§ å  å­ : {results['initial_memory_mb']:.2f}MB")
        print(f"æ  ç» å  å­? {results['final_memory_mb']:.2f}MB")
        print(f"å  å­ å¢ é  : {results['memory_delta_mb']:.2f}MB")

        print("\né¼ æ  äº ä»¶ç±»å  ç» è®¡:")
        type_counts: Dict[str, int] = {}
        for evt in results['events_received']:
            ct = evt['event_type']
            type_counts[ct] = type_counts.get(ct, 0) + 1
        for ct, count in sorted(type_counts.items()):
            print(f"  - {ct}: {count} ä¸?")

    if os.path.exists(ops_path):
        with open(ops_path, "r", encoding="utf-8") as f:
            ops = json.load(f)
        print(f"\næ §è¡ ç  é¼ æ  æ  ä½ æ °: {len(ops['operations'])}")

    print("\n" + "=" * 80)
    print("æµ è¯ éª è¯ æ »ç» :")
    print("-" * 40)

    if os.path.exists(results_path):
        results = json.load(open(results_path, "r", encoding="utf-8"))
        events = results['events_received']

        print(f"â ?äº ä»¶æ ¥æ ¶æ ? {len(events)} ä¸?")
        print(f"â ?è¿ æ»¤è®¡æ °: {results['filtered_count']} ä¸?(åº ä¸º0)")

        if results['filter_self'] == False and results['filtered_count'] == 0:
            print("â  â  â ?è ªè¿ æ»¤å  è ½å·²æ­£ç¡®ç¦ ç ¨")
        else:
            print("â ?è ªè¿ æ»¤ç ¶æ  é  è¦ æ£ æ ?")

        memory_stable = results['memory_delta_mb'] < 10
        print(f"â ?å  å­ ç¨³å® æ ? {'é  è¿ ' if memory_stable else 'è­¦å  '} (å¢ é  : {results['memory_delta_mb']:.2f}MB)")

        print("\näº ä»¶è¦ ç  æ  å µ:")
        type_counts = {}
        for evt in events:
            ct = evt['event_type']
            type_counts[ct] = type_counts.get(ct, 0) + 1

        print(f"  - MOVE: {type_counts.get('MOVE', 0)} ä¸?")
        print(f"  - LEFT_DOWN: {type_counts.get('LEFT_DOWN', 0)} ä¸?")
        print(f"  - LEFT_UP: {type_counts.get('LEFT_UP', 0)} ä¸?")
        print(f"  - RIGHT_DOWN: {type_counts.get('RIGHT_DOWN', 0)} ä¸?")
        print(f"  - RIGHT_UP: {type_counts.get('RIGHT_UP', 0)} ä¸?")
        print(f"  - SCROLL: {type_counts.get('SCROLL', 0)} ä¸?")
        print(f"  - DRAG: {type_counts.get('DRAG', 0)} ä¸?")

    print("\n" + "=" * 80)
    print("æµ è¯ å® æ  ")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--monitor":
            monitor_process(sys.argv[2], sys.argv[3])
        elif sys.argv[1] == "--simulator":
            simulator_process(sys.argv[2], sys.argv[3])
    else:
        run_integration_test()
