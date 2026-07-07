import os
import ctypes
from ctypes import c_void_p, c_long, c_wchar_p, POINTER

import vools
base_dir = os.path.dirname(vools.__file__)
dll_dir = os.path.join(base_dir, 'bridge', 'freebasic', 'modules')

if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(dll_dir)

ctypes.CDLL(os.path.join(dll_dir, 'grd_grid.dll'))
dll = ctypes.CDLL(os.path.join(dll_dir, 'table_viewer.dll'))

dll.TV_CREATE.argtypes = [c_wchar_p, c_long, c_long]
dll.TV_CREATE.restype = c_void_p

dll.TV_SET_SHEET_DATA.argtypes = [c_void_p, POINTER(POINTER(c_wchar_p)), c_long, c_long, c_long, c_long, c_wchar_p]
dll.TV_SET_SHEET_DATA.restype = None

dll.TV_SHOW_MODELESS.argtypes = [c_void_p]
dll.TV_SHOW_MODELESS.restype = None

dll.TV_CLOSE.argtypes = [c_void_p]
dll.TV_CLOSE.restype = None

hwnd = dll.TV_CREATE('测试', 800, 600)
print('HWND:', hwnd)

if hwnd:
    data = [['Name', 'Age'], ['Alice', '25']]
    rows = len(data)
    cols = max(len(r) for r in data)

    row_pointers = []
    string_arrays = []
    for row in data:
        arr = (c_wchar_p * cols)()
        for i, v in enumerate(row):
            arr[i] = str(v)
        string_arrays.append(arr)
        row_pointers.append(ctypes.cast(arr, POINTER(c_wchar_p)))

    c_array = (POINTER(c_wchar_p) * rows)(*row_pointers)

    dll.TV_SET_SHEET_DATA(c_void_p(hwnd), c_array, rows, cols, 1, 0, 'Sheet1')
    print('Data set done')

    dll.TV_SHOW_MODELESS(c_void_p(hwnd))
    print('Show modeless done')

    import time
    time.sleep(5)
    print('Done')
