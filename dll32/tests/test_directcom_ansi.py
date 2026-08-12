"""测试 DirectCOM ANSI 版本"""
import os
import sys
import ctypes

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_dir = os.path.join(_vools_dir, 'dll32', '_dlls')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

dll_path = os.path.join(dll_dir, 'DirectCOM.dll')
print("加载 DirectCOM.dll:", dll_path)

# 加载 DirectCOM (使用 CDLL 而不是 WinDLL)
dc = ctypes.CDLL(dll_path)

# 尝试 GetInstance
print("\n=== 测试 GetInstance (ANSI) ===")
try:
    func = dc.GETINSTANCE
    print("找到 GETINSTANCE")

    # ANSI 版本
    func.argtypes = [
        ctypes.c_char_p,  # DLL 名称 (bytes)
        ctypes.c_char_p   # 类名 (bytes)
    ]
    func.restype = ctypes.py_object

    dll_name = b"vbRichClient5.dll"
    class_name = b"cConstructor"

    obj = func(dll_name, class_name)
    print(f"  返回对象: {obj}")
    if obj:
        print(f"  对象类型: {type(obj)}")
        # 尝试调用对象方法
        try:
            ver = obj.Version
            print(f"  Version: {ver}")
        except Exception as e:
            print(f"  调用 Version 失败: {e}")
except Exception as e:
    print(f"  错误: {e}")
    import traceback
    traceback.print_exc()

# 尝试 WinDLL 版本
print("\n=== 测试 GetInstance (WinDLL) ===")
dc2 = ctypes.WinDLL(dll_path)
try:
    func = dc2.GETINSTANCE
    print("找到 GETINSTANCE")

    # ANSI 版本
    func.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p
    ]
    func.restype = ctypes.py_object

    dll_name = b"vbRichClient5.dll"
    class_name = b"cConstructor"

    obj = func(dll_name, class_name)
    print(f"  返回对象: {obj}")
except Exception as e:
    print(f"  错误: {e}")

print("\n=== 测试完成 ===")
