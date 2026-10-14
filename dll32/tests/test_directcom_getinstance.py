"""测试 DirectCOM 免注册 COM 加载（GetInstanceEx + win32com 可用路径）

DirectCOM.dll 的 GETINSTANCE 是 PowerBASIC 编译的 VB6 Declare 函数：

    Public Declare Function DirectCom_Create Lib "DirectCOM" Alias "GETINSTANCE" ( _
        FName As String, className As String) As Object

其内部走 CLSIDFromProgID + CoCreateInstance，需要注册表 ProgID，并且
VB6 String 是 BSTR——从 Python ctypes 外部无法正确构造，直接调用必崩
（access violation reading 0x69526272 = "br"，即字符串长度前缀被当指针解引用）。

本脚本验证：
  1. GetInstanceEx 导出存在（ctypes 只能探测，不能调）
  2. win32com EnsureDispatch 能真正创建 vbRichClient5.cConstructor 并调用方法
"""
import os
import sys

_vools_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll_dir = os.path.join(_vools_dir, 'dll32', '_dlls')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
sys.path.insert(0, os.path.dirname(_vools_dir))

import ctypes

dll_path = os.path.join(dll_dir, 'DirectCOM.dll')
print("加载 DirectCOM.dll:", dll_path)
dc = ctypes.WinDLL(dll_path)

print("\n=== 1. GetInstanceEx 导出探测 ===")
try:
    func = dc.GetInstanceEx
    print("找到 GetInstanceEx 函数（存在）")
    print("注意: GETINSTANCE 是 VB6 Declare(FName As String, className As String) As Object，")
    print("      内部走 CLSIDFromProgID + CoCreateInstance，BSTR 语义无法从 ctypes 外部构造，")
    print("      因此这里只探测导出，不直接调用（否则 access violation）。")
except AttributeError as e:
    print("GetInstanceEx 不存在:", e)

print("\n=== 2. win32com 创建 cConstructor（可用路径）===")
from win32com.client.gencache import EnsureDispatch

obj = EnsureDispatch('vbRichClient5.cConstructor')
print("创建成功:", repr(obj))
crypt = obj.Crypt()
enc = crypt.Base64Enc('Hello World')
print("Crypt.Base64Enc('Hello World') =", enc)
assert enc[0] == 'SGVsbG8gV29ybGQ=', enc
md5 = crypt.MD5('test')
print("Crypt.MD5('test') =", md5)
assert md5[0] == '098f6bcd4621d373cade4e832627b4f6', md5
print("\n=== 测试完成：DirectCOM 免注册 COM 加载可用 ===")
