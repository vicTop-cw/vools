import os
import ctypes
import time

import vools
base_dir = os.path.dirname(vools.__file__)
dll_dir = os.path.join(base_dir, 'bridge', 'freebasic', 'modules')

if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(dll_dir)

ctypes.CDLL(os.path.join(dll_dir, 'grd_grid.dll'))
dll = ctypes.CDLL(os.path.join(dll_dir, 'table_viewer.dll'))

dll.TV_CREATE.argtypes = [ctypes.c_wchar_p, ctypes.c_long, ctypes.c_long]
dll.TV_CREATE.restype = ctypes.c_void_p

dll.TV_SHOW_MODELESS.argtypes = [ctypes.c_void_p]
dll.TV_SHOW_MODELESS.restype = None

hwnd = dll.TV_CREATE('测试窗口', 800, 600)
print('HWND:', hwnd)

if hwnd:
    dll.TV_SHOW_MODELESS(ctypes.c_void_p(hwnd))
    print('Window shown, sleeping 3 seconds...')
    time.sleep(3)
    print('Done')
