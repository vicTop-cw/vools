import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vools.xl.viewer import show_table, TableViewer

data = [
    ['Name', 'Age', 'City'],
    ['Alice', '25', 'New York'],
    ['Bob', '30', 'London'],
    ['Charlie', '35', 'Tokyo'],
]

print("Creating viewer...")
viewer = TableViewer(data=data, title="Test Table", has_header=True)
print("Window created:", viewer._hWnd)

# 非模态显示
def close_after_delay():
    time.sleep(3)
    print("Closing window...")
    viewer.close()

threading.Thread(target=close_after_delay, daemon=True).start()
viewer.show()

# 等待消息循环结束
while viewer._msg_loop_thread and viewer._msg_loop_thread.is_alive():
    time.sleep(0.1)

print("Test completed")
