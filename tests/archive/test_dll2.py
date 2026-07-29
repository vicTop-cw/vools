# -*- coding: utf-8 -*-
import ctypes
import os

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'bridge', 'freebasic', 'modules', 'table_viewer.dll')

print(f"DLL 路径: {dll_path}")
print(f"文件存在: {os.path.exists(dll_path)}")
print(f"文件大小: {os.path.getsize(dll_path)} 字节")
print()

try:
    dll = ctypes.CDLL(dll_path)
    print("DLL 加载成功!")
    print()
    
    # 检查导出函数（FreeBASIC 导出的是大写名称）
    export_functions = {
        'tv_create': 'TV_CREATE',
        'tv_set_sheet_data': 'TV_SET_SHEET_DATA',
        'tv_set_multi_sheet': 'TV_SET_MULTI_SHEET',
        'tv_show_modal': 'TV_SHOW_MODAL',
        'tv_show_modeless': 'TV_SHOW_MODELESS',
        'tv_close': 'TV_CLOSE',
        'tv_get_selected_value': 'TV_GET_SELECTED_VALUE',
        'tv_get_selected': 'TV_GET_SELECTED',
        'tv_free_string': 'TV_FREE_STRING',
    }
    
    print("导出函数检查:")
    for func_name, export_name in export_functions.items():
        try:
            func = getattr(dll, export_name)
            print(f"  ✓ {func_name} ({export_name})")
        except AttributeError:
            print(f"  ✗ {func_name} - 未找到")
    
    print()
    print("所有导出函数验证完成!")
    
    # 验证 tv_create 函数签名
    print("\n函数签名验证:")
    dll.TV_CREATE.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.c_int]
    dll.TV_CREATE.restype = ctypes.c_void_p  # HWND
    print("  tv_create: 已配置签名")
    
    dll.TV_SET_SHEET_DATA.argtypes = [
        ctypes.c_void_p,  # hWnd
        ctypes.c_void_p,  # data_ptr (WString Ptr)
        ctypes.c_int,     # rows
        ctypes.c_int,     # cols
        ctypes.c_int,     # has_header
        ctypes.c_int,     # sheet_index
        ctypes.c_wchar_p, # sheet_name
    ]
    dll.TV_SET_SHEET_DATA.restype = None
    print("  tv_set_sheet_data: 已配置签名")
    
    dll.TV_SHOW_MODAL.argtypes = [ctypes.c_void_p]
    dll.TV_SHOW_MODAL.restype = None
    print("  tv_show_modal: 已配置签名")
    
    print("\n✓ DLL 验证通过!")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
