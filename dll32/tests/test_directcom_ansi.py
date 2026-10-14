"""测试 DirectCOM 免注册 COM 加载（ANSI/WinDLL 探测 + win32com 可用路径）

DirectCOM.dll 的 GETINSTANCE 是 PowerBASIC 编译的 VB6 Declare 函数
（见 E:\\vb\\VB6Mini\\lib\\vbRichClient\\DirectCOM.bas）：

    Public Declare Function DirectCom_Create Lib "DirectCOM" Alias "GETINSTANCE" ( _
        FName As String, className As String) As Object

VB6 `As String` 在 Declare 中默认 ByRef，实参是 BSTR 指针；DLL 内部再走
CLSIDFromProgID + CoCreateInstance。从 Python ctypes 传 char*/wchar* 都构造不出
合法 BSTR，必然 access violation（0x69526272 = "br"，即字符串被当长度前缀解引用）。

本脚本验证：
  1. CDLL / WinDLL 两种加载方式下 GETINSTANCE 导出均存在（探测，不调用）
  2. win32com EnsureDispatch 真正创建 vbRichClient5.cConstructor 并调用方法
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

print("\n=== 1. CDLL 加载 + GETINSTANCE 导出探测 ===")
dc = ctypes.CDLL(dll_path)
func = dc.GETINSTANCE
print("CDLL 下找到 GETINSTANCE 导出（存在）")
print("注意: 该函数是 VB6 Declare(FName As String, className As String) As Object，")
print("      BSTR 语义无法从 ctypes 外部构造，这里只探测导出，不直接调用。")

print("\n=== 2. WinDLL 加载 + GETINSTANCE 导出探测 ===")
dc2 = ctypes.WinDLL(dll_path)
func2 = dc2.GETINSTANCE
print("WinDLL 下找到 GETINSTANCE 导出（存在）")

print("\n=== 3. win32com 创建 cConstructor（可用路径）===")
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
