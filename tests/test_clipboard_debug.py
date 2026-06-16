import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, 'e:/IDEProjects/AI/vools')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d - %(message)s',
    datefmt='%H:%M:%S'
)

import tkinter as tk

def set_clipboard_text_tk(text: str):
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    root.destroy()

from vools.reactive.monitoring.clipboard import ClipSubject, ClipChangeType, ClipboardDispatcher, _make_signature

clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)
dispatcher = clip.dispatcher

received_events = []

def on_next(x):
    content = str(x.content)[:100] if x.content else "None"
    logging.info(f"剪贴板变�?- type={x.change_type.name}, content={content}")
    sig = _make_signature(x.change_type, x.content, x.files)
    logging.info(f"  签名: {sig}")
    logging.info(f"  统计: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}, self_filtered={dispatcher._self_filtered_count}")
    received_events.append((x.change_type, x.content))

def on_error(e):
    logging.error(f"错误: {e}")

def on_completed():
    logging.info("监控完成")

pb = clip.p().when_stop(lambda x: x.content and "STOP_TEST" in str(x.content))
sub = pb.subscribe(on_next, on_error, on_completed)

logging.info("监控已启动，等待1秒后开始设置剪贴板...")
time.sleep(1)

test_texts = [
    "test message 1",
    "hello world",
    "python is great",
    "test message 2",
    "STOP_TEST"
]

logging.info("开始设置剪贴板内容...")
for text in test_texts:
    logging.info(f"设置剪贴�? '{text}'")
    set_clipboard_text_tk(text)
    time.sleep(0.8)

logging.info(f"测试完成，收�?{len(received_events)} 个事�?)
for i, (ct, content) in enumerate(received_events):
    logging.info(f"  事件 {i}: {ct.name} - {str(content)[:50]}")