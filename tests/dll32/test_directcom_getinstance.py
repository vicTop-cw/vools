"""测试 DirectCOM.GetInstanceEx"""
import os
import sys
import ctypes

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_dir = os.path.join(_vools_dir, 'dll32', '_dlls')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

dll_path = os.path.join(dll_dir, 'DirectCOM.dll')
print("加载 DirectCOM.dll:", dll_path)

# 加载 DirectCOM
dc = ctypes.WinDLL(dll_path)

# 检查 GetInstanceEx 函数签名
print("\n检查 GetInstanceEx 函数...")
try:
    func = dc.GetInstanceEx
    print("找到 GetInstanceEx 函数")

    # 尝试不同的参数组合
    # 可能是 3 个参数: (DLL, Class, ppv)
    func.argtypes = [
        ctypes.c_wchar_p,  # pDllName
        ctypes.c_wchar_p,  # pClassName
        ctypes.POINTER(ctypes.c_void_p)  # ppv
    ]
    func.restype = ctypes.HRESULT

    # 创建参数
    dll_name = "vbRichClient5.dll"
    class_name = "cConstructor"
    ppv = ctypes.c_void_p()

    print("\n尝试 3 参数版本...")
    print("  DLL:", dll_name)
    print("  Class:", class_name)

    hr = func(dll_name, class_name, ctypes.byref(ppv))
    print("  返回值 (HR):", hr)

    if hr == 0:  # S_OK
        print("  成功创建对象!")
        print("  对象指针:", hex(ppv.value))
    else:
        print("  调用失败，错误码:", hr)
        # 获取错误信息
        try:
            err_func = dc.GetInstanceLastError
            err_func.argtypes = []
            err_func.restype = ctypes.c_int
            last_err = err_func()
            print("  LastError:", last_err)
        except:
            pass

except Exception as e:
    print("错误:", e)
    import traceback
    traceback.print_exc()

print("\n=== 测试完成 ===")
