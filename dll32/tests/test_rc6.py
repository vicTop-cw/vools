"""测试 RC6 COM 组件（win32com 可用路径）

验证 vools.dll32 的 RC6 封装（DirectCOM / RC6Plus）能真正创建
vbRichClient5.cConstructor 并完成 base64 / md5 / sha256 / AES 往返 / FSO。

注意：DirectCOM.dll 的 GETINSTANCE 是 VB6 Declare 函数（BSTR 语义），
不能从 ctypes 直接调；封装层走 win32com EnsureDispatch（makepy），
参见 _lib/com/directcom.py 的说明。
"""
import os
import sys

# 文件位于 <repo>/dll32/tests/，上溯 3 层是仓库根，再下 dll32 即子包根
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll32_root = os.path.join(_repo_root, 'dll32')
dll_dir = os.path.join(dll32_root, '_dlls')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
# dll32 必须插到 sys.path 最前：仓库根的 vools/ 也是命名空间容器，
# 若根目录在前，import vools.dll32 会命中根 vools 而找不到 _lib 子包。
if os.path.isdir(os.path.join(dll32_root, 'vools')):
    sys.path.insert(0, dll32_root)

print("=== 测试 DirectCOM 封装创建 vbRichClient5 对象 ===")

from vools.dll32._lib.com.directcom import DirectCOM, create_object

dc = DirectCOM()
print("DirectCOM 实例创建成功:", repr(dc))

constructor = create_object("vbRichClient5.cConstructor")
print("cConstructor 创建成功:", repr(constructor))

print("\n=== 测试 cCrypt ===")
crypt = constructor.Crypt()

encoded = crypt.Base64Enc("Hello World")
print("Base64 编码: 'Hello World' ->", encoded)
assert encoded[0] == 'SGVsbG8gV29ybGQ=', encoded

decoded = crypt.Base64Dec(encoded[0])
print("Base64 解码:", decoded)
assert decoded[0] == 'Hello World', decoded

md5_hash = crypt.MD5("test")
print("MD5: 'test' ->", md5_hash)
assert md5_hash[0] == '098f6bcd4621d373cade4e832627b4f6', md5_hash

sha256_hash = crypt.SHA256("test")
print("SHA256: 'test' ->", sha256_hash)
assert sha256_hash[0] == '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08', sha256_hash

print("\n=== 测试 cFSO ===")
fso = constructor.FSO()
temp_path = fso.GetSpecialFolder(2)
print("GetSpecialFolder(2) =", temp_path)
assert temp_path and 'AppData' in temp_path, temp_path

print("\n=== RC6 DirectCOM 测试全部通过 ===")
