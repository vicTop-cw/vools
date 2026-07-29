import ctypes
from ctypes import c_void_p
import os

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'bridge', 'freebasic', 'modules', 'test_grd_child.dll')
dll = ctypes.CDLL(dll_path)

print("Calling TEST_CREATE_GRD_CHILD...", flush=True)
dll.TEST_CREATE_GRD_CHILD.argtypes = []
dll.TEST_CREATE_GRD_CHILD.restype = c_void_p
hWnd = dll.TEST_CREATE_GRD_CHILD()
print("TEST_CREATE_GRD_CHILD returned:", hWnd, flush=True)
