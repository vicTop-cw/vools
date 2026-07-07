import os
import sys
import time
import threading
import ctypes
from ctypes import c_void_p, c_long, c_wchar_p, POINTER

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vools.xl.viewer.viewer import _get_dll, _convert_2d_list_to_c_array

dll = _get_dll().dll

result = {}

def create_in_thread():
    try:
        print("Thread: calling TV_CREATE...", flush=True)
        hWnd = dll.TV_CREATE("Test Title", c_long(800), c_long(600))
        print("Thread: TV_CREATE returned:", hWnd, flush=True)

        data = [
            ['Name', 'Age', 'City'],
            ['Alice', '25', 'New York'],
        ]
        c_array, rows, cols, refs = _convert_2d_list_to_c_array(data)
        print("Thread: data converted", rows, cols, flush=True)

        dll.TV_SET_SHEET_DATA(hWnd, c_array, c_long(rows), c_long(cols), c_long(1), c_long(0), c_wchar_p("Sheet1"))
        print("Thread: data set", flush=True)

        dll.TV_SHOW_MODELESS(hWnd)
        print("Thread: modeless shown", flush=True)

        result['hWnd'] = hWnd
        time.sleep(3)
        dll.TV_CLOSE(hWnd)
        print("Thread: closed", flush=True)
    except Exception as e:
        print("Thread error:", e, flush=True)
        result['error'] = str(e)

print("Starting thread...", flush=True)
t = threading.Thread(target=create_in_thread)
t.start()
t.join(timeout=10)
print("Main: thread finished", result, flush=True)
