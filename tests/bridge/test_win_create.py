import ctypes
from ctypes import c_void_p, c_long
import os

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'bridge', 'freebasic', 'modules', 'test_win_create.dll')
dll = ctypes.CDLL(dll_path)

print("Testing register class...", flush=True)
dll.TEST_REGISTER_CLASS.argtypes = []
dll.TEST_REGISTER_CLASS.restype = c_long
result = dll.TEST_REGISTER_CLASS()
print("Register class returned:", result, flush=True)

print("Testing create window...", flush=True)
dll.TEST_CREATE_WINDOW.argtypes = []
dll.TEST_CREATE_WINDOW.restype = c_void_p
hWnd = dll.TEST_CREATE_WINDOW()
print("Create window returned:", hWnd, flush=True)
