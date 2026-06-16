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

from vools.reactive.monitoring.clipboard import ClipboardDispatcher

dispatcher = ClipboardDispatcher(change_types=None, filter_self=False)

test_texts = [
    "test message 1",
    "hello world",
    "python is great",
    "test message 2",
    "STOP_TEST"
]

logging.info("开始测试，依次设置剪贴板内�?..")
for i, text in enumerate(test_texts):
    logging.info(f"设置剪贴�? '{text}'")
    for attempt in range(3):
        try:
            dispatcher.set_clipboard(content=text, change_type="TEXT")
            break
        except Exception as e:
            logging.warning(f"  尝试 {attempt+1} 失败: {e}")
            time.sleep(0.1)
    time.sleep(1)

logging.info("测试完成")