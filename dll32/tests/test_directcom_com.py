"""测试 DirectCOM COM 组件"""
import os
import sys
import ctypes

# 尝试使用 COM 方式创建对象
print("=== 测试 DirectCOM COM 方式 ===")

# 方法1: 使用 comtypes
print("\n方法1: 使用 comtypes")
try:
    import comtypes.client
    # 尝试通过 ProgID 创建
    obj = comtypes.client.CreateObject("DirectCOM.Object")
    print("通过 ProgID 创建成功:", obj)
except Exception as e:
    print("通过 ProgID 创建失败:", e)

# 方法2: 检查 DirectCOM.dll 是否注册了 CLSID
print("\n检查注册表...")
try:
    import winreg
    # 尝试读取 CLSID
    clsid_key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "CLSID")
    print("成功打开 CLSID 根键")
    winreg.CloseKey(clsid_key)
except Exception as e:
    print("检查注册表失败:", e)

# 方法3: 直接用 ctypes 加载
print("\n方法3: 直接用 ctypes 加载 DirectCOM.dll")
_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_path = os.path.join(_vools_dir, 'dll32', '_dlls', 'DirectCOM.dll')
try:
    dll = ctypes.WinDLL(dll_path)
    print("DLL 加载成功")

    # 尝试获取所有可能的函数名变体
    names_to_try = [
        'DirectCom_Create', 'DirectCOM_Create', 'DirectCom_CreateObject',
        'Create', 'DirectCreate', 'CreateObject',
        'DllGetClassObject', 'GetClassObject',
    ]

    for name in names_to_try:
        try:
            func = getattr(dll, name)
            print("找到函数:", name)
            # 尝试调用
            try:
                # 尝试不同的参数组合
                result = func(b"vbRichClient5.dll", b"cConstructor")
                print("  调用成功:", result)
            except Exception as call_e:
                print("  调用失败:", call_e)
        except AttributeError:
            pass

except Exception as e:
    print("DLL 加载失败:", e)

# 检查原始 DLL
print("\n检查原始 DirectCOM.dll")
original_dll = os.path.join(os.environ.get('USERPROFILE', 'C:\\'), 'dlls', 'DirectCOM.dll')
print("原始文件存在:", os.path.exists(original_dll))

print("\n=== 测试完成 ===")
