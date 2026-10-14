"""测试 RC6 COM 组件（32 位 Python 直接运行）"""
import os
import sys

os.environ['PATH'] = r'E:\vb\VB6Mini\lib\vbRichClient' + os.pathsep + os.environ.get('PATH', '')
sys.path.insert(0, r'E:\IDEProjects\AI\vools\dll32')

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
