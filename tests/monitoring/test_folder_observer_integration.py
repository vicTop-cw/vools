"""FolderObserver integration tests (Windows only).

FolderObserver å ?FolderSubject é  æ  æµ è¯

æµ è¯ æ ¹æ¡ :
1. é ¨ç½²ä¸¤ä¸ªç ¬ç« è¿ ç¨ ï¼ ç  æ §ç¨ åº?+ ç ®å½ æ  ä½ ç¨ åº
2. æµ è¯ 5ç§ ä»¥ä¸ ç ®å½ æ  ä½ å ºæ ¯ï¼ æ¯ ä¸ªå ºæ ¯æ §è¡ 3æ¬¡ä»¥ä¸?3. è®°å½ è¯¦ç» ç  æ ¥å¿ ä¿¡æ ¯ï¼ æ ¶é ´æ ³ã  è¿ ç¨ IDã  äº ä»¶ç±»å  ã  ç ®å½ è·¯å¾ ï¼
4. è®°å½ CPUå  å  å­ å  ç ¨æ  å ?5. è ªè¿ æ»¤å  è ½é» è®¤å ³é ­ï¼ æµ è¯ è¿ ç¨ ä¸­å ¯å ¯ç ¨éª è¯
"""

import os
import sys
import time
import json
import tempfile
import subprocess
import psutil
from datetime import datetime
from typing import Dict, List, Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.windows_only]


def log_event(log_file: str, event_type: str, **data) -> None:
    """Test helper function."""
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
    """Test helper function."""
    with open(control_file, "w", encoding="utf-8") as f:
        json.dump({"action": action, "timestamp": datetime.now().isoformat(), **kwargs}, f)


