"""测试标准 COM 方式访问 RC6 (vbRichClient5)

对比两种"标准 COM"路径：

  1. comtypes.client.CreateObject —— 对 vbRichClient5 不可用。
     它的 TypeLib 解析失败（GetRefTypeInfo failed / "加载类型库/DLL 时出错"），
     因为 vbRichClient5.dll 的 TypeLib 里有 VB6 编译器生成的异常引用。
  2. win32com.client.gencache.EnsureDispatch —— 可用。
     makepy 会为已注册的 ProgID 生成强类型包装，AESEncrypt/ArcFour 等
     接受 SAFEARRAY(VT_UI1) 的方法才能正确传递 Byte Array。

本脚本对两者都实测，并断言 win32com 路径真实可用。
"""
import os
import sys
import warnings

# 文件位于 <repo>/dll32/tests/，上溯 3 层是仓库根，再下 dll32 即子包根
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dll32_root = os.path.join(_repo_root, 'dll32')
dll_dir = os.path.join(dll32_root, '_dlls')
os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
if os.path.isdir(os.path.join(dll32_root, 'vools')):
    sys.path.insert(0, dll32_root)

# comtypes 解析 vbRichClient5 的 TypeLib 时会发 UserWarning（已知限制），静默掉
warnings.filterwarnings('ignore', category=UserWarning, module='comtypes')

PROG_ID = "vbRichClient5.cConstructor"

print("=== 测试标准 COM 方式访问 RC6 ===")

# 方法1: comtypes（已知对 vbRichClient5 TypeLib 解析失败）
print("\n方法1: 使用 comtypes")
try:
    import comtypes.client

    obj = comtypes.client.CreateObject(PROG_ID)
    print("对象创建成功:", repr(obj))
except Exception as e:
    print("comtypes 失败（已知限制）:", type(e).__name__, str(e)[:120])
    print("  -> vbRichClient5.dll 的 TypeLib 含 VB6 生成的异常引用，comtypes 无法解析")

# 方法2: win32com EnsureDispatch（可用路径）
print("\n方法2: 使用 win32com EnsureDispatch")
from win32com.client.gencache import EnsureDispatch

obj = EnsureDispatch(PROG_ID)
print("对象创建成功:", repr(obj))

crypt = obj.Crypt()
print("Crypt 对象:", repr(crypt))

encoded = crypt.Base64Enc("Hello World")
print("Base64Enc('Hello World'):", encoded)
assert encoded[0] == 'SGVsbG8gV29ybGQ=', encoded

md5 = crypt.MD5("test")
print("MD5('test'):", md5)
assert md5[0] == '098f6bcd4621d373cade4e832627b4f6', md5

sha256 = crypt.SHA256("test")
print("SHA256('test'):", sha256)
assert sha256[0] == '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08', sha256

# AES 往返（SAFEARRAY 参数，验证 makepy 强类型包装确实生效）
enc = crypt.AESEncrypt(b'data', 'password')
print("AESEncrypt(b'data','password'):", enc)
enc_bytes = bytes(enc[1].tobytes())
print("  encrypted hex:", enc_bytes.hex())
dec = crypt.AESDecrypt(enc_bytes, 'password')
dec_bytes = bytes(dec[1].tobytes())
print("  decrypted:", dec_bytes)
assert dec_bytes == b'data', dec_bytes

print("\n=== 测试完成：win32com 标准 COM 路径可用（base64/md5/sha256/AES 往返）===")
