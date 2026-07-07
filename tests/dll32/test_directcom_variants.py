"""测试 DirectCOM 各种函数"""
import os
import sys
import ctypes
import struct

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_dir = os.path.join(_vools_dir, 'dll32', '_dlls')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

dll_path = os.path.join(dll_dir, 'DirectCOM.dll')
print("加载 DirectCOM.dll:", dll_path)

# 加载 DirectCOM
dc = ctypes.WinDLL(dll_path)

# IUnknown 的 IID
IID_IUnknown = ctypes.c_void_p(0x00000000)

def try_call(func, args, name):
    """尝试调用函数"""
    print(f"\n尝试 {name}...")
    try:
        result = func(*args)
        print(f"  成功! 结果: {result}")
        return result
    except Exception as e:
        print(f"  失败: {e}")
        return None

# 尝试 GETDLLCLASSOBJECT
print("\n=== 测试 GETDLLCLASSOBJECT ===")
try:
    func = dc.GETDLLCLASSOBJECT
    print("找到 GETDLLCLASSOBJECT")

    # 函数原型可能是:
    # HRESULT GETDLLCLASSOBJECT(
    #   LPCOLESTR pDllName,    - DLL 名称
    #   LPCOLESTR pClassName,  - 类名
    #   REFIID riid,           - 接口 ID
    #   LPVOID *ppv            - 输出
    # )
    func.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p)
    ]
    func.restype = ctypes.HRESULT

    dll_name = "vbRichClient5.dll"
    class_name = "cConstructor"
    ppv = ctypes.c_void_p()

    hr = func(dll_name, class_name, IID_IUnknown, ctypes.byref(ppv))
    print(f"  返回值: {hr}")
    if hr == 0:
        print(f"  成功! 对象指针: {hex(ppv.value)}")
except Exception as e:
    print(f"  错误: {e}")

# 尝试 GetInstance
print("\n=== 测试 GetInstance ===")
try:
    func = dc.GETINSTANCE
    print("找到 GETINSTANCE")

    func.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p
    ]
    func.restype = ctypes.py_object

    dll_name = "vbRichClient5.dll"
    class_name = "cConstructor"

    obj = func(dll_name, class_name)
    print(f"  返回对象: {obj}")
    if obj:
        print(f"  对象类型: {type(obj)}")
except Exception as e:
    print(f"  错误: {e}")

# 尝试 GetInstanceEx
print("\n=== 测试 GetInstanceEx ===")
try:
    func = dc.GetInstanceEx
    print("找到 GetInstanceEx")

    # 尝试 py_object 返回类型
    func.restype = ctypes.py_object

    dll_name = "vbRichClient5.dll"
    class_name = "cConstructor"

    obj = func(dll_name, class_name)
    print(f"  返回对象: {obj}")
    if obj:
        print(f"  对象类型: {type(obj)}")
except Exception as e:
    print(f"  错误: {e}")

print("\n=== 测试完成 ===")