def read_control(control_file: str) -> Dict | None:
    """Test helper function."""
    if not os.path.exists(control_file):
        return None
    try:
        with open(control_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def create_test_directory_structure(base_dir: str) -> Dict[str, str]:
    """Test helper function."""
    structure = {
        "level1_sub1": os.path.join(base_dir, "level1_sub1"),
        "level1_sub2": os.path.join(base_dir, "level1_sub2"),
        "level2_sub1": os.path.join(base_dir, "level1_sub1", "level2_sub1"),
        "level2_sub2": os.path.join(base_dir, "level1_sub1", "level2_sub2"),
        "level2_sub3": os.path.join(base_dir, "level1_sub2", "level2_sub3"),
        "level3_sub1": os.path.join(base_dir, "level1_sub1", "level2_sub1", "level3_sub1"),
        "level3_sub2": os.path.join(base_dir, "level1_sub1", "level2_sub2", "level3_sub2"),
        "file_1kb": os.path.join(base_dir, "file_1kb.txt"),
        "file_5kb": os.path.join(base_dir, "file_5kb.txt"),
        "file_10mb": os.path.join(base_dir, "file_10mb.bin"),
    }
    return structure


def monitor_process(test_dir: str, control_file: str, log_file: str, enable_filter: bool = False):
    """Test helper function."""
    import logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    from vools.reactive.monitoring.folder_watcher import FolderSubject, FolderObserver, FolderChangeType

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024

    log_event(log_file, "monitor_start",
              pid=os.getpid(),
              test_dir=test_dir,
              enable_filter=enable_filter)

    events_received: List[Dict] = []
    event_timestamps: List[float] = []

    def on_event(fd):
        ts = time.time()
        events_received.append({
            "path": fd.path,
            "change_type": fd.change_type.name,
            "timestamp": fd.timestamp.isoformat(),
            "time_ms": ts,
        })
        event_timestamps.append(ts)
        log_event(log_file, "monitor_event",
                  path=fd.path,
                  change_type=fd.change_type.name)
        print(f"[ç  æ §] æ ¶å °äº ä»¶: {fd.change_type.name} - {os.path.basename(fd.path)}")

    fs = FolderSubject(paths=[test_dir], auto_start=True, filter_self=enable_filter)

    current_memory = process.memory_info().rss / 1024 / 1024

    print(f"[ç  æ §] å ¯å ¨æ  å  ï¼ å  ç«? {fs.backend_name}")
    print(f"[ç  æ §] filter_self: {fs.dispatcher.filter_self}")
    print(f"[ç  æ §] å  å§ å  å­ : {initial_memory:.2f}MB, å½ å  å  å­ : {current_memory:.2f}MB")
    log_event(log_file, "monitor_config",
              backend=fs.backend_name,
              filter_self=fs.dispatcher.filter_self,
              initial_memory_mb=initial_memory,
              current_memory_mb=current_memory)

    subscription = fs.subscribe(on_next=on_event)

    write_control(control_file, "ready",
                  pid=os.getpid(),
                  backend=fs.backend_name,
                  filter_self=enable_filter)

    events_before_self = len(events_received)
    filtered_before = fs.dispatcher._self_filtered_count

    time.sleep(0.5)

    self_folder = os.path.join(test_dir, "self_created_folder")
    print(f"[ç  æ §] å¼ å§ è ªè¿ æ»¤æµ è¯ ")
    log_event(log_file, "self_test_start")

    if enable_filter:
        fs.dispatcher.register_self_signature(self_folder, FolderChangeType.FOLDER_CREATED)

    os.makedirs(self_folder, exist_ok=True)
    time.sleep(0.3)

    if enable_filter:
        fs.dispatcher.register_self_signature(self_folder, FolderChangeType.FOLDER_DELETED)

    try:
        os.rmdir(self_folder)
    except:
        pass
    time.sleep(0.3)

    log_event(log_file, "self_test_end",
              events_before=events_before_self,
              events_after=len(events_received),
              filtered_before=filtered_before,
              filtered_after=fs.dispatcher._self_filtered_count)

    print(f"[ç  æ §] è ªæµ è¯ å® æ ?- æ °å¢ äº ä»¶: {len(events_received) - events_before_self}, è¿ æ»¤äº ä»¶: {fs.dispatcher._self_filtered_count - filtered_before}")

    while True:
        control = read_control(control_file)
        if control and control.get("action") == "stop":
            break
        time.sleep(0.1)

    time.sleep(1)

    subscription.unsubscribe()
    fs.stop()

    final_memory = process.memory_info().rss / 1024 / 1024

    log_event(log_file, "monitor_stop",
              events_received=len(events_received),
              final_memory_mb=final_memory,
              memory_delta_mb=final_memory - initial_memory)

    with open(os.path.join(test_dir, "_monitor_results.json"), "w", encoding="utf-8") as f:
        json.dump({
            "events_received": events_received,
            "dispatch_count": fs.dispatcher.dispatch_count,
            "filtered_count": fs.dispatcher._self_filtered_count,
            "initial_memory_mb": initial_memory,
            "final_memory_mb": final_memory,
            "memory_delta_mb": final_memory - initial_memory,
            "backend": fs.backend_name,
            "filter_self": fs.dispatcher.filter_self,
        }, f, ensure_ascii=False, indent=2)

    print(f"[ç  æ §] å  æ­¢ï¼ æ ¶å ?{len(events_received)} ä¸ªäº ä»?")


def folder_operations_process(test_dir: str, control_file: str, log_file: str, structure: Dict[str, str], repeat: int = 3):
    """Test helper function."""
    log_event(log_file, "ops_start", pid=os.getpid())

    while True:
        control = read_control(control_file)
        if control and control.get("action") == "ready":
            break
        time.sleep(0.1)

    time.sleep(0.5)

    operations: List[Dict] = []

    def op(name: str, action: str, path: str, **kwargs):
        ts = time.time()
        operations.append({
            "name": name,
            "action": action,
            "path": path,
            "timestamp": datetime.now().isoformat(),
            "time_ms": ts,
            **kwargs
        })
        log_event(log_file, "folder_operation",
                  name=name,
                  action=action,
                  path=path,
                  **kwargs)
        print(f"[æ  ä½ ] {name}: {action} {os.path.basename(path)}")

    op_scenarios = [
        ("create_subdir_l2", "create", structure["level2_sub1"], {}),
        ("create_subdir_l3", "create", structure["level3_sub1"], {}),
        ("delete_subdir_l3", "delete", structure["level3_sub1"], {}),
        ("rename_subdir", "rename", structure["level2_sub2"], {"target": os.path.join(test_dir, "level1_sub1", "level2_sub2_renamed")}),
        ("create_in_l1", "create", structure["level1_sub2"], {}),
        ("delete_in_l1", "delete", structure["level1_sub2"], {}),
        ("create_nested_structure", "create", os.path.join(test_dir, "nested", "deep", "folder"), {}),
        ("delete_nested_structure", "delete", os.path.join(test_dir, "nested"), {}),
    ]

    for i in range(repeat):
        print(f"\n=== æ §è¡ å ºæ ¯ {i+1}/{repeat} ===")
        for name, action, path, extra in op_scenarios:
            try:
                if action == "create":
                    os.makedirs(path, exist_ok=True)
                    op(f"{name}_run{i+1}", action, path, **extra)
                    time.sleep(0.2)
                elif action == "delete":
                    if os.path.exists(path):
                        os.rmdir(path)
                    op(f"{name}_run{i+1}", action, path, **extra)
                    time.sleep(0.2)
                elif action == "rename":
                    target = extra.get("target", path + "_renamed")
                    if os.path.exists(path):
                        os.rename(path, target)
                    op(f"{name}_run{i+1}", action, path, target=target)
                    time.sleep(0.2)
                    if os.path.exists(target):
                        os.rename(target, path)
            except Exception as e:
                print(f"[æ  ä½ ] {name} å¤±è´¥: {e}")
                log_event(log_file, "operation_error", name=name, error=str(e))

    with open(os.path.join(test_dir, "_operations.json"), "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)

    time.sleep(1)

    write_control(control_file, "stop")

    log_event(log_file, "ops_stop", operations=len(operations))
    print(f"[æ  ä½ ] å® æ   {len(operations)} ä¸ªæ  ä½?")


def run_integration_test(enable_filter: bool = False, repeat: int = 3):
    """Test helper function."""
    test_dir = tempfile.mkdtemp(prefix="vools_folder_test_")
    control_file = os.path.join(tempfile.gettempdir(), f"vools_folder_control_{os.getpid()}.json")
    log_file = os.path.join(tempfile.gettempdir(), f"vools_folder_test_log_{os.getpid()}.json")

    structure = create_test_directory_structure(test_dir)

    print("=" * 80)
    print("FolderObserver/FolderSubject é  æ  æµ è¯ ")
    print(f"æµ è¯ ç ®å½ : {test_dir}")
    print(f"filter_self: {'å ¯ç ¨' if enable_filter else 'å ³é ­ï¼ é» è®¤ï¼ '}")
    print(f"å ºæ ¯é  å¤ æ¬¡æ °: {repeat}")
    print("=" * 80)

    if os.path.exists(log_file):
        os.remove(log_file)
    if os.path.exists(control_file):
        os.remove(control_file)

    for name, path in structure.items():
        if "file" not in name:
            try:
                os.makedirs(path, exist_ok=True)
            except:
                pass

    if structure["file_1kb"]:
        with open(structure["file_1kb"], "w", encoding="utf-8") as f:
            f.write("x" * 1024)

    if structure["file_5kb"]:
        with open(structure["file_5kb"], "w", encoding="utf-8") as f:
            f.write("x" * 5120)

    if structure["file_10mb"]:
        with open(structure["file_10mb"], "wb") as f:
            f.write(b"x" * (10 * 1024 * 1024))

    print(f"\nç ®å½ ç» æ  å·²å  å»ºï¼ å  å « {len([k for k in structure if 'file' not in k])} ä¸ªå­ ç ®å½ ")

    monitor_proc = subprocess.Popen(
        [sys.executable, __file__, "--monitor", test_dir, control_file, log_file, str(enable_filter)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    ops_proc = subprocess.Popen(
        [sys.executable, __file__, "--operations", test_dir, control_file, log_file, json.dumps(structure), str(repeat)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        monitor_stdout, monitor_stderr = monitor_proc.communicate(timeout=120)
        ops_stdout, ops_stderr = ops_proc.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        monitor_proc.kill()
        ops_proc.kill()
        monitor_stdout, monitor_stderr = monitor_proc.communicate()
        ops_stdout, ops_stderr = ops_proc.communicate()

    print("\n" + "=" * 80)
    print("ç  æ §ç¨ åº è¾ å º:")
    print("-" * 40)
    print(monitor_stdout[:2000] if monitor_stdout else "")
    if monitor_stderr:
        print("é  è¯¯:")
        print(monitor_stderr[:500] if monitor_stderr else "")

    print("\n" + "=" * 80)
    print("ç ®å½ æ  ä½ ç¨ åº è¾ å º:")
    print("-" * 40)
    print(ops_stdout[:2000] if ops_stdout else "")
    if ops_stderr:
        print("é  è¯¯:")
        print(ops_stderr[:500] if ops_stderr else "")

    results_path = os.path.join(test_dir, "_monitor_results.json")
    ops_path = os.path.join(test_dir, "_operations.json")

    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)

        print("\n" + "=" * 80)
        print("æµ è¯ ç» æ  å  æ  :")
        print("-" * 40)
        print(f"æ ¶å °äº ä»¶æ ? {results['events_received']}")
        print(f"å  å  è®¡æ °: {results['dispatch_count']}")
        print(f"è ªè¿ æ»¤è®¡æ ? {results['filtered_count']}")
        print(f"å  ç«¯: {results['backend']}")
        print(f"filter_self: {results['filter_self']}")
        print(f"å  å§ å  å­ : {results['initial_memory_mb']:.2f}MB")
        print(f"æ  ç» å  å­? {results['final_memory_mb']:.2f}MB")
        print(f"å  å­ å¢ é  : {results['memory_delta_mb']:.2f}MB")

        if results['events_received']:
            print("\næ ¶å °ç  äº ä»¶ç±»å  ç» è®?")
            type_counts: Dict[str, int] = {}
            for evt in results['events_received']:
                ct = evt['change_type']
                type_counts[ct] = type_counts.get(ct, 0) + 1
            for ct, count in sorted(type_counts.items()):
                print(f"  - {ct}: {count} ä¸?")

    if os.path.exists(ops_path):
        with open(ops_path, "r", encoding="utf-8") as f:
            ops = json.load(f)

        print(f"\næ §è¡ ç  ç ®å½ æ  ä½ æ °: {len(ops['operations'])}")

    print("\n" + "=" * 80)
    print("æµ è¯ éª è¯ æ »ç» :")
    print("-" * 40)

    if os.path.exists(results_path):
        results = json.load(open(results_path, "r", encoding="utf-8"))
        events = results['events_received']

        folder_events = [e for e in events if any(x in e['path'] for x in ['level', 'nested'])]

        print(f"â ?ç ®å½ ç ¸å ³äº ä»¶æ  è ·: {len(folder_events)} ä¸?")
        print(f"â ?æ »äº ä»¶æ °: {len(events)} ä¸?")
        print(f"â ?è ªè¿ æ»¤äº ä»¶æ °: {results['filtered_count']} ä¸?")

        memory_stable = results['memory_delta_mb'] < 10
        print(f"â ?å  å­ ç¨³å® æ ? {'é  è¿ ' if memory_stable else 'è­¦å  '} (å¢ é  : {results['memory_delta_mb']:.2f}MB)")

        if enable_filter and results['filtered_count'] > 0:
            print("\nâ  â  â ?è ªè¿ æ»¤å  è ½éª è¯ æ  å ?")
        elif not enable_filter:
            print("\nâ  â  â ?é» è®¤å ³é ­æµ è¯ éª è¯ æ  å  ï¼ æ  æ  å¤ è¿ æ»¤ï¼?")

        if len(folder_events) > 0:
            print("â  â  â ?ç ®å½ å  æ ´æ  è ·éª è¯ æ  å  ")

        delay_threshold_ms = 500
        if events:
            event_times = [e['time_ms'] for e in events]
            min_time = min(event_times)
            max_delay = max([(t - min_time) * 1000 for t in event_times])
            print(f"â ?äº ä»¶å»¶è¿ : æ  å¤?{max_delay:.0f}ms (é  å ? {delay_threshold_ms}ms)")

    print("\n" + "=" * 80)
    print("æµ è¯ å® æ  ")
    print("=" * 80)

    return results_path, ops_path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--monitor":
            test_dir = sys.argv[2]
            control_file = sys.argv[3]
            log_file = sys.argv[4] if len(sys.argv) > 4 else ""
            enable_filter = sys.argv[5].lower() == "true" if len(sys.argv) > 5 else False
            monitor_process(test_dir, control_file, log_file, enable_filter)
        elif sys.argv[1] == "--operations":
            test_dir = sys.argv[2]
            control_file = sys.argv[3]
            log_file = sys.argv[4] if len(sys.argv) > 4 else ""
            structure_str = sys.argv[5] if len(sys.argv) > 5 else "{}"
            repeat = int(sys.argv[6]) if len(sys.argv) > 6 else 3
            structure = json.loads(structure_str)
            folder_operations_process(test_dir, control_file, log_file, structure, repeat)
    else:
        print("\n" + "=" * 80)
        print("æµ è¯  1: è ªè¿ æ»¤å  è ½é» è®¤å ³é ?")
        print("=" * 80)
        run_integration_test(enable_filter=False, repeat=3)

        time.sleep(2)

        print("\n" + "=" * 80)
        print("æµ è¯  2: è ªè¿ æ»¤å  è ½å ¯ç ?")
        print("=" * 80)
        run_integration_test(enable_filter=True, repeat=3)
