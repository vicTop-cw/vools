"""Clipboard event-loss integration tests (Windows only)."""
import sys
import time
import logging
import threading
import tkinter as tk

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.windows_only]
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(message)s',
    datefmt='%H:%M:%S'
)

from vools.reactive.monitoring.clipboard import ClipSubject, ClipChangeType, ClipboardDispatcher, _make_signature

def set_clipboard_text_tk(text: str):
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    root.destroy()

def test_rapid_consecutive_copy():
    logging.info("=" * 60)
    logging.info("æµ è¯ 1: å¿«é  è¿ ç»­å¤ å ¶ç ¸å  å  å®¹ï¼ éª è¯ ä¸ ä¼ æ°¸ä¹ ä¸¢å¤±äº ä»¶ï¼?")
    logging.info("=" * 60)

    received_events = []
    lock = threading.Lock()

    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)
    dispatcher = clip.dispatcher

    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  æ ¶å °: type={x.change_type.name}, content={content}, seq={x.sequence}")

    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)

    logging.info(f"ä½¿ç ¨å  ç«¯: {dispatcher.backend_name}")
    logging.info("ç­ å¾ 1ç§ å  å¼ å§ æµ è¯?..")
    time.sleep(1)

    same_text = "same_content_test"
    for i in range(5):
        logging.info(f"  è®¾ç½®å ªè´´æ ?[{i+1}/5]: '{same_text}'")
        set_clipboard_text_tk(same_text)
        time.sleep(0.1)

    time.sleep(0.5)
    set_clipboard_text_tk("TEST_DONE")
    time.sleep(0.5)

    clip.stop()

    with lock:
        count = len(received_events)
        unique_contents = set(str(e[1]) for e in received_events)

    logging.info(f"\nç» æ  : æ ¶å ° {count} ä¸ªäº ä»? ä¸ å  å  å®¹æ ? {len(unique_contents)}")
    logging.info(f"ç» è®¡: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}")

    if count >= 1:
        logging.info("â ?æµ è¯ é  è¿ ï¼ è ³å° æ ¶å °äº ä¸ ä¸ªäº ä»?")
    else:
        logging.error("â ?æµ è¯ å¤±è´¥ï¼ æ²¡æ  æ ¶å °ä»»ä½ äº ä»?")

    return count >= 1

def test_rapid_different_copy():
    logging.info("\n" + "=" * 60)
    logging.info("æµ è¯ 2: å¿«é  è¿ ç»­å¤ å ¶ä¸ å  å  å®¹ï¼ éª è¯ æ  æ  äº ä»¶é ½è ½è¢«æ  è ·ï¼?")
    logging.info("=" * 60)

    received_events = []
    lock = threading.Lock()

    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)
    dispatcher = clip.dispatcher

    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  æ ¶å °: type={x.change_type.name}, content={content}, seq={x.sequence}")

    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)

    logging.info(f"ä½¿ç ¨å  ç«¯: {dispatcher.backend_name}")
    logging.info("ç­ å¾ 1ç§ å  å¼ å§ æµ è¯?..")
    time.sleep(1)

    expected_texts = [
        "rapid_test_1",
        "rapid_test_2",
        "rapid_test_3",
        "rapid_test_4",
        "rapid_test_5"
    ]

    for i, text in enumerate(expected_texts):
        logging.info(f"  è®¾ç½®å ªè´´æ ?[{i+1}/5]: '{text}'")
        set_clipboard_text_tk(text)
        time.sleep(0.08)

    time.sleep(0.5)
    set_clipboard_text_tk("TEST_DONE")
    time.sleep(0.5)

    clip.stop()

    with lock:
        count = len(received_events)
        received_contents = [str(e[1]) for e in received_events if e[1] != "TEST_DONE"]

    found_count = sum(1 for et in expected_texts if et in received_contents)

    logging.info(f"\nç» æ  : æ ¶å ° {count} ä¸ªäº ä»?")
    logging.info(f"æ  æ  å  å®¹: {expected_texts}")
    logging.info(f"å® é  æ ¶å °: {received_contents}")
    logging.info(f"æ ¾å ° {found_count}/{len(expected_texts)} ä¸ªæ  æ  å  å®?")
    logging.info(f"ç» è®¡: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}")

    if found_count == len(expected_texts):
        logging.info("â ?æµ è¯ é  è¿ ï¼ æ  æ  æ  æ  å  å®¹é ½è¢«æ  è ?")
    else:
        logging.error(f"â ?æµ è¯ å¤±è´¥ï¼ å ªæ ¾å °äº?{found_count}/{len(expected_texts)} ä¸ªæ  æ  å  å®?")

    return found_count == len(expected_texts)

