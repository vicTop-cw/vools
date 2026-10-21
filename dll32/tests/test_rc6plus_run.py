"""测试 RC6 COM 组件（32 位 Python 直接运行）"""
import os
import sys

# VB6 Mini 运行时目录：默认使用本机路径，可用环境变量 VB6_MINI_HOME 覆盖
_vb6_home = os.environ.get('VB6_MINI_HOME', r'E:\vb\VB6Mini')
os.environ['PATH'] = os.path.join(_vb6_home, 'lib', 'vbRichClient') + os.pathsep + os.environ.get('PATH', '')

# 仓库根由 __file__ 推导，避免硬编码绝对路径
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from vools.dll32._lib.com.rc6plus import RC6Plus

print("=== RC6Plus 测试 ===")
r = RC6Plus()
print("constructor =", repr(r.constructor))

print("\n=== base64 ===")
enc = r.base64_encode('Hello World')
print("encode:", enc)
dec = r.base64_decode(enc)
print("decode:", dec)
assert dec == 'Hello World'

print("\n=== hash ===")
print("md5:", r.md5('test'))
print("sha256:", r.sha256('test'))
assert r.md5('test') == '098f6bcd4621d373cade4e832627b4f6'

print("\n=== aes ===")
e = r.aes_encrypt('data', 'password')
print("encrypted:", e)
d = r.aes_decrypt(e, 'password')
print("decrypted:", d)
assert d == b'data'

print("\n=== fso ===")
print("special folder:", r.fso.GetSpecialFolder(2))

print("\n=== RC6Plus 测试全部通过 ===")
