import sys
import time
import logging
import threading
from datetime import datetime

sys.path.insert(0, 'e:/IDEProjects/AI/vools')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d - %(message)s',
    datefmt='%H:%M:%S'
)

from vools.reactive.monitoring.clipboard import ClipSubject, ClipChangeType, ClipboardDispatcher

clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)
dispatcher = clip.dispatcher

logging.info(f"使用后端: {type(dispatcher._backend).__name__}")

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
    for attempt in range(5):
        try:
            dispatcher.set_clipboard(content=text, change_type="TEXT")
            break
        except Exception as e:
            logging.warning(f"  尝试 {attempt+1} 失败: {e}")
            time.sleep(0.05)
    time.sleep(0.5)

logging.info(f"测试完成，收�?{len(received_events)} 个事�?)
for i, (ct, content) in enumerate(received_events):
    logging.info(f"  事件 {i}: {ct.name} - {str(content)[:50]}")