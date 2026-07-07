"""检查 DirectCOM.dll 导出函数"""
import ctypes
import os

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'dll32', '_dlls', 'DirectCOM.dll')

print(f"检查 DLL: {dll_path}")
print(f"文件存在: {os.path.exists(dll_path)}")

try:
    dll = ctypes.WinDLL(dll_path)
    print("DLL 加载成功")

    # 尝试获取所有导出函数
    print("\n尝试获取导出函数...")

    # 先试试常见的函数名
    for name in ['DirectCom_Create', 'DirectCOM_Create', 'CreateObject', 'DllGetClassObject']:
        try:
            func = getattr(dll, name)
            print(f"找到函数: {name}")
        except AttributeError:
            print(f"未找到: {name}")

except Exception as e:
    print(f"加载失败: {e}")
