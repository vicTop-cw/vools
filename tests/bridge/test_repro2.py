import os
import sys
import ctypes
from ctypes import c_void_p, c_long, c_wchar_p, POINTER

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vools.xl.viewer.viewer import _get_dll, _convert_2d_list_to_c_array

print("Loading DLL...", flush=True)
dll = _get_dll().dll
print("DLL loaded", flush=True)

print("Calling TV_CREATE...", flush=True)
hWnd = dll.TV_CREATE("Test Title", c_long(800), c_long(600))
print("TV_CREATE returned:", hWnd, flush=True)

data = [
    ['Name', 'Age', 'City'],
    ['Alice', '25', 'New York'],
]
c_array, rows, cols, refs = _convert_2d_list_to_c_array(data)
print("Data converted", rows, cols, flush=True)

dll.TV_SET_SHEET_DATA(hWnd, c_array, c_long(rows), c_long(cols), c_long(1), c_long(0), c_wchar_p("Sheet1"))
print("Data set", flush=True)

dll.TV_SHOW_MODELESS(hWnd)
print("Modeless shown", flush=True)

import time
time.sleep(2)
dll.TV_CLOSE(hWnd)
print("Closed", flush=True)