def test_time_window_dedup():
    logging.info("\n" + "=" * 60)
    logging.info("æµ è¯ 3: æ ¶é ´çª å £å »é  ï¼ éª è¯ ç ¸å  å  å®¹å ¨TTLå  å ¯å  æ¬¡è§¦å  ï¼?")
    logging.info("=" * 60)

    received_events = []
    lock = threading.Lock()

    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False, signature_ttl=0.5)
    dispatcher = clip.dispatcher

    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  æ ¶å °: type={x.change_type.name}, content={content}, seq={x.sequence}")

    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)

    logging.info(f"ä½¿ç ¨å  ç«¯: {dispatcher.backend_name}")
    logging.info("ç­ å¾ 1ç§ å  å¼ å§ æµ è¯?..")
    time.sleep(1)

    same_text = "time_window_test"

    logging.info(f"ç¬¬ä¸ æ¬¡è®¾ç½? '{same_text}'")
    set_clipboard_text_tk(same_text)
    time.sleep(0.2)

    logging.info(f"ç¬¬äº æ¬¡è®¾ç½®ï¼ TTLå  ï¼ : '{same_text}'")
    set_clipboard_text_tk(same_text)
    time.sleep(0.6)

    logging.info(f"ç¬¬ä¸ æ¬¡è®¾ç½®ï¼ TTLå  ï¼ : '{same_text}'")
    set_clipboard_text_tk(same_text)
    time.sleep(0.5)

    set_clipboard_text_tk("TEST_DONE")
    time.sleep(0.5)

    clip.stop()

    with lock:
        count = len(received_events)
        same_content_count = sum(1 for e in received_events if str(e[1]) == same_text)

    logging.info(f"\nç» æ  : æ ¶å ° {count} ä¸ªäº ä»? å ¶ä¸­ç ¸å  å  å®¹äº ä»¶æ ? {same_content_count}")
    logging.info(f"ç» è®¡: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}")

    if same_content_count >= 2:
        logging.info("â ?æµ è¯ é  è¿ ï¼ ç ¸å  å  å®¹å ¨TTLå  æ  å  å  æ¬¡è§¦å ?")
    else:
        logging.error("â ?æµ è¯ å¤±è´¥ï¼ ç ¸å  å  å®¹æ²¡æ  å ¨TTLå  å  æ¬¡è§¦å ?")

    return same_content_count >= 2

def test_self_filter():
    logging.info("\n" + "=" * 60)
    logging.info("æµ è¯ 4: è ªè¿ æ»¤æ ºå ¶ï¼ éª è¯ å  å  ä¸ ä¼ å¯¼è ´æ  é  å¾ªç ¯ï¼?")
    logging.info("=" * 60)

    received_events = []
    lock = threading.Lock()

    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=True)
    dispatcher = clip.dispatcher

    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  æ ¶å °: type={x.change_type.name}, content={content}, seq={x.sequence}")

    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)

    logging.info(f"ä½¿ç ¨å  ç«¯: {dispatcher.backend_name}")
    logging.info("ç­ å¾ 1ç§ å  å¼ å§ æµ è¯?..")
    time.sleep(1)

    logging.info("å¤ é ¨è®¾ç½®å ªè´´æ ? 'external_content'")
    set_clipboard_text_tk("external_content")
    time.sleep(0.5)

    logging.info("é  è¿ dispatcherå  å  : 'written_back_content'")
    clip.set_text("written_back_content", source="test")
    time.sleep(0.5)

    set_clipboard_text_tk("TEST_DONE")
    time.sleep(0.5)

    clip.stop()

    with lock:
        count = len(received_events)

    logging.info(f"\nç» æ  : æ ¶å ° {count} ä¸ªäº ä»?")
    logging.info(f"ç» è®¡: dispatch={dispatcher.dispatch_count}, self_filtered={dispatcher.self_filtered_count}, error={dispatcher.error_count}")

    if dispatcher.self_filtered_count >= 1:
        logging.info("â ?æµ è¯ é  è¿ ï¼ è ªè¿ æ»¤æ ºå ¶æ­£å¸¸å·¥ä½ ")
    else:
        logging.error("â ?æµ è¯ å¤±è´¥ï¼ è ªè¿ æ»¤æ ºå ¶æ²¡æ  æ­£å¸¸å·¥ä½ ")

    return dispatcher.self_filtered_count >= 1

if __name__ == "__main__":
    logging.info("å ªè´´æ ¿äº ä»¶ä¸¢å¤±ä¿®å¤ éª è¯ æµ è¯?")
    logging.info("=" * 60)

    results = []

    results.append(test_rapid_consecutive_copy())
    results.append(test_rapid_different_copy())
    results.append(test_time_window_dedup())
    results.append(test_self_filter())

    logging.info("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    logging.info(f"æµ è¯ ç» æ  : {passed}/{total} é  è¿ ")

    if passed == total:
        logging.info("â ?æ  æ  æµ è¯ é  è¿ ï¼?")
        sys.exit(0)
    else:
        logging.error("â ?é ¨å  æµ è¯ å¤±è´¥")
        sys.exit(1)
