import sys
import time
import logging
import ctypes
from datetime import datetime

sys.path.insert(0, 'e:/IDEProjects/AI/vools')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d - %(message)s',
    datefmt='%H:%M:%S'
)

from vools.reactive.monitoring.clipboard import ClipSubject, ClipChangeType

def set_clipboard_text_direct(text: str):
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _CF_UNICODETEXT = 13
    
    src = text.encode("utf-16-le") + b"\x00\x00"
    for attempt in range(10):
        if not _user32.OpenClipboard(None):
            time.sleep(0.05)
            continue
        try:
            _user32.EmptyClipboard()
            h_mem = _kernel32.GlobalAlloc(0x40, len(src))
            if h_mem:
                ptr = _kernel32.GlobalLock(h_mem)
                ctypes.memmove(ptr, src, len(src))
                _kernel32.GlobalUnlock(h_mem)
                _user32.SetClipboardData(_CF_UNICODETEXT, h_mem)
            return
        finally:
            _user32.CloseClipboard()
    raise OSError("OpenClipboard 失败")

clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)

received_events = []

def on_next(x):
    content = str(x.content)[:100] if x.content else "None"
    logging.info(f"剪贴板变�?- type={x.change_type.name}, content={content}")
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
    set_clipboard_text_direct(text)
    time.sleep(0.5)

logging.info(f"测试完成，收�?{len(received_events)} 个事�?)
for i, (ct, content) in enumerate(received_events):
    logging.info(f"  事件 {i}: {ct.name} - {str(content)[:50]}")