import ctypes
from ctypes import c_void_p, c_long, c_wchar_p
import os

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'bridge', 'freebasic', 'modules', 'grd_grid.dll')
dll = ctypes.CDLL(dll_path)

print("Loading grd_grid.dll...", flush=True)

print("Calling FB_GRD_INIT...", flush=True)
dll.FB_GRD_INIT.argtypes = []
dll.FB_GRD_INIT.restype = c_long
result = dll.FB_GRD_INIT()
print("FB_GRD_INIT returned:", result, flush=True)

print("Calling FB_GRD_GET_CLASS_NAME...", flush=True)
dll.FB_GRD_GET_CLASS_NAME.argtypes = []
dll.FB_GRD_GET_CLASS_NAME.restype = c_void_p
class_name_ptr = dll.FB_GRD_GET_CLASS_NAME()
print("FB_GRD_GET_CLASS_NAME returned:", class_name_ptr, flush=True)

if class_name_ptr:
    class_name = ctypes.string_at(class_name_ptr).decode('ascii', errors='replace')
    print("Class name:", class_name, flush=True)
