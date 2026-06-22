"""FileObserver integration tests (Windows only).

FileObserver å ?FileSubject é  æ  æµ è¯ 

æµ è¯ æ ¹æ¡ :
1. é ¨ç½²ä¸¤ä¸ªç ¬ç« è¿ ç¨ ï¼ ç  æ §ç¨ åº?+ æ  ä»¶æ  ä½ ç¨ åº 
2. ç  æ §ç¨ åº å® ç °é» è®¤è ªè¿ æ»¤å  è ?3. éª è¯ é  ç  æ §ç¨ åº äº§ç  ç  å  æ ´è ½è¢«æ­£ç¡®æ  è ·
4. éª è¯ ç  æ §ç¨ åº è ªèº«äº§ç  ç  ä¿®æ ¹ä¸ ä¼ è§¦å  è®¢é  äº ä»?"""

import os
import sys
import time
import json
import tempfile
import subprocess
from datetime import datetime

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.windows_only]


def log_event(log_file, event_type, **data):
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


def write_control(control_file, action):
    """å  å ¥æ §å ¶æ  ä»¤"""
    with open(control_file, "w", encoding="utf-8") as f:
        json.dump({"action": action, "timestamp": datetime.now().isoformat()}, f)


def read_control(control_file):
    """è¯»å  æ §å ¶æ  ä»¤"""
    if not os.path.exists(control_file):
        return None
    try:
        with open(control_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def monitor_process(test_dir, control_file, log_file):
    """ç  æ §ç¨ åº è¿ ç¨ """
    import logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vools.reactive.monitoring.file_watcher import FileSubject, FileObserver, FileChangeType

    log_event(log_file, "monitor_start", pid=os.getpid(), test_dir=test_dir)

    events_received = []

    def on_event(fd):
        events_received.append({
            "path": fd.path,
            "change_type": fd.change_type.name,
            "timestamp": fd.timestamp.isoformat(),
            "size": fd.size,
        })
        log_event(log_file, "monitor_event",
                  path=fd.path,
                  change_type=fd.change_type.name,
                  size=fd.size,
                  filtered=False)
        print(f"[ç  æ §] æ ¶å °äº ä»¶: {fd.change_type.name} - {os.path.basename(fd.path)}")

    fs = FileSubject(paths=[test_dir], auto_start=True, filter_self=True)

    print(f"[ç  æ §] å ¯å ¨æ  å  ï¼ å  ç«? {fs.backend_name}")
    print(f"[ç  æ §] filter_self: {fs.dispatcher.filter_self}")
    log_event(log_file, "monitor_config", backend=fs.backend_name, filter_self=fs.dispatcher.filter_self)

    subscription = fs.subscribe(on_next=on_event)

    write_control(control_file, "ready")

    events_before_self = len(events_received)
    filtered_before = fs.dispatcher._self_filtered_count

    time.sleep(0.5)

    self_file = os.path.join(test_dir, "self_modified.txt")
    print(f"[ç  æ §] å¼ å§ è ªä¿®æ ¹æµ è¯ : {self_file}")
    log_event(log_file, "self_modify_start", path=self_file)

    fs.dispatcher.register_self_signature(self_file, FileChangeType.CREATED)
    with open(self_file, "w", encoding="utf-8") as f:
        f.write("self modified content")
    time.sleep(0.3)

    fs.dispatcher.register_self_signature(self_file, FileChangeType.MODIFIED)
    with open(self_file, "a", encoding="utf-8") as f:
        f.write("\nmore content")
    time.sleep(0.3)

    fs.dispatcher.register_self_signature(self_file, FileChangeType.DELETED)
    os.remove(self_file)
    time.sleep(0.3)

    log_event(log_file, "self_modify_end",
              events_before=events_before_self,
              events_after=len(events_received),
              filtered_before=filtered_before,
              filtered_after=fs.dispatcher._self_filtered_count)

    print(f"[ç  æ §] è ªä¿®æ ¹æµ è¯ å® æ ?- æ °å¢ äº ä»¶: {len(events_received) - events_before_self}, è¿ æ»¤äº ä»¶: {fs.dispatcher._self_filtered_count - filtered_before}")

    while True:
        control = read_control(control_file)
        if control and control.get("action") == "stop":
            break
        time.sleep(0.1)

    time.sleep(1)

    subscription.unsubscribe()
    fs.stop()

    log_event(log_file, "monitor_stop",
              events_received=len(events_received))

    with open(os.path.join(test_dir, "_monitor_results.json"), "w", encoding="utf-8") as f:
        json.dump({
            "events_received": events_received,
            "dispatch_count": fs.dispatcher.dispatch_count,
            "filtered_count": fs.dispatcher._self_filtered_count,
        }, f, ensure_ascii=False, indent=2)

    print(f"[ç  æ §] å  æ­¢ï¼ æ ¶å ?{len(events_received)} ä¸ªäº ä»?")


def file_operations_process(test_dir, control_file, log_file):
    """æ  ä»¶æ  ä½ ç¨ åº è¿ ç¨ """
    log_event(log_file, "ops_start", pid=os.getpid())

    while True:
        control = read_control(control_file)
        if control and control.get("action") == "ready":
            break
        time.sleep(0.1)

    time.sleep(0.5)

    text_file = os.path.join(test_dir, "test_text.txt")
    binary_file = os.path.join(test_dir, "test_binary.bin")
    rename_file = os.path.join(test_dir, "test_rename.txt")
    rename_target = os.path.join(test_dir, "test_renamed.txt")

    operations = []

    def op(name, action, path, **kwargs):
        operations.append({
            "name": name,
            "action": action,
            "path": path,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        })
        log_event(log_file, "file_operation", name=name, action=action, path=path, **kwargs)
        print(f"[æ  ä½ ] {name}: {action} {os.path.basename(path)}")

    op("create_text", "create", text_file, content="Hello, World!")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write("Hello, World!")
    time.sleep(0.3)

    op("modify_text", "modify", text_file, content="Modified content")
    with open(text_file, "a", encoding="utf-8") as f:
        f.write("\nModified content")
    time.sleep(0.3)

    op("create_binary", "create", binary_file, content="binary_data")
    with open(binary_file, "wb") as f:
        f.write(b"binary data 123")
    time.sleep(0.3)

    op("modify_binary", "modify", binary_file, content="more_binary_data")
    with open(binary_file, "ab") as f:
        f.write(b" more data")
    time.sleep(0.3)

    op("create_rename", "create", rename_file, content="to be renamed")
    with open(rename_file, "w", encoding="utf-8") as f:
        f.write("to be renamed")
    time.sleep(0.3)

    op("rename_file", "rename", rename_file, target=rename_target)
    os.rename(rename_file, rename_target)
    time.sleep(0.3)

    op("delete_text", "delete", text_file)
    os.remove(text_file)
    time.sleep(0.3)

    op("delete_binary", "delete", binary_file)
    os.remove(binary_file)
    time.sleep(0.3)

    with open(os.path.join(test_dir, "_operations.json"), "w", encoding="utf-8") as f:
        json.dump({"operations": operations}, f, ensure_ascii=False, indent=2)

    time.sleep(1)

    write_control(control_file, "stop")

    log_event(log_file, "ops_stop", operations=len(operations))
    print(f"[æ  ä½ ] å® æ   {len(operations)} ä¸ªæ  ä½?")


def run_integration_test():
    """è¿ è¡ é  æ  æµ è¯ """
    test_dir = tempfile.mkdtemp(prefix="vools_file_test_")
    control_file = os.path.join(tempfile.gettempdir(), f"vools_control_{os.getpid()}.json")
    log_file = os.path.join(tempfile.gettempdir(), f"vools_test_log_{os.getpid()}.json")

    print("=" * 70)
    print("FileObserver/FileSubject é  æ  æµ è¯ ")
    print(f"æµ è¯ ç ®å½ : {test_dir}")
    print("=" * 70)

    if os.path.exists(log_file):
        os.remove(log_file)
    if os.path.exists(control_file):
        os.remove(control_file)

    monitor_proc = subprocess.Popen(
        [sys.executable, __file__, "--monitor", test_dir, control_file, log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    ops_proc = subprocess.Popen(
        [sys.executable, __file__, "--operations", test_dir, control_file, log_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    monitor_stdout, monitor_stderr = monitor_proc.communicate(timeout=60)
    ops_stdout, ops_stderr = ops_proc.communicate(timeout=60)

    print("\n" + "=" * 70)
    print("ç  æ §ç¨ åº è¾ å º:")
    print("-" * 40)
    print(monitor_stdout)
    if monitor_stderr:
        print("é  è¯¯:")
        print(monitor_stderr)

    print("\n" + "=" * 70)
    print("æ  ä»¶æ  ä½ ç¨ åº è¾ å º:")
    print("-" * 40)
    print(ops_stdout)
    if ops_stderr:
        print("é  è¯¯:")
        print(ops_stderr)

    results_path = os.path.join(test_dir, "_monitor_results.json")
    ops_path = os.path.join(test_dir, "_operations.json")

    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)

        print("\n" + "=" * 70)
        print("æµ è¯ ç» æ  å  æ  :")
        print("-" * 40)
        print(f"æ ¶å °äº ä»¶æ ? {len(results['events_received'])}")
        print(f"å  å  è®¡æ °: {results['dispatch_count']}")
        print(f"è ªè¿ æ»¤è®¡æ ? {results['filtered_count']}")

        print("\næ ¶å °ç  äº ä»?")
        for evt in results['events_received']:
            print(f"  - {evt['change_type']}: {os.path.basename(evt['path'])}")

    if os.path.exists(ops_path):
        with open(ops_path, "r", encoding="utf-8") as f:
            ops = json.load(f)

        print("\næ §è¡ ç  æ  ä½?")
        for op in ops['operations']:
            print(f"  - {op['name']}: {op['action']} {os.path.basename(op['path'])}")

    print("\n" + "=" * 70)
    print("æµ è¯ éª è¯ æ »ç» :")
    print("-" * 40)
    if os.path.exists(results_path):
        events = results['events_received']
        filtered_count = results['filtered_count']

        test_text_events = [e for e in events if 'test_text' in e['path']]
        test_binary_events = [e for e in events if 'test_binary' in e['path']]
        test_rename_events = [e for e in events if 'test_renamed' in e['path']]
        self_modified_events = [e for e in events if 'self_modified' in e['path']]

        print(f"â ?æ  æ ¬æ  ä»¶äº ä»¶: {len(test_text_events)} ä¸?(å  å»º/ä¿®æ ¹/å  é ¤)")
        print(f"â ?äº è¿ å ¶æ  ä»¶äº ä»? {len(test_binary_events)} ä¸?(å  å»º/ä¿®æ ¹/å  é ¤)")
        print(f"â ?é  å ½å  æ  ä»¶äº ä»? {len(test_rename_events)} ä¸?")
        print(f"â ?è ªä¿®æ ¹æ  ä»¶äº ä»? {len(self_modified_events)} ä¸ªè¢«æ ¥æ ¶ (é ¨å  MODIFIEDæ ªè¿ æ»¤æ ¯æ­£å¸¸ç ?")
        print(f"â ?è ªè¿ æ»¤äº ä»¶æ °: {filtered_count} ä¸?(CREATED/MODIFIED/DELETEDå ?ä¸?")

        if filtered_count >= 3:
            print("\nâ  â  â ?è ªè¿ æ»¤å  è ½éª è¯ æ  å ? ç  æ §ç¨ åº è ªèº«äº§ç  ç  æ  ä»¶å  æ ´äº ä»¶è¢«æ­£ç¡®è¿ æ»¤")
        else:
            print("\nâ ?è ªè¿ æ»¤å  è ½éª è¯ æ ªå® å ¨é  è¿ ")

        if len(test_text_events) > 0 and len(test_binary_events) > 0:
            print("â  â  â ?æ  ä»¶å  æ ´æ  è ·éª è¯ æ  å  : å ¶ä» è¿ ç¨ äº§ç  ç  æ  ä»¶å  æ ´äº ä»¶è¢«æ­£ç¡®æ  è ·")
        else:
            print("â ?æ  ä»¶å  æ ´æ  è ·éª è¯ æ ªå® å ¨é  è¿ ")

    print("\n" + "=" * 70)
    print("æµ è¯ å® æ  ")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--monitor":
            monitor_process(sys.argv[2], sys.argv[3], sys.argv[4])
        elif sys.argv[1] == "--operations":
            file_operations_process(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        run_integration_test()