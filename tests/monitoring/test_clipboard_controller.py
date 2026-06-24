"""Clipboard controller integration tests (Windows only)."""
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

from vools.reactive.monitoring.clipboard import ClipboardDispatcher

dispatcher = ClipboardDispatcher(change_types=None, filter_self=False)

test_texts = [
    "test message 1",
    "hello world",
    "python is great",
    "test message 2",
    "STOP_TEST"
]

logging.info("å¼å§æµè¯ï¼ä¾æ¬¡è®¾ç½®åªè´´æ¿åå®?..")
for i, text in enumerate(test_texts):
    logging.info(f"è®¾ç½®åªè´´æ? '{text}'")
    for attempt in range(3):
        try:
            dispatcher.set_clipboard(content=text, change_type="TEXT")
            break
        except Exception as e:
            logging.warning(f"  å°è¯ {attempt+1} å¤±è´¥: {e}")
            time.sleep(0.1)
    time.sleep(1)

logging.info("æµè¯å®æ")