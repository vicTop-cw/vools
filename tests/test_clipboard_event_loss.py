import sys
import time
import logging
import threading
import tkinter as tk

sys.path.insert(0, 'e:/IDEProjects/AI/vools')

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
    logging.info("测试1: 快速连续复制相同内容（验证不会永久丢失事件�?)
    logging.info("=" * 60)
    
    received_events = []
    lock = threading.Lock()
    
    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)
    dispatcher = clip.dispatcher
    
    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  收到: type={x.change_type.name}, content={content}, seq={x.sequence}")
    
    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)
    
    logging.info(f"使用后端: {dispatcher.backend_name}")
    logging.info("等待1秒后开始测�?..")
    time.sleep(1)
    
    same_text = "same_content_test"
    for i in range(5):
        logging.info(f"  设置剪贴�?[{i+1}/5]: '{same_text}'")
        set_clipboard_text_tk(same_text)
        time.sleep(0.1)
    
    time.sleep(0.5)
    set_clipboard_text_tk("TEST_DONE")
    time.sleep(0.5)
    
    clip.stop()
    
    with lock:
        count = len(received_events)
        unique_contents = set(str(e[1]) for e in received_events)
    
    logging.info(f"\n结果: 收到 {count} 个事�? 不同内容�? {len(unique_contents)}")
    logging.info(f"统计: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}")
    
    if count >= 1:
        logging.info("�?测试通过：至少收到了一个事�?)
    else:
        logging.error("�?测试失败：没有收到任何事�?)
    
    return count >= 1

def test_rapid_different_copy():
    logging.info("\n" + "=" * 60)
    logging.info("测试2: 快速连续复制不同内容（验证所有事件都能被捕获�?)
    logging.info("=" * 60)
    
    received_events = []
    lock = threading.Lock()
    
    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False)
    dispatcher = clip.dispatcher
    
    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  收到: type={x.change_type.name}, content={content}, seq={x.sequence}")
    
    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)
    
    logging.info(f"使用后端: {dispatcher.backend_name}")
    logging.info("等待1秒后开始测�?..")
    time.sleep(1)
    
    expected_texts = [
        "rapid_test_1",
        "rapid_test_2", 
        "rapid_test_3",
        "rapid_test_4",
        "rapid_test_5"
    ]
    
    for i, text in enumerate(expected_texts):
        logging.info(f"  设置剪贴�?[{i+1}/5]: '{text}'")
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
    
    logging.info(f"\n结果: 收到 {count} 个事�?)
    logging.info(f"期望内容: {expected_texts}")
    logging.info(f"实际收到: {received_contents}")
    logging.info(f"找到 {found_count}/{len(expected_texts)} 个期望内�?)
    logging.info(f"统计: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}")
    
    if found_count == len(expected_texts):
        logging.info("�?测试通过：所有期望内容都被捕�?)
    else:
        logging.error(f"�?测试失败：只找到�?{found_count}/{len(expected_texts)} 个期望内�?)
    
    return found_count == len(expected_texts)

def test_time_window_dedup():
    logging.info("\n" + "=" * 60)
    logging.info("测试3: 时间窗口去重（验证相同内容在TTL后可再次触发�?)
    logging.info("=" * 60)
    
    received_events = []
    lock = threading.Lock()
    
    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=False, signature_ttl=0.5)
    dispatcher = clip.dispatcher
    
    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  收到: type={x.change_type.name}, content={content}, seq={x.sequence}")
    
    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)
    
    logging.info(f"使用后端: {dispatcher.backend_name}")
    logging.info("等待1秒后开始测�?..")
    time.sleep(1)
    
    same_text = "time_window_test"
    
    logging.info(f"第一次设�? '{same_text}'")
    set_clipboard_text_tk(same_text)
    time.sleep(0.2)
    
    logging.info(f"第二次设置（TTL内）: '{same_text}'")
    set_clipboard_text_tk(same_text)
    time.sleep(0.6)
    
    logging.info(f"第三次设置（TTL后）: '{same_text}'")
    set_clipboard_text_tk(same_text)
    time.sleep(0.5)
    
    set_clipboard_text_tk("TEST_DONE")
    time.sleep(0.5)
    
    clip.stop()
    
    with lock:
        count = len(received_events)
        same_content_count = sum(1 for e in received_events if str(e[1]) == same_text)
    
    logging.info(f"\n结果: 收到 {count} 个事�? 其中相同内容事件�? {same_content_count}")
    logging.info(f"统计: dispatch={dispatcher.dispatch_count}, duplicate={dispatcher.duplicate_count}, error={dispatcher.error_count}")
    
    if same_content_count >= 2:
        logging.info("�?测试通过：相同内容在TTL后成功再次触�?)
    else:
        logging.error("�?测试失败：相同内容没有在TTL后再次触�?)
    
    return same_content_count >= 2

def test_self_filter():
    logging.info("\n" + "=" * 60)
    logging.info("测试4: 自过滤机制（验证写回不会导致无限循环�?)
    logging.info("=" * 60)
    
    received_events = []
    lock = threading.Lock()
    
    clip = ClipSubject(change_types=ClipChangeType.TEXT, filter_self=True)
    dispatcher = clip.dispatcher
    
    def on_next(x):
        with lock:
            received_events.append((x.change_type, x.content))
        content = str(x.content)[:50] if x.content else "None"
        logging.info(f"  收到: type={x.change_type.name}, content={content}, seq={x.sequence}")
    
    pb = clip.p().when_stop(lambda x: x.content and "TEST_DONE" in str(x.content))
    sub = pb.subscribe(on_next)
    
    logging.info(f"使用后端: {dispatcher.backend_name}")
    logging.info("等待1秒后开始测�?..")
    time.sleep(1)
    
    logging.info("外部设置剪贴�? 'external_content'")
    set_clipboard_text_tk("external_content")
    time.sleep(0.5)
    
    logging.info("通过dispatcher写回: 'written_back_content'")
    clip.set_text("written_back_content", source="test")
    time.sleep(0.5)
    
    set_clipboard_text_tk("TEST_DONE")
    time.sleep(0.5)
    
    clip.stop()
    
    with lock:
        count = len(received_events)
    
    logging.info(f"\n结果: 收到 {count} 个事�?)
    logging.info(f"统计: dispatch={dispatcher.dispatch_count}, self_filtered={dispatcher.self_filtered_count}, error={dispatcher.error_count}")
    
    if dispatcher.self_filtered_count >= 1:
        logging.info("�?测试通过：自过滤机制正常工作")
    else:
        logging.error("�?测试失败：自过滤机制没有正常工作")
    
    return dispatcher.self_filtered_count >= 1

if __name__ == "__main__":
    logging.info("剪贴板事件丢失修复验证测�?)
    logging.info("=" * 60)
    
    results = []
    
    results.append(test_rapid_consecutive_copy())
    results.append(test_rapid_different_copy())
    results.append(test_time_window_dedup())
    results.append(test_self_filter())
    
    logging.info("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    logging.info(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        logging.info("�?所有测试通过�?)
        sys.exit(0)
    else:
        logging.error("�?部分测试失败")
        sys.exit(1)