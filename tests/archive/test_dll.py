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
    
    # 检查导出函数
    export_functions = [
        'tv_create',
        'tv_set_sheet_data',
        'tv_set_multi_sheet',
        'tv_show_modal',
        'tv_show_modeless',
        'tv_close',
        'tv_get_selected_value',
        'tv_get_selected',
        'tv_free_string',
    ]
    
    print("导出函数检查:")
    for func_name in export_functions:
        try:
            func = getattr(dll, func_name)
            print(f"  ✓ {func_name}")
        except AttributeError:
            print(f"  ✗ {func_name} - 未找到")
    
    print()
    print("所有导出函数验证完成!")
    
except Exception as e:
    print(f"DLL 加载失败: {e}")
    import traceback
    traceback.print_exc()
