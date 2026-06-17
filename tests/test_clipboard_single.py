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

logging.info(f"ä½¿ç¨åç«¯: {type(dispatcher._backend).__name__}")

received_events = []

def on_next(x):
    content = str(x.content)[:100] if x.content else "None"
    logging.info(f"åªè´´æ¿åæ?- type={x.change_type.name}, content={content}")
    received_events.append((x.change_type, x.content))

def on_error(e):
    logging.error(f"éè¯¯: {e}")

def on_completed():
    logging.info("çæ§å®æ")

pb = clip.p().when_stop(lambda x: x.content and "STOP_TEST" in str(x.content))
sub = pb.subscribe(on_next, on_error, on_completed)

logging.info("çæ§å·²å¯å¨ï¼ç­å¾1ç§åå¼å§è®¾ç½®åªè´´æ¿...")
time.sleep(1)

test_texts = [
    "test message 1",
    "hello world",
    "python is great",
    "test message 2",
    "STOP_TEST"
]

logging.info("å¼å§è®¾ç½®åªè´´æ¿åå®¹...")
for text in test_texts:
    logging.info(f"è®¾ç½®åªè´´æ? '{text}'")
    for attempt in range(5):
        try:
            dispatcher.set_clipboard(content=text, change_type="TEXT")
            break
        except Exception as e:
            logging.warning(f"  å°è¯ {attempt+1} å¤±è´¥: {e}")
            time.sleep(0.05)
    time.sleep(0.5)

logging.info(f"æµè¯å®æï¼æ¶å?{len(received_events)} ä¸ªäºä»?)
for i, (ct, content) in enumerate(received_events):
    logging.info(f"  äºä»¶ {i}: {ct.name} - {str(content)[:50]}")