"""使用 ImageHelp 枚举 DLL 导出函数"""
import ctypes
import os

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'dll32', '_dlls', 'DirectCOM.dll')
print(f"检查 DLL: {dll_path}")
print(f"文件存在: {os.path.exists(dll_path)}")

# 使用 ctypes 直接尝试不同的调用方式
dll = ctypes.WinDLL(dll_path)

# 尝试所有可见的函数
print("\n尝试调用可见的函数...")

# 尝试获取所有非下划线开头的函数
for name in ['DirectCom', 'DirectCOM', 'Create', 'Init', 'Startup', 'DllGetClassObject']:
    try:
        func = getattr(dll, name, None)
        if func:
            print(f"找到函数: {name}, 类型: {type(func)}")
            # 尝试获取地址
            print(f"  函数地址: {hex(ctypes.addressof(func))}")
    except Exception as e:
        print(f"检查 {name} 时出错: {e}")

# 打印所有可见的函数
print("\n所有可见的属性/函数:")
for name in dir(dll):
    if not name.startswith('_'):
        print(f"  {name}")
