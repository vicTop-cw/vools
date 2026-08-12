"""测试标准 COM 方式访问 RC6"""
import os
import sys

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_dir = os.path.join(_vools_dir, 'dll32', '_dlls')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

print("=== 测试标准 COM 方式访问 RC6 ===")

# 方法1: 使用 comtypes
print("\n方法1: 使用 comtypes")
try:
    import comtypes.client

    # 创建对象
    obj = comtypes.client.CreateObject("vbRichClient5.cConstructor")
    print("对象创建成功:", obj)

    # 获取版本
    try:
        ver = obj.Version
        print("Version:", ver)
    except Exception as e:
        print("获取 Version 失败:", e)

    # 尝试调用其他方法
    try:
        crypt = obj.Crypt()
        print("Crypt 对象:", crypt)

        # Base64 编码
        encoded = crypt.Base64Enc("Hello World")
        print("Base64Enc('Hello World'):", encoded)

        # MD5
        md5 = crypt.MD5("test")
        print("MD5('test'):", md5)

    except Exception as e:
        print("调用方法失败:", e)

except Exception as e:
    print("comtypes 失败:", e)
    import traceback
    traceback.print_exc()

# 方法2: 使用 pythoncom
print("\n方法2: 使用 pythoncom")
try:
    import pythoncom
    import win32com.client

    # 创建对象
    obj = win32com.client.Dispatch("vbRichClient5.cConstructor")
    print("对象创建成功:", obj)

    # 获取版本
    try:
        ver = obj.Version
        print("Version:", ver)
    except Exception as e:
        print("获取 Version 失败:", e)

    # 尝试调用其他方法
    try:
        crypt = obj.Crypt()
        print("Crypt 对象:", crypt)

        # Base64 编码
        encoded = crypt.Base64Enc("Hello World")
        print("Base64Enc('Hello World'):", encoded)

        # MD5
        md5 = crypt.MD5("test")
        print("MD5('test'):", md5)

    except Exception as e:
        print("调用方法失败:", e)

except Exception as e:
    print("pythoncom 失败:", e)

print("\n=== 测试完成 ===")
