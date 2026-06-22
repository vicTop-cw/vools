"""Clipboard simple integration tests (Windows only)."""
import sys
import time
import logging
from datetime import datetime

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.windows_only]

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
    time.sleep(0.1)
    root.destroy()

from vools.reactive.monitoring.clipboard import ClipSubject, ClipChangeType

clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)

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
    set_clipboard_text_tk(text)
    time.sleep(0.5)

logging.info(f"æµè¯å®æï¼æ¶å?{len(received_events)} ä¸ªäºä»?")
for i, (ct, content) in enumerate(received_events):
    logging.info(f"  äºä»¶ {i}: {ct.name} - {str(content)[:50]}")