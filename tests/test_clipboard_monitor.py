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

from vools.reactive.monitoring.clipboard import ClipSubject, ClipChangeType, ClipboardDispatcher

clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)
dispatcher = clip.dispatcher

logging.info(f"使用后端: {type(dispatcher._backend).__name__}")
logging.info(f"change_types_allowed: {dispatcher._change_types_allowed}")

def on_next(x):
    content = str(x.content)[:100] if x.content else "None"
    logging.info(f"剪贴板变�?- type={x.change_type.name}, content={content}")
    logging.info(f"  统计: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}")

def on_error(e):
    logging.error(f"错误: {e}")

def on_completed():
    logging.info("监控完成")

pb = clip.p().when_stop(lambda x: x.content and "STOP_TEST" in str(x.content))
sub = pb.subscribe(on_next, on_error, on_completed)

logging.info(f"clip.monitoring: {clip.monitoring}")
logging.info(f"dispatcher.is_running: {dispatcher.is_running}")
logging.info("监控已启动，等待剪贴板变�?..")

while clip.monitoring:
    time.sleep(0.1)